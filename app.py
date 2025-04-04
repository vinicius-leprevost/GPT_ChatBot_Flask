# app.py
import os
# Correctly import specific errors from the openai library for v1.0+
from openai import OpenAI, RateLimitError, AuthenticationError, APIConnectionError, OpenAIError
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import google.api_core.exceptions
import logging

# --- Load Environment Variables ---
load_dotenv()

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# --- Configure OpenAI API ---
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    logging.error("Missing OpenAI API Key. Set it in the .env file as OPENAI_API_KEY.")
    raise ValueError("Missing OpenAI API Key. Set it in the .env file as OPENAI_API_KEY.")
if openai_api_key.startswith('"') or openai_api_key.startswith("'"):
    logging.warning("OpenAI API Key in .env might have unnecessary quotes around it.")
# Initialize the OpenAI client (recommended for v1.0+)
client = OpenAI(api_key=openai_api_key)


# --- Configure Google Generative AI (Gemini) ---
google_api_key = os.getenv("GOOGLE_API_KEY")
if not google_api_key:
    logging.error("Missing Google API Key. Set it in the .env file as GOOGLE_API_KEY.")
    raise ValueError("Missing Google API Key. Set it in the .env file as GOOGLE_API_KEY.")
if google_api_key.startswith('"') or google_api_key.startswith("'"):
    logging.warning("Google API Key in .env might have unnecessary quotes around it.")
try:
    genai.configure(api_key=google_api_key)
    logging.info("Google Generative AI configured successfully.")
except Exception as e:
     logging.error(f"Failed to configure Google Generative AI: {e}", exc_info=True)
     raise ValueError(f"Failed to configure Google Generative AI: {e}")


# --- (Optional) Simple In-Memory History ---
openai_conversation_history = [
    {"role": "system", "content": "You are a helpful and modern assistant responding via OpenAI."}
]

# --- Routes ---
@app.route('/')
def index():
    """ Renders the main chat page. """
    global openai_conversation_history
    openai_conversation_history = [{"role": "system", "content": "You are a helpful and modern assistant."}]
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    """ Handles chat requests, routing to the selected AI model. """
    global openai_conversation_history
    try:
        data = request.json
        # --- ADDED LOGGING: Print the entire received data ---
        logging.info(f"Received request data: {data}")
        # --- End Added Logging ---

        user_message = data.get('message')
        # Ensure model_choice is read correctly from the received data
        model_choice = data.get('model_choice', 'gpt') # Default to GPT if not specified

        if not user_message:
            logging.warning("Received empty message.")
            return jsonify({"error": "Empty message received."}), 400

        logging.info(f"Processing message for model: {model_choice}") # Log the choice being processed
        bot_response = ""

        # --- Route to the selected AI Model ---
        if model_choice == 'gemini':
            # (Gemini logic remains the same as before)
            try:
                model = genai.GenerativeModel('gemini-1.5-flash-latest')
                logging.info(f"Calling Gemini API with prompt: '{user_message[:50]}...'")
                response = model.generate_content(user_message)

                if response.parts:
                    bot_response = response.text
                    logging.info("Received response from Gemini API.")
                elif response.prompt_feedback.block_reason:
                     block_reason = response.prompt_feedback.block_reason.name
                     bot_response = f"Response blocked due to: {block_reason}"
                     logging.warning(f"Gemini response blocked: {block_reason}")
                else:
                     bot_response = "Gemini returned an empty response."
                     logging.warning("Gemini returned empty response.")

            except google.api_core.exceptions.PermissionDenied as e:
                 logging.error(f"Google API Permission Denied: {e}", exc_info=True)
                 return jsonify({"error": "Google API permission denied. Check your key and ensure the API is enabled."}), 403
            except google.api_core.exceptions.ResourceExhausted as e:
                 logging.error(f"Google API Quota Exceeded: {e}", exc_info=True)
                 return jsonify({"error": "Google API quota exceeded. Please try again later."}), 429
            except google.api_core.exceptions.GoogleAPIError as e:
                 logging.error(f"Google API Error: {e}", exc_info=True)
                 return jsonify({"error": "An error occurred with the Google API."}), 500
            except Exception as e:
                logging.error(f"Unexpected error calling Google Gemini API: {e}", exc_info=True)
                return jsonify({"error": "An unexpected error occurred while contacting the Google Gemini API."}), 500

        elif model_choice == 'gpt':
            try:
                current_openai_context = openai_conversation_history + [{"role": "user", "content": user_message}]

                logging.info(f"Calling OpenAI API with {len(current_openai_context)} history messages.")
                # Use the initialized client object to make the API call
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=current_openai_context,
                    temperature=0.7,
                    max_tokens=150
                )
                bot_response = response.choices[0].message.content.strip()
                logging.info("Received response from OpenAI API.")

                openai_conversation_history.append({"role": "user", "content": user_message})
                openai_conversation_history.append({"role": "assistant", "content": bot_response})

                MAX_HISTORY_LEN = 10
                if len(openai_conversation_history) > MAX_HISTORY_LEN + 1:
                    openai_conversation_history = [openai_conversation_history[0]] + openai_conversation_history[-(MAX_HISTORY_LEN):]

            # --- FIXED Error Handling for OpenAI v1.0+ ---
            except AuthenticationError as e:
                 logging.error(f"OpenAI API Authentication Failed: {e}", exc_info=True)
                 # Provide a more specific error message if possible from the exception object
                 error_message = str(e) or "Check your API key."
                 return jsonify({"error": f"OpenAI API authentication failed. {error_message}"}), 401
            except RateLimitError as e:
                # This block will now correctly catch the 429 error
                logging.error(f"OpenAI API Rate Limit Exceeded: {e}", exc_info=True)
                # Extract the specific message from the error if available
                try:
                    error_detail = e.response.json().get('error', {}).get('message', 'Please check your plan and billing details.')
                except:
                    error_detail = 'Please check your plan and billing details.'
                return jsonify({"error": f"OpenAI API request limit reached. {error_detail}"}), 429
            except APIConnectionError as e:
                logging.error(f"OpenAI API Connection Error: {e}", exc_info=True)
                return jsonify({"error": "Could not connect to OpenAI API."}), 504
            except OpenAIError as e: # Catch other specific OpenAI errors
                logging.error(f"OpenAI API Error: {e}", exc_info=True)
                error_message = str(e) or f"{type(e).__name__}"
                status_code = e.http_status if hasattr(e, 'http_status') else 500
                return jsonify({"error": f"An error occurred with the OpenAI API: {error_message}"}), status_code
            except Exception as e:
                logging.error(f"Unexpected error calling OpenAI API: {e}", exc_info=True)
                return jsonify({"error": "An unexpected error occurred while contacting the OpenAI API."}), 500
            # --- End Fixed Error Handling ---
        else:
            logging.warning(f"Received invalid model choice: {model_choice}")
            return jsonify({"error": "Invalid model choice specified."}), 400

        # --- Return successful response ---
        return jsonify({'response': bot_response})

    except Exception as e:
        # General catch-all for errors before model routing (e.g., bad JSON request)
        logging.error(f"General error in /chat endpoint: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred."}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)