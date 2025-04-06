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
# Suppress excessive retry logs from OpenAI client during rate limiting for title generation
logging.getLogger("openai").setLevel(logging.WARNING)


app = Flask(__name__)

# --- Configure Flask Session ---
app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    logging.error("FATAL: FLASK_SECRET_KEY is not set in .env file. Sessions will not persist correctly.")
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
# Define models for title generation per provider
TITLE_GENERATION_MODEL_GPT = "gpt-3.5-turbo"
# Use a fast model for Gemini title generation
TITLE_GENERATION_MODEL_GEMINI = "gemini-1.5-flash-latest"

# --- MODIFIED Helper Function for Title Generation ---
def generate_chat_title(user_message, model_choice, openai_api_key, google_api_key):
    """Generates a title for a chat using the API key for the selected model."""
    fallback_title = "Chat " + time.strftime("%H:%M") # Default fallback

    prompt_content = TITLE_GENERATION_PROMPT_TEMPLATE.format(user_message=user_message[:200]) # Limit prompt length

    try:
        if model_choice == 'gemini':
            if not google_api_key:
                logging.warning("Cannot generate title with Gemini: Google API Key not found in session.")
                return fallback_title + " (Key Missing)"
            logging.info(f"Generating title with Gemini ({TITLE_GENERATION_MODEL_GEMINI})...")
            genai.configure(api_key=google_api_key)
            model = genai.GenerativeModel(TITLE_GENERATION_MODEL_GEMINI)
            # Simple prompt, no history needed for title
            response = model.generate_content(prompt_content)
            title = response.text.strip().replace('"', '')

        elif model_choice == 'gpt':
            if not openai_api_key:
                logging.warning("Cannot generate title with GPT: OpenAI API Key not found in session.")
                return fallback_title + " (Key Missing)"
            logging.info(f"Generating title with OpenAI ({TITLE_GENERATION_MODEL_GPT})...")
            client = OpenAI(api_key=openai_api_key, max_retries=1) # Reduce retries for title to fail faster on rate limit
            response = client.chat.completions.create(
                model=TITLE_GENERATION_MODEL_GPT,
                messages=[{"role": "user", "content": prompt_content}],
                temperature=0.3,
                max_tokens=MAX_TITLE_GENERATION_TOKENS,
                n=1,
                stop=None,
            )
            title = response.choices[0].message.content.strip().replace('"', '')

        else:
            logging.warning(f"Cannot generate title: Invalid model_choice '{model_choice}'.")
            return fallback_title + " (Model Invalid)"

        logging.info(f"Generated title: '{title}' using {model_choice}")
        # Basic validation: If title is empty or very short/generic, use fallback
        if not title or len(title) < 3 or title.lower().startswith(("title", "chat", "conversation", "response", "untitled")):
             logging.warning(f"Generated title '{title}' seems invalid/generic, using fallback.")
             # Use a slightly different fallback if generation seemed to work but was poor
             return f"Chat: {user_message[:25]}..."
        return title

    # --- Specific Error Handling ---
    # OpenAI
    except AuthenticationError as e:
        logging.error(f"OpenAI Authentication failed during title generation: {e}")
        return fallback_title + " (Auth Error)"
    except RateLimitError as e:
         logging.warning(f"OpenAI Rate limit hit during title generation: {e}")
         return fallback_title + " (Rate Limit)"
    except BadRequestError as e:
         logging.error(f"OpenAI BadRequestError during title generation: {e}")
         return fallback_title + " (Request Error)"
    except OpenAIError as e:
        logging.error(f"OpenAI API Error during title generation: {e}")
        return fallback_title + " (API Error)"
    # Google / Gemini
    except (google.api_core.exceptions.PermissionDenied, google.api_core.exceptions.InvalidArgument) as e:
        logging.error(f"Google API Auth/Argument Error during title generation: {e}", exc_info=False)
        return fallback_title + " (Auth Error)"
    except google.api_core.exceptions.ResourceExhausted as e:
        logging.error(f"Google API Quota Exceeded during title generation: {e}", exc_info=False)
        return fallback_title + " (Rate Limit)"
    except google.api_core.exceptions.GoogleAPIError as e:
        logging.error(f"Google API Error during title generation: {e}", exc_info=True)
        return fallback_title + " (API Error)"
    # General
    except Exception as e:
        logging.error(f"Unexpected error generating chat title using {model_choice}: {e}", exc_info=True)
        return fallback_title + " (Error)"


# --- Routes (Index, New Chat, Load Chat, Update Title, Delete Chat, Save API Keys remain unchanged) ---

@app.route('/')
def index():
    """ Renders the main chat page, loading existing chat history for the sidebar. """
    # Initialize session structure if first visit
    if 'chats' not in session:
        session['chats'] = {}
    if 'current_chat_id' not in session:
        session['current_chat_id'] = None

    openai_key_present = session.get('openai_api_key') is not None
    google_key_present = session.get('google_api_key') is not None
    logging.info(f"Loading index. Current chat ID: {session.get('current_chat_id')}. Total chats: {len(session.get('chats', {}))}")
    logging.info(f"API Keys on page load: OpenAI Present = {openai_key_present}, Google Present = {google_key_present}")

    chats_list = sorted(
        [chat for chat in session['chats'].values() if 'id' in chat],
        key=lambda x: x.get('id', '0'),
        reverse=True
    )

    current_chat_history = []
    current_title = "New Chat"
    current_chat_id = session.get('current_chat_id')

    if current_chat_id and current_chat_id in session['chats']:
        current_chat = session['chats'][current_chat_id]
        current_chat_history = current_chat.get('history', [])
        if not isinstance(current_chat_history, list):
            current_chat_history = []
        if not current_chat_history or current_chat_history[0].get('role') != 'system':
             current_chat_history.insert(0, DEFAULT_SYSTEM_MESSAGE)
             session['chats'][current_chat_id]['history'] = current_chat_history # Fix if missing
             session.modified = True
             logging.warning(f"Corrected missing/invalid system message for chat {current_chat_id} on index load")
        current_title = current_chat.get('title', 'Chat')
    else:
         current_chat_id = None
         if session.get('current_chat_id') is not None:
             logging.info(f"Invalid current_chat_id '{session.get('current_chat_id')}' found, resetting to None.")
             session['current_chat_id'] = None # Explicitly set to None if invalid ID was found
             session.modified = True
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
    openai_key_present_before = session.get('openai_api_key') is not None
    google_key_present_before = session.get('google_api_key') is not None
    logging.info(f"Executing /new_chat. Current chat ID was: {session.get('current_chat_id')}")
    logging.info(f"API Keys BEFORE setting current_chat_id=None: OpenAI Present={openai_key_present_before}, Google Present={google_key_present_before}")

    session['current_chat_id'] = None
    session.modified = True # Good practice when changing session

    openai_key_present_after = session.get('openai_api_key') is not None
    google_key_present_after = session.get('google_api_key') is not None
    logging.info(f"Finished /new_chat. Current chat ID is now: {session.get('current_chat_id')}")
    logging.info(f"API Keys AFTER setting current_chat_id=None: OpenAI Present={openai_key_present_after}, Google Present={google_key_present_after}")

    return jsonify({"message": "New chat session initiated."}), 200

@app.route('/load_chat/<chat_id>', methods=['GET'])
def load_chat(chat_id):
    """ Loads the history and title of a specific chat into the session and returns it. """
    if 'chats' not in session or chat_id not in session['chats']:
        logging.warning(f"Attempted to load non-existent chat ID: {chat_id}")
        return jsonify({"error": "Chat not found."}), 404

    session['current_chat_id'] = chat_id
    chat_data = session['chats'][chat_id]

    history = chat_data.get('history', [])
    if not isinstance(history, list): # Ensure history is a list
        history = []
    if not history or history[0].get('role') != 'system':
         history.insert(0, DEFAULT_SYSTEM_MESSAGE)
         chat_data['history'] = history # Update the data to be sent back
         session['chats'][chat_id]['history'] = history # Update in session too
         session.modified = True # Mark session as modified because we fixed history
         logging.warning(f"Corrected missing/invalid system message for chat {chat_id}")

    logging.info(f"Loading chat ID: {chat_id}, Title: {chat_data.get('title')}")
    return jsonify({
        "id": chat_id,
        "title": chat_data.get('title', 'Chat'),
        "history": history # Send corrected history
    }), 200

@app.route('/update_title/<chat_id>', methods=['POST'])
def update_title(chat_id):
    """ Updates the title of a specific chat. """
    if 'chats' not in session or chat_id not in session['chats']:
        return jsonify({"error": "Chat not found"}), 404

    data = request.json
    new_title = data.get('new_title', '').strip()
    MAX_TITLE_LENGTH = 100 # Consistent with JS

    if not new_title:
        return jsonify({"error": "Title cannot be empty."}), 400
    if len(new_title) > MAX_TITLE_LENGTH:
         return jsonify({"error": f"Title cannot exceed {MAX_TITLE_LENGTH} characters."}), 400

    try:
        session['chats'][chat_id]['title'] = new_title
        session.modified = True
        logging.info(f"Updated title for chat {chat_id} to '{new_title}'")
        return jsonify({"message": "Title updated successfully.", "new_title": new_title}), 200
    except Exception as e:
        logging.error(f"Error updating title for chat {chat_id}: {e}", exc_info=True)
        return jsonify({"error": "Failed to update title on server."}), 500

@app.route('/delete_chat/<chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    """ Deletes a specific chat from the session. """
    logging.info(f"Attempting to delete chat ID: {chat_id}")
    if 'chats' not in session or chat_id not in session['chats']:
        logging.warning(f"Delete failed: Chat ID {chat_id} not found in session.")
        return jsonify({"error": "Chat not found."}), 404

    try:
        deleted_chat_title = session['chats'][chat_id].get('title', 'Unknown Chat')
        del session['chats'][chat_id] # Remove the chat data

        if session.get('current_chat_id') == chat_id:
            session['current_chat_id'] = None
            logging.info(f"Deleted chat {chat_id} was the active chat. Resetting current_chat_id.")

        session.modified = True # IMPORTANT: Ensure session changes are saved
        logging.info(f"Successfully deleted chat ID: {chat_id} (Title: '{deleted_chat_title}')")
        return jsonify({"message": "Chat deleted successfully."}), 200

    except KeyError:
        logging.warning(f"Delete failed: Chat ID {chat_id} caused KeyError during deletion (might indicate race condition or session issue).")
        return jsonify({"error": "Chat not found during deletion."}), 404
    except Exception as e:
        logging.error(f"Error deleting chat ID {chat_id}: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred while deleting the chat."}), 500

@app.route('/save_api_keys', methods=['POST'])
def save_api_keys():
    """ Saves API keys provided by the user into the session. """
    try:
        data = request.json
        openai_key = data.get('openai_key')
        google_key = data.get('google_key')
        changed = False

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
        return jsonify({"error": "Failed to save API keys."}), 500


# --- /chat route MODIFIED to pass model_choice to title generation ---
@app.route('/chat', methods=['POST'])
def chat():
    """ Handles chat requests, manages history, generates titles using selected model's key, and routes to the AI model. """
    try:
        data = request.json
        logging.debug(f"Received chat request data: {data}")

        user_message_content = data.get('message')
        model_choice = data.get('model_choice', 'gemini') # Default to gemini if not provided

        if not user_message_content:
            logging.warning("Received empty message.")
            return jsonify({"error": "Empty message received."}), 400

        if 'chats' not in session:
             session['chats'] = {} # Initialize if missing

        current_chat_id = session.get('current_chat_id')
        is_new_chat = current_chat_id is None
        new_chat_info = None

        # --- Fetch keys needed for title generation and chat itself ---
        openai_api_key = session.get('openai_api_key')
        google_api_key = session.get('google_api_key')

        if is_new_chat:
            # --- Create a new chat ---
            new_id = str(uuid.uuid4())
            current_chat_id = new_id
            session['current_chat_id'] = new_id
            initial_history = [DEFAULT_SYSTEM_MESSAGE] # Start with system message

            # --- Generate title using the appropriate key based on model_choice ---
            generated_title = generate_chat_title(
                user_message_content,
                model_choice, # Pass the selected model
                openai_api_key,
                google_api_key
            )
            # --- End title generation change ---

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

            current_chat_history = session['chats'][current_chat_id].get('history', [])
            if not isinstance(current_chat_history, list): # Ensure it's a list
                 current_chat_history = []
            if not current_chat_history or current_chat_history[0].get('role') != 'system':
                 current_chat_history.insert(0, DEFAULT_SYSTEM_MESSAGE)
                 session['chats'][current_chat_id]['history'] = current_chat_history
                 session.modified = True # Mark modified as history was changed
                 logging.warning(f"Corrected missing/invalid system message for chat {current_chat_id} during chat request")


        # --- Append user message ---
        user_message = {"role": "user", "content": user_message_content}
        current_chat_history.append(user_message)

        logging.info(f"Processing message for model: {model_choice} in chat: {current_chat_id}")
        bot_response_content = ""
        error_occurred = False
        is_api_error = False # Flag specifically for API key issues
        status_code = 200

        # --- API Key Check and AI Call (Gemini) ---
        if model_choice == 'gemini':
            # google_api_key already fetched
            if not google_api_key:
                 error_message = "Google API Key not set. Please add it via 'API Keys'."
                 logging.warning(f"{error_message} (Chat ID: {current_chat_id})")
                 bot_response_content = f"ERROR: {error_message}"
                 error_occurred = True
                 is_api_error = True
                 status_code = 400 # Bad Request (client-side issue - missing key)
            else:
                try:
                    genai.configure(api_key=google_api_key)
                    model = genai.GenerativeModel('gemini-1.5-flash-latest') # Or 'gemini-1.5-pro-latest'
                    logging.info(f"Calling Gemini API with prompt (simplified): '{user_message_content[:50]}...'")

                    # Convert chat history for Gemini API
                    gemini_history = []
                    for msg in current_chat_history[:-1]: # Exclude the last user message
                        role = 'user' if msg['role'] == 'user' else 'model'
                        if msg['role'] != 'system': # Skip system message for Gemini history
                            gemini_history.append({'role': role, 'parts': [msg['content']]})

                    chat_session = model.start_chat(history=gemini_history)
                    response = chat_session.send_message(user_message_content)

                    if response.parts:
                        bot_response_content = response.text
                        logging.info("Received response from Gemini API.")
                    elif hasattr(response, 'prompt_feedback') and response.prompt_feedback and hasattr(response.prompt_feedback, 'block_reason') and response.prompt_feedback.block_reason:
                        block_reason = response.prompt_feedback.block_reason.name
                        bot_response_content = f"Response blocked due to: {block_reason}"
                        logging.warning(f"Gemini response blocked: {block_reason}")
                        error_occurred = True # Treat as error for UI
                    else:
                        bot_response_content = "Gemini returned an empty or unexpected response."
                        logging.warning(f"Gemini returned empty/unexpected response. Response: {response}")
                        error_occurred = True

                except (google.api_core.exceptions.PermissionDenied, google.api_core.exceptions.InvalidArgument) as e:
                    error_msg = str(e)
                    logging.error(f"Google API Auth/Argument Error: {error_msg}", exc_info=False)
                    bot_response_content = f"ERROR: Google API permission denied or invalid argument. Check your key/API settings. ({type(e).__name__})"
                    error_occurred = True
                    is_api_error = True
                    status_code = 403 # Forbidden
                except google.api_core.exceptions.ResourceExhausted as e:
                    logging.error(f"Google API Quota Exceeded: {e}", exc_info=False)
                    bot_response_content = "ERROR: Google API quota exceeded. Please try again later."
                    error_occurred = True
                    status_code = 429 # Too Many Requests
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
            # openai_api_key already fetched
            if not openai_api_key:
                error_message = "OpenAI API Key not set. Please add it via 'API Keys'."
                logging.warning(f"{error_message} (Chat ID: {current_chat_id})")
                bot_response_content = f"ERROR: {error_message}"
                error_occurred = True
                is_api_error = True
                status_code = 400 # Bad Request
            else:
                try:
                    client = OpenAI(api_key=openai_api_key) # Default retries are fine for main chat
                    logging.info(f"Calling OpenAI API with {len(current_chat_history)} history messages for chat {current_chat_id}.")
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=current_chat_history,
                        temperature=0.7,
                        max_tokens=150 # Consider making this configurable
                    )
                    bot_response_content = response.choices[0].message.content.strip()
                    logging.info("Received response from OpenAI API.")

                except AuthenticationError as e:
                    logging.error(f"OpenAI API Authentication Failed: {e}", exc_info=False)
                    bot_response_content = f"ERROR: OpenAI API authentication failed. Check your key."
                    error_occurred = True
                    is_api_error = True
                    status_code = 401 # Unauthorized
                except RateLimitError as e:
                    logging.error(f"OpenAI API Rate Limit Exceeded: {e}", exc_info=False)
                    bot_response_content = f"ERROR: OpenAI API request limit reached. Check plan/billing."
                    error_occurred = True
                    status_code = 429 # Too Many Requests
                except APIConnectionError as e:
                    logging.error(f"OpenAI API Connection Error: {e}", exc_info=True)
                    bot_response_content = "ERROR: Could not connect to OpenAI API."
                    error_occurred = True
                    status_code = 504 # Gateway Timeout
                except BadRequestError as e:
                     logging.error(f"OpenAI API BadRequestError: {e}", exc_info=True)
                     error_message = str(e) or "Invalid request sent to OpenAI."
                     if "content_policy_violation" in error_message.lower():
                         bot_response_content = "Response blocked due to OpenAI's content policy."
                         logging.warning(f"OpenAI content policy violation for chat {current_chat_id}")
                     else:
                         bot_response_content = f"ERROR: OpenAI API request error: {error_message}"
                     error_occurred = True
                     status_code = e.status_code if hasattr(e, 'status_code') else 400
                except OpenAIError as e:
                    logging.error(f"OpenAI API Error: {e}", exc_info=True)
                    error_message = str(e) or "An unknown error occurred."
                    status_code_from_error = e.http_status if hasattr(e, 'http_status') else 500
                    bot_response_content = f"ERROR: An error occurred with the OpenAI API: {error_message}"
                    error_occurred = True
                    status_code = status_code_from_error
                except Exception as e:
                    logging.error(f"Unexpected error calling OpenAI API: {e}", exc_info=True)
                    bot_response_content = "ERROR: An unexpected error occurred while contacting the OpenAI API."
                    error_occurred = True
                    status_code = 500
        else:
            bot_response_content = "ERROR: Invalid model choice specified."
            error_occurred = True
            status_code = 400 # Bad Request

        # --- Append bot response to history ---
        if not error_occurred and bot_response_content:
             bot_message = {"role": "assistant", "content": bot_response_content}
             current_chat_history.append(bot_message)
        elif error_occurred:
             logging.error(f"Error response generated for chat {current_chat_id}: {bot_response_content}")
             if not is_api_error and current_chat_history and current_chat_history[-1]['role'] == 'user':
                  logging.warning(f"Removing last user message from history for chat {current_chat_id} due to non-API error.")
                  current_chat_history.pop()

        # --- Trim History ---
        MAX_HISTORY_MESSAGES = 20 # Max user+assistant messages (excluding system)
        if len(current_chat_history) > (MAX_HISTORY_MESSAGES + 1): # +1 for system prompt
            messages_to_keep = current_chat_history[-(MAX_HISTORY_MESSAGES):]
            current_chat_history = [current_chat_history[0]] + messages_to_keep
            session['chats'][current_chat_id]['history'] = current_chat_history
            logging.info(f"Trimmed history for chat {current_chat_id} to {len(current_chat_history)-1} user/assistant messages")

        # --- Mark session as modified ---
        session.modified = True

        # --- Return Response ---
        response_data = {
            "is_error": error_occurred,
            # Use 'response' key for both success and error messages
            'response': bot_response_content
        }
        if new_chat_info:
            response_data['new_chat_info'] = new_chat_info

        return jsonify(response_data), status_code

    except Exception as e:
        logging.error(f"General error in /chat endpoint: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred processing your request.", "is_error": True}), 500


if __name__ == '__main__':
    # Use Gunicorn or another WSGI server in production instead of app.run(debug=True)
    # Example: gunicorn --bind 0.0.0.0:5000 app:app
    app.run(host='0.0.0.0', port=5000, debug=True) # Use debug=True only for development