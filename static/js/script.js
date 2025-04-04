// static/js/script.js

document.addEventListener('DOMContentLoaded', () => {
    // Main Chat Elements
    const messageForm = document.getElementById('message-form');
    const messageInput = document.getElementById('message-input');
    const chatWindow = document.getElementById('chat-window');
    const sendButton = document.getElementById('send-button');
    const typingIndicator = document.getElementById('typing-indicator');
    const modelSelect = document.getElementById('model-select');
    const currentChatTitle = document.getElementById('chat-title-text');

    // Sidebar Elements
    const newChatButton = document.getElementById('new-chat-button');
    const chatList = document.getElementById('chat-list');

    // API Key Modal Elements (from previous step)
    const saveKeysButton = document.getElementById('save-keys-button');
    const openaiKeyInput = document.getElementById('openai-key-input');
    const googleKeyInput = document.getElementById('google-key-input');
    const keyStatusDiv = document.getElementById('key-status');
    const modalKeyStatusDiv = document.getElementById('modal-key-status');
    const apiKeysModalElement = document.getElementById('apiKeysModal');
    const apiKeysModal = apiKeysModalElement ? new bootstrap.Modal(apiKeysModalElement) : null; // Handle potential absence

    // State variable (though backend session is the source of truth)
    let currentChatId = document.querySelector('#chat-list .list-group-item.active')?.dataset.chatId || null;

    // --- Utility Functions ---

    // Scroll chat window to bottom
    function scrollToBottom() {
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    // Append a message to the chat window
    function appendMessage(sender, text, isError = false, isHtml = false) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', sender === 'user' ? 'user-message' : 'bot-message');
        if (isError) {
            messageDiv.classList.add('error-message'); // Use CSS for styling
            // Add alert icon for clarity
            messageDiv.innerHTML = `<i class="fas fa-exclamation-triangle me-2"></i> ${text}`;
        } else if (isHtml) {
             messageDiv.innerHTML = text; // Allow basic HTML for initial message links
        }
        else {
             messageDiv.textContent = text; // Default safe text rendering
        }

        chatWindow.appendChild(messageDiv);
        scrollToBottom();
    }

    // Show/hide the typing indicator
    function showTypingIndicator(show) {
        typingIndicator.style.display = show ? 'flex' : 'none';
         if (show) {
            scrollToBottom(); // Ensure indicator is visible
         }
    }

    // Update active state in the sidebar
    function setActiveChatItem(chatId) {
        document.querySelectorAll('#chat-list .list-group-item').forEach(item => {
            item.classList.remove('active');
            if (item.dataset.chatId === chatId) {
                item.classList.add('active');
            }
        });
         currentChatId = chatId; // Update local state tracker
         console.log("Set active chat ID:", currentChatId);
    }

     // Add a new chat item to the top of the sidebar list
     function addChatToList(chatId, title, isActive = false) {
         const listItem = document.createElement('li');
         listItem.className = 'list-group-item list-group-item-action';
         listItem.setAttribute('role', 'button');
         listItem.dataset.chatId = chatId;
         listItem.textContent = title.substring(0, 35) + (title.length > 35 ? '...' : ''); // Truncate visually

         if (isActive) {
             listItem.classList.add('active');
         }

         // Insert at the top of the list
         chatList.insertBefore(listItem, chatList.firstChild);

         // Ensure click listener works for this new item (handled by delegation)
     }

    // Clear chat window and show initial message
    function clearChatWindow(showInitialMessage = true) {
         chatWindow.innerHTML = ''; // Clear messages
         if (showInitialMessage) {
             appendMessage('bot',
                'Hello! Ask me anything in this new chat. <br><small class="text-muted">Remember to <button type="button" class="btn btn-link p-0 align-baseline" data-bs-toggle="modal" data-bs-target="#apiKeysModal">add your API keys</button> if needed.</small>',
                false, true); // Allow HTML for the button link
         }
    }


    // --- Event Handlers ---

    // 1. Start New Chat
    newChatButton.addEventListener('click', async () => {
        console.log("New chat button clicked");
        try {
            const response = await fetch('/new_chat', { method: 'POST' });
            if (!response.ok) throw new Error(`Server error: ${response.status}`);

            clearChatWindow();
            setActiveChatItem(null); // Deselect any active item
            currentChatTitle.textContent = "New Chat"; // Update header title
            document.title = "New Chat - Multi-AI Chatbot"; // Update page title
            messageInput.focus();
            sendButton.disabled = true; // Disable send until input

        } catch (error) {
            console.error('Error starting new chat:', error);
            appendMessage('bot', `Error starting new chat: ${error.message}`, true);
        }
    });

    // 2. Load Existing Chat (Using Event Delegation)
    chatList.addEventListener('click', async (event) => {
        const targetItem = event.target.closest('.list-group-item'); // Find the list item clicked
        if (targetItem && targetItem.dataset.chatId) {
            const chatIdToLoad = targetItem.dataset.chatId;
            if (chatIdToLoad === currentChatId) return; // Don't reload if already active

            console.log("Load chat clicked:", chatIdToLoad);
            try {
                const response = await fetch(`/load_chat/${chatIdToLoad}`);
                if (!response.ok) {
                     const errorData = await response.json().catch(() => ({ error: `Server error: ${response.status}` }));
                    throw new Error(errorData.error || `Failed to load chat.`);
                }

                const chatData = await response.json();

                // Update UI
                clearChatWindow(false); // Clear window without initial message
                chatData.history.forEach(message => {
                    // Skip system message display
                    if (message.role === 'user' || message.role === 'assistant') {
                         // Check for potential 'is_error' flag if you add it backend
                         const isError = message.is_error || (message.role === 'assistant' && message.content.startsWith("ERROR:"));
                         appendMessage(message.role, message.content, isError);
                    }
                });
                 if (!chatData.history || chatData.history.length <= 1) { // Add initial prompt if history empty/only system
                     appendMessage('bot', 'Continue this conversation or ask something new.');
                 }

                setActiveChatItem(chatIdToLoad);
                currentChatTitle.textContent = chatData.title; // Update header title
                 document.title = `${chatData.title} - Multi-AI Chatbot`; // Update page title
                messageInput.focus();
                 sendButton.disabled = messageInput.value.trim() === '';


            } catch (error) {
                console.error('Error loading chat:', error);
                appendMessage('bot', `Error loading chat: ${error.message}`, true);
                 // Optionally revert active state if load fails?
            }
        }
    });

    // 3. Send Message (Form Submission)
    messageForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const userMessage = messageInput.value.trim();
        if (!userMessage) return;

        const selectedModel = modelSelect.value;

        appendMessage('user', userMessage);
        const messageToSend = userMessage; // Store before clearing
        messageInput.value = '';
        sendButton.disabled = true; // Disable while processing
        showTypingIndicator(true);
        messageInput.focus();

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: messageToSend, // Use stored message
                    model_choice: selectedModel
                    // No need to send chat_id, backend uses session['current_chat_id']
                }),
            });

            showTypingIndicator(false);
            const data = await response.json(); // Always try to parse JSON first

            if (!response.ok) {
                // Error came from backend API route or middleware
                 const errorMsg = data.error || `Server Error: ${response.statusText} (${response.status})`;
                console.error('Server response error:', response.status, errorMsg);
                appendMessage('bot', `${errorMsg}`, true); // Display specific error
                return;
            }

            // Check if the backend logic itself returned an error *within* a 200 OK response
             if (data.error) {
                 console.error('Backend processing error:', data.error);
                 appendMessage('bot', `${data.error}`, true); // Display specific error
                 // No 'return' here if we want to handle potential `new_chat_info` even on error
             } else if (data.response) {
                  appendMessage('bot', data.response); // Display successful bot response
             } else if (!data.new_chat_info) { // Handle case where response is OK but has no content/error/new_chat
                  console.warn("Received OK response with no data:", data);
                  appendMessage('bot', "Received an empty response from the server.", true);
             }


            // Handle new chat creation feedback
            if (data.new_chat_info) {
                 console.log("New chat created by backend:", data.new_chat_info);
                 // Add to sidebar and make active
                 addChatToList(data.new_chat_info.id, data.new_chat_info.title, true);
                 setActiveChatItem(data.new_chat_info.id);
                 // Update header title
                 currentChatTitle.textContent = data.new_chat_info.title;
                  document.title = `${data.new_chat_info.title} - Multi-AI Chatbot`; // Update page title
            }

        } catch (error) {
            showTypingIndicator(false);
            console.error('Network or fetch error:', error);
            appendMessage('bot', `Network error: Could not connect to the server. (${error.message})`, true);
        } finally {
            sendButton.disabled = messageInput.value.trim() === ''; // Re-enable based on input
            messageInput.focus();
        }
    });

    // 4. Save API Keys (Modal) - Logic mostly unchanged
    if (saveKeysButton) {
         saveKeysButton.addEventListener('click', async () => {
             const openaiKey = openaiKeyInput.value.trim();
             const googleKey = googleKeyInput.value.trim();
             modalKeyStatusDiv.textContent = 'Saving...';
             modalKeyStatusDiv.className = 'mt-3 small text-muted';

             try {
                 const response = await fetch('/save_api_keys', {
                     method: 'POST',
                     headers: { 'Content-Type': 'application/json' },
                     body: JSON.stringify({ openai_key: openaiKey, google_key: googleKey }),
                 });
                 const data = await response.json();

                 if (!response.ok) throw new Error(data.error || `HTTP error ${response.status}`);

                 modalKeyStatusDiv.textContent = data.message || 'Keys updated!';
                 modalKeyStatusDiv.className = 'mt-3 small text-success';
                 keyStatusDiv.textContent = 'API Keys updated in session.'; // Main window feedback
                 keyStatusDiv.className = 'p-2 text-center small text-success';
                 setTimeout(() => keyStatusDiv.textContent = '', 5000);

                 setTimeout(() => {
                     if(apiKeysModal) apiKeysModal.hide();
                     modalKeyStatusDiv.textContent = '';
                     modalKeyStatusDiv.className = 'mt-3 small';
                 }, 1500);

             } catch (error) {
                 console.error('Error saving API keys:', error);
                 modalKeyStatusDiv.textContent = `Error: ${error.message}`;
                 modalKeyStatusDiv.className = 'mt-3 small text-danger';
                 keyStatusDiv.textContent = 'Failed to update API keys.';
                 keyStatusDiv.className = 'p-2 text-center small text-danger';
             }
         });
     }
     if (apiKeysModalElement) {
         apiKeysModalElement.addEventListener('hidden.bs.modal', () => {
             modalKeyStatusDiv.textContent = '';
             modalKeyStatusDiv.className = 'mt-3 small';
         });
     }


    // 5. Enable/disable send button based on input
    messageInput.addEventListener('input', () => {
        sendButton.disabled = messageInput.value.trim() === '';
    });

    // --- Initial Setup ---
    scrollToBottom(); // Scroll down on initial load
    messageInput.focus();
     sendButton.disabled = messageInput.value.trim() === ''; // Initial state

     // Add tooltip to truncated sidebar items (Optional UX enhancement)
     chatList.addEventListener('mouseover', (event) => {
        const targetItem = event.target.closest('.list-group-item');
        if (targetItem && targetItem.scrollWidth > targetItem.clientWidth && !targetItem.title) {
             // Find original title if stored differently, or use textContent as fallback
             targetItem.title = targetItem.textContent.trim(); // Simple tooltip with the text
        }
     });

});