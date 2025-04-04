# app.py
import os
import time
import uuid
from openai import OpenAI, RateLimitError, AuthenticationError, APIConnectionError, OpenAIError, BadRequestError
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
import google.api_core.exceptions
import logging
import secrets

# --- Load Environment Variables ---
load_dotenv()

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('werkzeug').setLevel(logging.WARNING) # Quieter Flask logs

app = Flask(__name__)

# --- Configure Flask Session ---
app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    logging.error("FATAL: FLASK_SECRET_KEY is not set in .env file. Sessions will not persist correctly.")
    # In a real app, you might raise an error here or generate a temporary one with strong warnings.
    app.secret_key = secrets.token_hex(24) # Generate temp key, but sessions won't persist reliably across restarts
    logging.warning("Using temporary FLASK_SECRET_KEY. Sessions may be lost on restart.")


# --- Constants ---
DEFAULT_SYSTEM_MESSAGE = {"role": "system", "content": "You are a helpful and modern assistant."}
TITLE_GENERATION_PROMPT_TEMPLATE = """
Generate a very concise title (max 5 words) for a chat conversation that starts with this user message:
"{user_message}"
Respond ONLY with the title itself, nothing else. Example: "Python List Comprehension"
"""
MAX_TITLE_GENERATION_TOKENS = 20
TITLE_GENERATION_MODEL = "gpt-3.5-turbo"

# --- Helper Function for Title Generation (Unchanged) ---
def generate_chat_title(user_message, api_key):
    """Generates a title for a chat using an LLM."""
    if not api_key:
        logging.warning("Cannot generate title: OpenAI API Key not found in session.")
        return "Chat " + time.strftime("%H:%M") # Fallback title

    try:
        client = OpenAI(api_key=api_key)
        prompt = TITLE_GENERATION_PROMPT_TEMPLATE.format(user_message=user_message[:200]) # Limit prompt length

        logging.info(f"Generating title with prompt: '{prompt}'")
        response = client.chat.completions.create(
            model=TITLE_GENERATION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=MAX_TITLE_GENERATION_TOKENS,
            n=1,
            stop=None,
        )
        title = response.choices[0].message.content.strip().replace('"', '') # Clean up response
        logging.info(f"Generated title: '{title}'")
        # Basic validation: If title is empty or very short/generic, use fallback
        if not title or len(title) < 3 or title.lower().startswith(("title", "chat", "conversation")):
             logging.warning(f"Generated title '{title}' seems invalid, using fallback.")
             return f"Chat: {user_message[:25]}..." # Fallback using first part of message
        return title

    except AuthenticationError:
        logging.error("OpenAI Authentication failed during title generation. Check key.")
        return "Chat Error" # Fallback
    except RateLimitError:
         logging.warning("Rate limit hit during title generation.")
         return "Chat (Rate Limited)" # Fallback
    except BadRequestError as e:
         logging.error(f"BadRequestError during title generation: {e}")
         return f"Chat: {user_message[:25]}..." # Fallback
    except Exception as e:
        logging.error(f"Error generating chat title: {e}", exc_info=True)
        return f"Chat: {user_message[:25]}..." # Fallback

# --- Routes ---

@app.route('/')
def index():
    """ Renders the main chat page, loading existing chat history for the sidebar. """
    # Initialize session structure if first visit
    if 'chats' not in session:
        session['chats'] = {}
    if 'current_chat_id' not in session:
        session['current_chat_id'] = None

    # --- LOGGING FOR KEY PERSISTENCE ---
    openai_key_present = session.get('openai_api_key') is not None
    google_key_present = session.get('google_api_key') is not None
    logging.info(f"Loading index. Current chat ID: {session.get('current_chat_id')}. Total chats: {len(session.get('chats', {}))}")
    logging.info(f"API Keys on page load: OpenAI Present = {openai_key_present}, Google Present = {google_key_present}")
    # --- END LOGGING ---

    # Convert chats dict to list for easier template iteration
    chats_list = sorted(session['chats'].values(), key=lambda x: x.get('id', '0'), reverse=True)

    current_chat_history = []
    current_title = "New Chat"
    current_chat_id = session.get('current_chat_id')

    if current_chat_id and current_chat_id in session['chats']:
        current_chat = session['chats'][current_chat_id]
        # Ensure history exists and has at least the system message
        current_chat_history = current_chat.get('history', [])
        if not current_chat_history or current_chat_history[0]['role'] != 'system':
             current_chat_history.insert(0, DEFAULT_SYSTEM_MESSAGE)
             session['chats'][current_chat_id]['history'] = current_chat_history # Fix if missing
             session.modified = True
        current_title = current_chat.get('title', 'Chat')
    else:
         # If current_chat_id is None or invalid, ensure state is clean "New Chat"
         current_chat_id = None
         session['current_chat_id'] = None # Explicitly set to None if invalid ID was found
         current_chat_history = [DEFAULT_SYSTEM_MESSAGE] # Default history for new chat view
         current_title = "New Chat"


    return render_template(
        'index.html',
        chats=chats_list,
        current_chat_id=current_chat_id,
        current_chat_history=current_chat_history,
        current_title=current_title
    )

@app.route('/new_chat', methods=['POST'])
def new_chat():
    """ Sets the application state to start a new chat. Does NOT clear API keys. """
    # --- LOGGING TO CONFIRM KEYS ARE NOT CLEARED ---
    openai_key_present_before = session.get('openai_api_key') is not None
    google_key_present_before = session.get('google_api_key') is not None
    logging.info(f"Executing /new_chat. Current chat ID was: {session.get('current_chat_id')}")
    logging.info(f"API Keys BEFORE setting current_chat_id=None: OpenAI Present={openai_key_present_before}, Google Present={google_key_present_before}")
    # --- END LOGGING ---

    session['current_chat_id'] = None
    session.modified = True # Good practice when changing session

    # --- LOGGING AFTER CHANGE ---
    openai_key_present_after = session.get('openai_api_key') is not None
    google_key_present_after = session.get('google_api_key') is not None
    logging.info(f"Finished /new_chat. Current chat ID is now: {session.get('current_chat_id')}")
    logging.info(f"API Keys AFTER setting current_chat_id=None: OpenAI Present={openai_key_present_after}, Google Present={google_key_present_after}")
    # --- END LOGGING ---

    return jsonify({"message": "New chat session initiated."}), 200

@app.route('/load_chat/<chat_id>', methods=['GET'])
def load_chat(chat_id):
    """ Loads the history and title of a specific chat into the session and returns it. """
    if 'chats' not in session or chat_id not in session['chats']:
        logging.warning(f"Attempted to load non-existent chat ID: {chat_id}")
        return jsonify({"error": "Chat not found."}), 404

    session['current_chat_id'] = chat_id
    chat_data = session['chats'][chat_id]

    # Ensure history exists and starts with system message
    history = chat_data.get('history', [])
    if not history or history[0].get('role') != 'system':
         history.insert(0, DEFAULT_SYSTEM_MESSAGE)
         chat_data['history'] = history # Update the data to be sent back
         session['chats'][chat_id]['history'] = history # Update in session too
         logging.warning(f"Corrected missing/invalid system message for chat {chat_id}")

    logging.info(f"Loading chat ID: {chat_id}, Title: {chat_data.get('title')}")
    session.modified = True # Ensure session is saved
    return jsonify({
        "id": chat_id,
        "title": chat_data.get('title', 'Chat'),
        "history": history # Send corrected history
    }), 200

# --- /save_api_keys route remains unchanged ---
@app.route('/save_api_keys', methods=['POST'])
def save_api_keys():
    """ Saves API keys provided by the user into the session. """
    try:
        data = request.json
        openai_key = data.get('openai_key')
        google_key = data.get('google_key')
        changed = False
        # Logic for saving/updating/removing keys in session
        if openai_key:
            if session.get('openai_api_key') != openai_key:
                 session['openai_api_key'] = openai_key
                 logging.info("OpenAI API Key saved/updated in session.")
                 changed = True
        else:
            if session.pop('openai_api_key', None): # Remove if empty/not provided
                 logging.info("OpenAI API Key removed from session.")
                 changed = True

        if google_key:
             if session.get('google_api_key') != google_key:
                 session['google_api_key'] = google_key
                 logging.info("Google API Key saved/updated in session.")
                 changed = True
        else:
             if session.pop('google_api_key', None): # Remove if empty/not provided
                 logging.info("Google API Key removed from session.")
                 changed = True

        if changed:
             session.modified = True
             return jsonify({"message": "API keys updated successfully."}), 200
        else:
             return jsonify({"message": "API keys unchanged."}), 200

    except Exception as e:
        logging.error(f"Error saving API keys: {e}", exc_info=True)
        # Avoid marking modified unless sure, could overwrite valid keys if read failed
        return jsonify({"error": "Failed to save API keys."}), 500


# --- /chat route remains largely unchanged, using session keys ---
@app.route('/chat', methods=['POST'])
def chat():
    """ Handles chat requests, manages history, generates titles, and routes to the AI model using session keys. """
    try:
        data = request.json
        logging.debug(f"Received chat request data: {data}")

        user_message_content = data.get('message')
        model_choice = data.get('model_choice', 'gpt')

        if not user_message_content:
            logging.warning("Received empty message.")
            return jsonify({"error": "Empty message received."}), 400

        if 'chats' not in session:
             session['chats'] = {} # Initialize if missing

        current_chat_id = session.get('current_chat_id')
        is_new_chat = current_chat_id is None
        new_chat_info = None

        openai_api_key = session.get('openai_api_key') # Get key for potential title generation

        if is_new_chat:
            # --- Create a new chat ---
            new_id = str(uuid.uuid4())
            current_chat_id = new_id
            session['current_chat_id'] = new_id
            initial_history = [DEFAULT_SYSTEM_MESSAGE] # Start with system message
            # Generate title *before* saving the initial structure
            generated_title = generate_chat_title(user_message_content, openai_api_key)
            session['chats'][current_chat_id] = {
                'id': current_chat_id,
                'title': generated_title,
                'history': initial_history
            }
            logging.info(f"Created new chat with ID: {current_chat_id}, Title: '{generated_title}'")
            new_chat_info = {'id': current_chat_id, 'title': generated_title} # Prepare info for frontend
            current_chat_history = initial_history # Use the newly created history
        else:
            # --- Load existing chat ---
            if current_chat_id not in session['chats']:
                 logging.error(f"Current chat ID {current_chat_id} not found in session chats. Resetting.")
                 session['current_chat_id'] = None
                 session.modified = True
                 return jsonify({"error": "Current chat session is invalid. Please start a new chat."}), 400

            # Ensure history exists and starts correctly
            current_chat_history = session['chats'][current_chat_id].get('history', [])
            if not current_chat_history or current_chat_history[0].get('role') != 'system':
                 current_chat_history.insert(0, DEFAULT_SYSTEM_MESSAGE)
                 session['chats'][current_chat_id]['history'] = current_chat_history
                 logging.warning(f"Corrected missing/invalid system message for chat {current_chat_id} during chat request")


        # --- Append user message ---
        user_message = {"role": "user", "content": user_message_content}
        current_chat_history.append(user_message)

        logging.info(f"Processing message for model: {model_choice} in chat: {current_chat_id}")
        bot_response_content = ""
        error_occurred = False
        status_code = 200

        # --- API Key Check and AI Call (Gemini) ---
        if model_choice == 'gemini':
            google_api_key = session.get('google_api_key')
            if not google_api_key:
                 error_message = "Google API Key not set. Please add it via 'API Keys'."
                 logging.warning(f"{error_message} (Chat ID: {current_chat_id})")
                 bot_response_content = f"ERROR: {error_message}"
                 error_occurred = True
                 status_code = 400
            else:
                # --- Gemini API Call Logic (remains the same) ---
                try:
                    genai.configure(api_key=google_api_key)
                    model = genai.GenerativeModel('gemini-1.5-flash-latest')
                    logging.info(f"Calling Gemini API with prompt (simplified): '{user_message_content[:50]}...'")
                    # Consider sending relevant history parts to Gemini if needed by the model
                    response = model.generate_content(user_message_content)

                    if response.parts:
                        bot_response_content = response.text
                        logging.info("Received response from Gemini API.")
                    elif hasattr(response, 'prompt_feedback') and response.prompt_feedback and hasattr(response.prompt_feedback, 'block_reason') and response.prompt_feedback.block_reason:
                        block_reason = response.prompt_feedback.block_reason.name
                        bot_response_content = f"Response blocked due to: {block_reason}"
                        logging.warning(f"Gemini response blocked: {block_reason}")
                    else:
                        bot_response_content = "Gemini returned an empty or unexpected response."
                        logging.warning(f"Gemini returned empty/unexpected response. Response: {response}")

                # --- Gemini Error Handling (remains the same) ---
                except (google.api_core.exceptions.PermissionDenied, google.api_core.exceptions.InvalidArgument) as e:
                    logging.error(f"Google API Auth/Argument Error: {e}", exc_info=False) # Less verbose logs for common errors
                    bot_response_content = "ERROR: Google API permission denied or invalid argument. Check your key/API settings."
                    error_occurred = True
                    status_code = 403
                except google.api_core.exceptions.ResourceExhausted as e:
                    logging.error(f"Google API Quota Exceeded: {e}", exc_info=False)
                    bot_response_content = "ERROR: Google API quota exceeded. Please try again later."
                    error_occurred = True
                    status_code = 429
                except google.api_core.exceptions.GoogleAPIError as e:
                    logging.error(f"Google API Error: {e}", exc_info=True)
                    bot_response_content = "ERROR: An error occurred with the Google API."
                    error_occurred = True
                    status_code = 500
                except Exception as e:
                    logging.error(f"Unexpected error calling Google Gemini API: {e}", exc_info=True)
                    bot_response_content = "ERROR: An unexpected error occurred with the Google Gemini API."
                    error_occurred = True
                    status_code = 500

        # --- API Key Check and AI Call (GPT) ---
        elif model_choice == 'gpt':
            # openai_api_key already fetched for potential title generation
            if not openai_api_key:
                error_message = "OpenAI API Key not set. Please add it via 'API Keys'."
                logging.warning(f"{error_message} (Chat ID: {current_chat_id})")
                bot_response_content = f"ERROR: {error_message}"
                error_occurred = True
                status_code = 400
            else:
                # --- OpenAI API Call Logic (remains the same) ---
                try:
                    client = OpenAI(api_key=openai_api_key)
                    logging.info(f"Calling OpenAI API with {len(current_chat_history)} history messages for chat {current_chat_id}.")
                    # Make sure current_chat_history includes the latest user message
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=current_chat_history,
                        temperature=0.7,
                        max_tokens=150
                    )
                    bot_response_content = response.choices[0].message.content.strip()
                    logging.info("Received response from OpenAI API.")

                # --- OpenAI Error Handling (remains the same) ---
                except AuthenticationError as e:
                    logging.error(f"OpenAI API Authentication Failed: {e}", exc_info=False)
                    bot_response_content = f"ERROR: OpenAI API authentication failed. Check your key."
                    error_occurred = True
                    status_code = 401
                except RateLimitError as e:
                    logging.error(f"OpenAI API Rate Limit Exceeded: {e}", exc_info=False)
                    bot_response_content = f"ERROR: OpenAI API request limit reached. Check plan/billing."
                    error_occurred = True
                    status_code = 429
                except APIConnectionError as e:
                    logging.error(f"OpenAI API Connection Error: {e}", exc_info=True)
                    bot_response_content = "ERROR: Could not connect to OpenAI API."
                    error_occurred = True
                    status_code = 504
                except BadRequestError as e:
                     logging.error(f"OpenAI API BadRequestError: {e}", exc_info=True)
                     error_message = str(e) or "Invalid request sent to OpenAI."
                     bot_response_content = f"ERROR: OpenAI API request error: {error_message}"
                     error_occurred = True
                     status_code = e.status_code if hasattr(e, 'status_code') else 400
                except OpenAIError as e:
                    logging.error(f"OpenAI API Error: {e}", exc_info=True)
                    error_message = str(e) or "An unknown error occurred."
                    status_code = e.http_status if hasattr(e, 'http_status') else 500
                    bot_response_content = f"ERROR: An error occurred with the OpenAI API: {error_message}"
                    error_occurred = True
                except Exception as e:
                    logging.error(f"Unexpected error calling OpenAI API: {e}", exc_info=True)
                    bot_response_content = "ERROR: An unexpected error occurred while contacting the OpenAI API."
                    error_occurred = True
                    status_code = 500
        else:
            bot_response_content = "ERROR: Invalid model choice specified."
            error_occurred = True
            status_code = 400

        # --- Append bot response to history if successful ---
        if not error_occurred and bot_response_content:
             bot_message = {"role": "assistant", "content": bot_response_content}
             current_chat_history.append(bot_message)
        elif error_occurred:
             # Log the error response content for debugging, but don't add "ERROR: ..." to history
             logging.error(f"Error response generated for chat {current_chat_id}: {bot_response_content}")


        # --- Trim History ---
        MAX_HISTORY_MESSAGES = 20 # Max user+assistant messages (excluding system)
        if len(current_chat_history) > (MAX_HISTORY_MESSAGES + 1): # +1 for system prompt
            # Keep system prompt + last MAX_HISTORY_MESSAGES
            current_chat_history = [current_chat_history[0]] + current_chat_history[-(MAX_HISTORY_MESSAGES):]
            session['chats'][current_chat_id]['history'] = current_chat_history
            logging.info(f"Trimmed history for chat {current_chat_id} to {len(current_chat_history)-1} user/assistant messages")

        # --- Mark session as modified ---
        session.modified = True

        # --- Return Response ---
        response_data = {}
        if error_occurred:
             response_data['error'] = bot_response_content # Send specific error message
        else:
            response_data['response'] = bot_response_content # Send successful response

        if new_chat_info:
            response_data['new_chat_info'] = new_chat_info # Always include if generated

        return jsonify(response_data), status_code # Return appropriate status code

    except Exception as e:
        logging.error(f"General error in /chat endpoint: {e}", exc_info=True)
        session.modified = True # Ensure session is saved on unexpected errors
        return jsonify({"error": "An internal server error occurred processing your request."}), 500


if __name__ == '__main__':
    # Make sure debug=False and use a proper WSGI server (like gunicorn) in production
    app.run(host='0.0.0.0', port=5000, debug=True)