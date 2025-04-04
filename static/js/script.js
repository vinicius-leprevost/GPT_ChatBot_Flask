// static/js/script.js

document.addEventListener('DOMContentLoaded', () => {
    const messageForm = document.getElementById('message-form');
    const messageInput = document.getElementById('message-input');
    const chatWindow = document.getElementById('chat-window');
    const sendButton = document.getElementById('send-button');
    const typingIndicator = document.getElementById('typing-indicator');

    // Function to append a message to the chat window
    function appendMessage(sender, text) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', sender === 'user' ? 'user-message' : 'bot-message');
        // Use textContent for security (prevents XSS from text)
        messageDiv.textContent = text;
        chatWindow.appendChild(messageDiv);
        // Scroll to the bottom
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    // Function to show/hide the typing indicator
    function showTypingIndicator(show) {
        typingIndicator.style.display = show ? 'flex' : 'none';
         if (show) {
             chatWindow.scrollTop = chatWindow.scrollHeight; // Ensure indicator is visible
         }
    }

    // Handle form submission (send message)
    messageForm.addEventListener('submit', async (event) => {
        event.preventDefault(); // Prevent default page reload

        const userMessage = messageInput.value.trim();
        if (!userMessage) return; // Don't send empty messages

        appendMessage('user', userMessage); // Display user message immediately
        messageInput.value = ''; // Clear input field
        messageInput.focus(); // Keep focus on input
        sendButton.disabled = true; // Disable send button during processing
        showTypingIndicator(true); // Show "Bot is typing..."

        try {
            // Send message to the Flask backend
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: userMessage }),
            });

            showTypingIndicator(false); // Hide "Bot is typing..."

            if (!response.ok) {
                 // Try to get detailed error from JSON response body
                 let errorMsg = `Error: ${response.statusText}`;
                 try {
                     const errorData = await response.json();
                     // Use error message from backend if available
                     errorMsg = errorData.error || errorMsg;
                 } catch (e) { /* Ignore if response is not JSON */ }
                console.error('Server response error:', response.status, errorMsg);
                // Display error message in English
                appendMessage('bot', `Sorry, there was an error processing your request. (${errorMsg})`);
                return; // Stop processing on error
            }

            // Process successful response
            const data = await response.json();
            if (data.response) {
                appendMessage('bot', data.response); // Display bot response
            } else if (data.error) {
                 // Handle errors explicitly returned in JSON data
                 console.error('Server returned error:', data.error);
                 // Display error message in English
                 appendMessage('bot', `Sorry, an error occurred: ${data.error}`);
            }

        } catch (error) {
            showTypingIndicator(false); // Hide indicator on network error
            console.error('Network or fetch error:', error);
            // Display error message in English
            appendMessage('bot', 'Sorry, could not connect to the server. Please check your connection.');
        } finally {
             sendButton.disabled = false; // Re-enable send button
        }
    });

     // Optional UX improvement: Enable/disable button based on input content
     messageInput.addEventListener('input', () => {
         sendButton.disabled = messageInput.value.trim() === '';
     });

     // Focus the input field when the page loads
     messageInput.focus();
});