// static/js/script.js

document.addEventListener('DOMContentLoaded', () => {
    // --- Main Chat Elements ---
    const messageForm = document.getElementById('message-form');
    const messageInput = document.getElementById('message-input');
    const chatWindow = document.getElementById('chat-window');
    const sendButton = document.getElementById('send-button');
    const typingIndicator = document.getElementById('typing-indicator');
    const modelSelect = document.getElementById('model-select');
    const currentChatTitleElement = document.getElementById('chat-title-text'); // Target the span inside h1

    // --- Sidebar Elements ---
    const newChatButton = document.getElementById('new-chat-button');
    const chatList = document.getElementById('chat-list');

    // --- API Key Modal Elements ---
    const saveKeysButton = document.getElementById('save-keys-button');
    const openaiKeyInput = document.getElementById('openai-key-input');
    const googleKeyInput = document.getElementById('google-key-input');
    const keyStatusDiv = document.getElementById('key-status');
    const modalKeyStatusDiv = document.getElementById('modal-key-status');
    const apiKeysModalElement = document.getElementById('apiKeysModal');
    const apiKeysModal = apiKeysModalElement ? new bootstrap.Modal(apiKeysModalElement) : null;

    // --- State ---
    // Initialize currentChatId by checking if an item has the 'active' class from server render
    let currentChatId = document.querySelector('#chat-list .list-group-item.active')?.dataset.chatId || null;
    console.log("Initial currentChatId:", currentChatId);

    // --- Utility Functions ---

    // Scroll chat window to bottom
    function scrollToBottom() {
        requestAnimationFrame(() => {
             // Add a small delay to ensure content is rendered before scrolling
             setTimeout(() => { chatWindow.scrollTop = chatWindow.scrollHeight; }, 50);
        });
    }

    // --- Append Message with Code Block Handling ---
    function appendMessage(sender, text, isError = false) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', sender === 'user' ? 'user-message' : 'bot-message');
        const isLikelyHtml = /[<>&]/.test(text) && !text.includes('```'); // Basic check

        if (isError) {
            messageDiv.classList.add('error-message');
            // Use innerHTML carefully ONLY for the icon + safe text
            const icon = '<i class="fas fa-exclamation-triangle me-2"></i>';
            const messageTextSpan = document.createElement('span');
            // Ensure error text itself is treated as text content
            messageTextSpan.textContent = text.startsWith("ERROR:") ? text.substring(6).trim() : text;
            messageDiv.innerHTML = icon; // Add icon first
            messageDiv.appendChild(messageTextSpan); // Append text safely
        } else if (sender === 'bot' && text.includes('```')) {
            // Handle potential code blocks using manual replacement + escaping
            messageDiv.innerHTML = ''; // Clear potential textContent set elsewhere
            const codeBlockRegex = /```(\w*)\n([\s\S]*?)\n```/g;
            let lastIndex = 0;
            let match;

            while ((match = codeBlockRegex.exec(text)) !== null) {
                // 1. Append text BEFORE the code block (as a text node for safety)
                const textBefore = text.substring(lastIndex, match.index);
                if (textBefore) {
                    messageDiv.appendChild(document.createTextNode(textBefore));
                }

                // 2. Create and append the code block (<pre><code>)
                const language = match[1] || 'plaintext'; // Default language if not specified
                const codeContent = match[2];

                const pre = document.createElement('pre');
                const code = document.createElement('code');
                // Add class for potential syntax highlighting libraries (like highlight.js)
                const safeLanguage = language.replace(/[^a-zA-Z0-9_-]/g, ''); // Basic sanitization
                code.className = `language-${safeLanguage}`;
                code.textContent = codeContent; // Set code content as text (this is safe)
                pre.appendChild(code);
                messageDiv.appendChild(pre);

                lastIndex = codeBlockRegex.lastIndex;
            }

            // 3. Append any remaining text AFTER the last code block (as text node)
            const textAfter = text.substring(lastIndex);
            if (textAfter) {
                 messageDiv.appendChild(document.createTextNode(textAfter));
            }
        // } else if (sender === 'bot' && isLikelyHtml) {
            // Experimental: If it looks like HTML and isn't a code block, try rendering it.
            // This is potentially UNSAFE if the bot response isn't trusted or sanitized server-side.
            // Use with caution. Consider using a sanitizer library (like DOMPurify) here.
            // console.warn("Rendering potentially unsafe HTML from bot message:", text.substring(0, 50) + "...");
            // messageDiv.innerHTML = text; // UNSAFE WITHOUT SANITIZATION
            // For now, default to textContent for safety:
            // messageDiv.textContent = text;
        } else {
            // Default: Set as plain text (handles user messages and simple bot messages)
            messageDiv.textContent = text;
        }

        chatWindow.appendChild(messageDiv);
        scrollToBottom(); // Scroll after adding ANY message
    }


    // Show/hide the typing indicator
    function showTypingIndicator(show) {
        typingIndicator.style.display = show ? 'flex' : 'none';
         if (show) {
            scrollToBottom(); // Ensure indicator is visible if shown
         }
    }

    // Update active state in the sidebar
    function setActiveChatItem(chatId) {
        document.querySelectorAll('#chat-list .list-group-item').forEach(item => {
            item.classList.remove('active');
        });
        if (chatId) {
            const activeItem = chatList.querySelector(`.list-group-item[data-chat-id="${chatId}"]`);
            if (activeItem) {
                activeItem.classList.add('active');
            } else {
                 console.warn(`setActiveChatItem: Could not find list item for chatId ${chatId}`);
            }
        }
         currentChatId = chatId;
         console.log("Set active chat ID:", currentChatId);
         // Enable message input only if a chat is active OR if we are in the 'new chat' state (null chatId)
         // The newChatButton handler will explicitly enable it for null chatId.
         // This function primarily disables it if NO chat is selected (e.g. after delete).
         messageInput.disabled = currentChatId === null && !document.querySelector('#chat-list .list-group-item.active');

         // Send button depends on input being enabled AND having text
         sendButton.disabled = messageInput.disabled || messageInput.value.trim() === '';
    }

    // Helper Function: Toggle Edit Mode for a List Item
    function toggleEditMode(listItem, isEditing) {
        const titleSpan = listItem.querySelector('.chat-title-text');
        const titleInput = listItem.querySelector('.chat-title-input');
        const viewIcons = listItem.querySelector('.action-icons-view');
        const editIcons = listItem.querySelector('.action-icons-edit');
        const mainClickArea = listItem.querySelector('.chat-item-main');

        if (!titleSpan || !titleInput || !viewIcons || !editIcons || !mainClickArea) {
            console.error("Could not find necessary elements within list item for toggling edit mode.");
            return;
        }

        if (isEditing) {
            titleSpan.classList.add('d-none');
            viewIcons.classList.add('d-none');
            titleInput.classList.remove('d-none');
            editIcons.classList.remove('d-none');
            mainClickArea.removeAttribute('role');
            mainClickArea.style.cursor = 'default';

            const originalTitle = titleInput.dataset.originalTitle || titleSpan.textContent;
            titleInput.value = originalTitle; // Use full original title for editing
            titleInput.dataset.originalTitle = originalTitle; // Ensure stored

            titleInput.focus();
            titleInput.select();
        } else {
            titleInput.classList.add('d-none');
            editIcons.classList.add('d-none');
            titleSpan.classList.remove('d-none');
            viewIcons.classList.remove('d-none');
            mainClickArea.setAttribute('role', 'button');
            mainClickArea.style.cursor = 'pointer';

            // Update span text from input's *current value* (which was saved or cancelled to original)
            // Truncate for display only
            const currentTitle = titleInput.value;
            titleSpan.textContent = currentTitle.substring(0, 25) + (currentTitle.length > 25 ? '...' : '');
            // Keep full title in data-original-title and input value
            titleInput.dataset.originalTitle = currentTitle;
        }
    }

     // Add a new chat item to the top of the sidebar list
     function addChatToList(chatId, title, isActive = false) {
         const listItem = document.createElement('li');
         listItem.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
         listItem.dataset.chatId = chatId;

         // Use textContent for safety when inserting the title initially
         const truncatedTitle = title.substring(0, 25) + (title.length > 25 ? '...' : '');
         const titleTextNode = document.createTextNode(truncatedTitle);
         const titleSpan = document.createElement('span');
         titleSpan.className = 'chat-title-text';
         titleSpan.appendChild(titleTextNode);

         // Store the full title safely in the input and its data attribute
         const safeFullTitle = title; // Title from backend is already escaped Markupsafe

         // Sanitize chatId for attribute selectors if needed, though UUIDs are generally safe
         const safeChatId = chatId.replace(/[^a-zA-Z0-9_-]/g, '');

         listItem.innerHTML = `
            <div class="chat-item-main flex-grow-1 me-2" role="button" style="cursor: pointer;">
                ${titleSpan.outerHTML}
                <input type="text" class="form-control form-control-sm chat-title-input d-none" value="${safeFullTitle.replace(/"/g, '"')}" data-original-title="${safeFullTitle.replace(/"/g, '"')}">
            </div>
            <div class="chat-item-actions flex-shrink-0">
                 <span class="action-icons-view">
                     <i class="fas fa-pencil-alt text-secondary action-icon edit-chat-button" role="button" title="Edit title" data-chat-id="${safeChatId}"></i>
                     <i class="fas fa-trash-alt text-danger action-icon delete-chat-button ms-2" role="button" title="Delete chat" data-chat-id="${safeChatId}"></i>
                 </span>
                 <span class="action-icons-edit d-none">
                    <i class="fas fa-check text-success action-icon save-title-button" role="button" title="Save title" data-chat-id="${safeChatId}"></i>
                    <i class="fas fa-times text-secondary action-icon cancel-edit-button ms-2" role="button" title="Cancel edit" data-chat-id="${safeChatId}"></i>
                 </span>
            </div>
         `;

         // Remove existing active class before adding new item
         const currentlyActive = chatList.querySelector('.list-group-item.active');
         if (currentlyActive) {
              currentlyActive.classList.remove('active');
         }

         chatList.insertBefore(listItem, chatList.firstChild); // Add to top

         if (isActive) {
             listItem.classList.add('active');
         }
     }

    // Clear chat window and maybe show initial message
    function clearChatWindow(showInitialMessage = true, messageText = null, isError = false) {
         chatWindow.innerHTML = ''; // Clear messages
         if (showInitialMessage) {
             const initialHtmlContent = messageText ||
                'Hello! Start a new chat or select one. <br><small class="text-muted">Remember to <button type="button" class="btn btn-link p-0 align-baseline" data-bs-toggle="modal" data-bs-target="#apiKeysModal">add your API keys</button> if needed.</small>';

             const messageDiv = document.createElement('div');
             messageDiv.classList.add('message', 'bot-message');
             if (isError) {
                  messageDiv.classList.add('error-message');
                   // Prepend icon for error message
                  messageDiv.innerHTML = '<i class="fas fa-exclamation-triangle me-2"></i> ';
                  // Append text safely
                  messageDiv.appendChild(document.createTextNode(messageText));
             } else {
                 // Use innerHTML only for this controlled initial message which contains safe HTML
                 messageDiv.innerHTML = initialHtmlContent;
             }
             chatWindow.appendChild(messageDiv);
         }
         scrollToBottom(); // Scroll down after clearing/adding initial
    }

    // Render chat history from data
    function renderHistory(history) {
         clearChatWindow(false); // Clear before rendering
         if (history && history.length > 0) {
             history.forEach(message => {
                 // Skip system messages in rendering
                 if (message.role === 'user') {
                     appendMessage(message.role, message.content);
                 } else if (message.role === 'assistant') {
                     // Use the is_error flag from the backend if provided
                     // Default to false if missing
                     const isError = message.is_error || false;
                     appendMessage(message.role, message.content, isError);
                 }
             });
         }
          // If history only contains system message or is empty/null after filtering, show prompt
         const nonSystemMessages = history ? history.filter(m => m.role !== 'system') : [];
         if (!nonSystemMessages || nonSystemMessages.length === 0) {
            // Don't use appendMessage here, as it calls scroll again.
            // Modify clearChatWindow or add a separate function if needed.
            // For now, let's assume loading an empty chat means showing the default "Ask me anything".
            const promptDiv = document.createElement('div');
            promptDiv.classList.add('message', 'bot-message');
            promptDiv.textContent = 'Chat loaded. Ask me anything.';
            chatWindow.appendChild(promptDiv);

         }
         scrollToBottom(); // Scroll once after rendering all messages
    }


    // --- Event Handlers ---

    // 1. Start New Chat
    newChatButton.addEventListener('click', async () => {
        console.log("New chat button clicked");
         // Cancel any ongoing title edit
         const currentlyEditing = chatList.querySelector('.list-group-item .action-icons-edit:not(.d-none)');
         if (currentlyEditing) {
             const editingItem = currentlyEditing.closest('.list-group-item');
             if (editingItem) {
                 const titleInput = editingItem.querySelector('.chat-title-input');
                 if (titleInput) {
                     titleInput.value = titleInput.dataset.originalTitle || ''; // Restore original value
                     toggleEditMode(editingItem, false);
                     console.log("Cancelled edit on item due to starting new chat.");
                 }
             }
         }

        try {
            const response = await fetch('/new_chat', { method: 'POST' });
            if (!response.ok) throw new Error(`Server error: ${response.status}`);
            const data = await response.json();

            // Reset UI for new chat
            clearChatWindow(true); // Show standard initial message
            setActiveChatItem(null); // No chat selected initially (this disables input temporarily)
            currentChatTitleElement.textContent = "New Chat";
            document.title = "New Chat - Multi-AI Chatbot";

            // --- FIX: Explicitly enable input for a new chat session ---
            messageInput.disabled = false;
            // Also ensure send button state is correct (disabled if input is empty)
            sendButton.disabled = messageInput.value.trim() === '';
            // --- END FIX ---

            messageInput.focus();


        } catch (error) {
            console.error('Error starting new chat:', error);
            // Use clearChatWindow to display the error
            clearChatWindow(true, `Error starting new chat: ${error.message}`, true);
        }
    });

    // 2. Handle Clicks within the Chat List (Load/Edit/Delete/Save/Cancel)
    chatList.addEventListener('click', async (event) => {
        const target = event.target;
        const listItem = target.closest('.list-group-item');
        if (!listItem) return;

        const chatId = listItem.dataset.chatId;
        if (!chatId) {
             console.error("Clicked list item missing data-chat-id");
             return;
        }

        // --- Action Icon Clicks ---
        if (target.classList.contains('edit-chat-button')) {
             event.stopPropagation(); // Prevent chat load on icon click
             console.log("Edit button clicked for chat:", chatId);
             const otherEditing = chatList.querySelector('.list-group-item .action-icons-edit:not(.d-none)');
             // If another item is being edited, cancel its edit mode
             if (otherEditing && otherEditing.closest('.list-group-item') !== listItem) {
                  const otherItem = otherEditing.closest('.list-group-item');
                  const otherInput = otherItem.querySelector('.chat-title-input');
                  otherInput.value = otherInput.dataset.originalTitle || '';
                  toggleEditMode(otherItem, false);
             }
             // Toggle edit mode for the clicked item
             toggleEditMode(listItem, true);
        }
        else if (target.classList.contains('cancel-edit-button')) {
            event.stopPropagation(); // Prevent chat load
            console.log("Cancel edit button clicked for chat:", chatId);
            const titleInput = listItem.querySelector('.chat-title-input');
            titleInput.value = titleInput.dataset.originalTitle || ''; // Restore original
            toggleEditMode(listItem, false);
        }
         else if (target.classList.contains('save-title-button')) {
            event.stopPropagation(); // Prevent chat load
            console.log("Save title button clicked for chat:", chatId);
            const titleInput = listItem.querySelector('.chat-title-input');
            const newTitle = titleInput.value.trim();
            const originalTitle = titleInput.dataset.originalTitle || '';

            if (!newTitle) { alert("Title cannot be empty."); titleInput.focus(); return; }
            const MAX_TITLE_LENGTH = 100;
            if (newTitle.length > MAX_TITLE_LENGTH) { alert(`Title cannot exceed ${MAX_TITLE_LENGTH} characters.`); titleInput.focus(); return; }
            if (newTitle === originalTitle) { toggleEditMode(listItem, false); return; } // No change

            // --- Call Backend ---
            try {
                 target.classList.add('fa-spinner', 'fa-spin'); target.classList.remove('fa-check'); target.style.pointerEvents = 'none';
                 const response = await fetch(`/update_title/${chatId}`, {
                     method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ new_title: newTitle }),
                 });
                 const data = await response.json(); // Always try to parse JSON first
                 if (!response.ok) {
                    // Throw an error with the message from JSON if available
                    throw new Error(data.error || `Server error ${response.status}`);
                 }

                 // Update UI (use title from response - it's escaped server-side)
                 const titleSpan = listItem.querySelector('.chat-title-text');
                 const updatedTitle = data.new_title || newTitle; // Use response title if provided
                 // Update input first (stores full title)
                 titleInput.value = updatedTitle;
                 titleInput.dataset.originalTitle = updatedTitle; // Update original title store
                 // Then update span (handles truncation)
                 titleSpan.textContent = updatedTitle.substring(0, 25) + (updatedTitle.length > 25 ? '...' : '');


                 toggleEditMode(listItem, false); // Switch back to view mode

                 if (currentChatId === chatId) {
                      currentChatTitleElement.textContent = updatedTitle; // Update header
                      document.title = `${updatedTitle} - Multi-AI Chatbot`;
                 }
                  console.log("Title updated successfully for:", chatId);

            } catch (error) {
                 console.error('Error updating title:', error);
                 alert(`Failed to update title: ${error.message}`);
                 // Optionally revert input visually, but keep data-original-title as is was before save attempt
                 // titleInput.value = originalTitle;
                 toggleEditMode(listItem, false); // Switch back to view mode even on error
            } finally {
                 // Ensure icon returns to normal state
                 target.classList.remove('fa-spinner', 'fa-spin'); target.classList.add('fa-check'); target.style.pointerEvents = 'auto';
            }
        }
        else if (target.classList.contains('delete-chat-button')) {
            event.stopPropagation(); // Prevent chat load
            console.log("Delete button clicked for chat:", chatId);
            // Get the full title from the input's data attribute for the confirmation dialog
            const titleToDelete = listItem.querySelector('.chat-title-input')?.dataset.originalTitle || `Chat ID ${chatId}`;

            if (window.confirm(`Are you sure you want to delete the chat "${titleToDelete}"? This cannot be undone.`)) {
                 try {
                     target.classList.add('fa-spinner', 'fa-spin'); target.classList.remove('fa-trash-alt'); target.style.pointerEvents = 'none';
                     const response = await fetch(`/delete_chat/${chatId}`, { method: 'DELETE' });

                     // --- FIX: Check response before parsing JSON ---
                     if (!response.ok) {
                          // Try to parse JSON error, otherwise use status text
                          let errorMsg = `Server error: ${response.status} ${response.statusText}`;
                          try {
                              const errorData = await response.json();
                              errorMsg = errorData.error || errorMsg;
                          } catch (jsonError) {
                              // If response is not JSON (like the HTML error page), log the text
                              const responseText = await response.text();
                              console.error("Non-JSON response from delete:", responseText);
                              // The alert below will show the generic server error
                          }
                          throw new Error(errorMsg);
                     }

                     // Only parse JSON if response is OK
                     const data = await response.json();
                     console.log("Chat delete response:", data);

                     const wasActive = listItem.classList.contains('active');
                     listItem.remove();

                     // Check if any chats remain
                     const remainingChats = chatList.querySelectorAll('.list-group-item').length > 0;

                     if (wasActive || currentChatId === chatId) { // Reset if active chat was deleted
                         console.log("Deleted chat was active, resetting view.");
                         currentChatId = null; // Update state variable
                         clearChatWindow(true); // Show initial message
                         currentChatTitleElement.textContent = "New Chat";
                         document.title = "New Chat - Multi-AI Chatbot";
                         setActiveChatItem(null); // Update button states etc. -> This will disable input
                          // Explicitly re-enable input if NO chats remain (effectively forces new chat state)
                         if (!remainingChats) {
                             messageInput.disabled = false;
                             sendButton.disabled = messageInput.value.trim() === '';
                         }
                         messageInput.focus();
                     }
                 } catch (error) {
                      console.error('Error deleting chat:', error);
                      alert(`Failed to delete chat: ${error.message}`);
                      // Reset icon state on failure
                      target.classList.remove('fa-spinner', 'fa-spin'); target.classList.add('fa-trash-alt'); target.style.pointerEvents = 'auto';
                 }
            }
        }
        // --- Main Item Click (Load Chat) ---
        // Ensure the click is on the main area and NOT inside the input field when it's visible
        else if (target.closest('.chat-item-main') && !target.classList.contains('chat-title-input')) {
            const chatIdToLoad = chatId;
            if (chatIdToLoad === currentChatId) return; // Don't reload if already active

            // Cancel any ongoing edit first
            const currentlyEditing = chatList.querySelector('.list-group-item .action-icons-edit:not(.d-none)');
             if (currentlyEditing) {
                 const editingItem = currentlyEditing.closest('.list-group-item');
                 if (editingItem && editingItem !== listItem) { // Ensure it's a different item
                     const titleInput = editingItem.querySelector('.chat-title-input');
                     if (titleInput) {
                         titleInput.value = titleInput.dataset.originalTitle || '';
                         toggleEditMode(editingItem, false);
                         console.log("Cancelled edit on previous item due to loading another chat.");
                     }
                 }
             }

            console.log("Load chat clicked:", chatIdToLoad);
            listItem.style.cursor = 'wait'; document.body.style.cursor = 'wait'; // Indicate loading

            try {
                const response = await fetch(`/load_chat/${chatIdToLoad}`);
                 if (!response.ok) {
                      const errorData = await response.json().catch(() => ({ error: `Server error: ${response.status}` }));
                     throw new Error(errorData.error || `Failed to load chat.`);
                 }
                 const chatData = await response.json();

                 // Update UI
                 renderHistory(chatData.history); // Use the render function
                 setActiveChatItem(chatIdToLoad); // Update active state/buttons
                 const safeTitle = chatData.title || "Chat"; // Use escaped title from backend
                 currentChatTitleElement.textContent = safeTitle;
                 document.title = `${safeTitle} - Multi-AI Chatbot`;
                 messageInput.disabled = false; // Ensure input is enabled after loading
                 sendButton.disabled = messageInput.value.trim() === ''; // Update send button state
                 messageInput.focus();

            } catch (error) {
                console.error('Error loading chat:', error);
                clearChatWindow(true, `Error loading chat: ${error.message}`, true); // Show error in chat window
                 // Keep input disabled if load fails? Or enable for new chat? Reset state:
                 setActiveChatItem(null);
                 currentChatTitleElement.textContent = "Error Loading";
                 document.title = "Error - Multi-AI Chatbot";
                 messageInput.disabled = true; // Disable input on error
                 sendButton.disabled = true;
            } finally {
                 listItem.style.cursor = ''; document.body.style.cursor = ''; // Reset cursor
            }
        }
    });


    // 3. Send Message (Form Submission)
    messageForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const userMessage = messageInput.value.trim();
        // Check if input is disabled OR empty
        if (messageInput.disabled || !userMessage) return;

        const selectedModel = modelSelect.value;
        // Use the JS state variable `currentChatId` directly
        const isCurrentlyNewChat = (currentChatId === null);

        appendMessage('user', userMessage);
        // scrollToBottom() is called within appendMessage now

        const messageToSend = userMessage; // Keep original case etc.
        messageInput.value = '';
        sendButton.disabled = true; // Disable send until response or new input
        messageInput.disabled = true; // Disable input while waiting
        showTypingIndicator(true);

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: messageToSend,
                    model_choice: selectedModel
                    // Backend uses session['current_chat_id']
                }),
            });

            showTypingIndicator(false);
            const data = await response.json(); // Assume JSON response for errors too based on backend logic

            // Use backend's 'is_error' flag and message content directly
            const responseText = data.response || data.error || "An unexpected empty response occurred.";
            const isErrorFromServer = data.is_error || !response.ok; // Fallback check on response status

            if (responseText) {
                 appendMessage('bot', responseText, isErrorFromServer);
            } else {
                 console.warn("Received response but no message content or error:", data);
                 // Avoid showing an empty bubble
            }

            // Handle new chat creation feedback only if a new chat was actually created
            if (data.new_chat_info && isCurrentlyNewChat) {
                 console.log("New chat created by backend:", data.new_chat_info);
                 addChatToList(data.new_chat_info.id, data.new_chat_info.title, true); // Add and make active
                 setActiveChatItem(data.new_chat_info.id); // Update state, title, buttons
                 currentChatTitleElement.textContent = data.new_chat_info.title; // Update header
                 document.title = `${data.new_chat_info.title} - Multi-AI Chatbot`;
            } else if (isCurrentlyNewChat && !data.new_chat_info && !isErrorFromServer) {
                 // If it was supposed to be a new chat but backend didn't confirm (and no error occurred)
                 // This might indicate a logic issue. Maybe reload the chat list?
                 console.warn("Sent message in 'new chat' mode, but backend did not return new_chat_info and no error reported. State might be inconsistent.");
                 // Force reload might be too disruptive, just log for now.
            }

        } catch (error) {
            showTypingIndicator(false);
            console.error('Network or fetch error:', error);
            appendMessage('bot', `Network Error: Could not reach the server. ${error.message}`, true);
        } finally {
            // Re-enable input unless no chat is selected (e.g., after delete)
            messageInput.disabled = (currentChatId === null && !document.querySelector('#chat-list .list-group-item.active'));
            // Re-evaluate send button state
            sendButton.disabled = messageInput.disabled || messageInput.value.trim() === '';
            if (!messageInput.disabled) {
                 messageInput.focus();
            }
            scrollToBottom(); // Ensure view is at the bottom after response/error
        }
    });

    // 4. Save API Keys (Modal)
    if (saveKeysButton && apiKeysModal) {
         saveKeysButton.addEventListener('click', async () => {
             const openaiKey = openaiKeyInput.value; // Keep empty strings if cleared
             const googleKey = googleKeyInput.value; // Keep empty strings if cleared
             modalKeyStatusDiv.textContent = 'Saving...';
             modalKeyStatusDiv.className = 'mt-3 small text-muted';

             try {
                 const response = await fetch('/save_api_keys', {
                     method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
                         // Send trimmed keys or empty strings if inputs are empty
                         openai_key: openaiKey.trim(),
                         google_key: googleKey.trim()
                     }),
                 });
                 const data = await response.json();
                 if (!response.ok) throw new Error(data.error || `HTTP error ${response.status}`);

                 modalKeyStatusDiv.textContent = data.message || 'Keys updated!';
                 modalKeyStatusDiv.className = 'mt-3 small text-success';
                 keyStatusDiv.textContent = 'API Keys updated in session.'; // Status below input
                 keyStatusDiv.className = 'p-1 text-center small text-success';
                 setTimeout(() => keyStatusDiv.textContent = '', 5000); // Clear status after delay
                 // Optionally close modal automatically on success
                 setTimeout(() => {
                      if (apiKeysModal) apiKeysModal.hide();
                 }, 1500);

             } catch (error) {
                 console.error('Error saving API keys:', error);
                 modalKeyStatusDiv.textContent = `Error: ${error.message}`;
                 modalKeyStatusDiv.className = 'mt-3 small text-danger';
                 keyStatusDiv.textContent = 'Failed to update API keys.'; // Status below input
                 keyStatusDiv.className = 'p-1 text-center small text-danger';
             }
         });
     }
     if (apiKeysModalElement) {
         apiKeysModalElement.addEventListener('hidden.bs.modal', () => {
             // Reset modal status when closed
             modalKeyStatusDiv.textContent = '';
             modalKeyStatusDiv.className = 'mt-3 small';
             // Do NOT clear inputs when modal closes, user might want to reopen and see them.
         });
         apiKeysModalElement.addEventListener('show.bs.modal', () => {
             // Optional: Fetch current keys from session to pre-fill? Requires backend endpoint.
             // For now, just clear status and ensure inputs are ready.
             modalKeyStatusDiv.textContent = '';
             modalKeyStatusDiv.className = 'mt-3 small';
             // Fetching keys to display them is complex and might expose keys unintentionally.
             // Best practice is to keep them write-only in the modal.
         });
     }


    // 5. Enable/disable send button based on input
    messageInput.addEventListener('input', () => {
        // Enable only if input has text AND input is not disabled (i.e., a chat is active/loaded or new chat)
        sendButton.disabled = messageInput.disabled || messageInput.value.trim() === '';
    });

     // Handle Enter key in title input to trigger save
     chatList.addEventListener('keypress', (event) => {
         if (event.key === 'Enter' && event.target.classList.contains('chat-title-input')) {
             event.preventDefault(); // Prevent form submission if inside one
             const listItem = event.target.closest('.list-group-item');
             const saveButton = listItem?.querySelector('.save-title-button');
             if (saveButton) {
                  saveButton.click();
                  // Optionally blur the input after saving with Enter
                  event.target.blur();
             }
         }
     });

     // Handle Escape key in title input to trigger cancel
      chatList.addEventListener('keyup', (event) => {
         if (event.key === 'Escape' && event.target.classList.contains('chat-title-input')) {
             const listItem = event.target.closest('.list-group-item');
             const cancelButton = listItem?.querySelector('.cancel-edit-button');
             if (cancelButton) {
                 cancelButton.click();
                 // Optionally blur the input after cancelling with Escape
                 event.target.blur();
             }
         }
     });


    // --- Initial Setup ---
    function initializeChatView() {
        // Find the active item from the server render (if any)
        const activeItem = chatList.querySelector('.list-group-item.active');
        currentChatId = activeItem?.dataset.chatId || null;

        if (currentChatId) {
             // If a chat is marked active, load its history via the standard click handler
             console.log("Initial load: Found active chat ID", currentChatId, " - simulating load.");
             // Simulate a click on the main area to load it using the existing handler
             // Ensure the main click area exists before trying to click it
             const mainClickArea = activeItem?.querySelector('.chat-item-main');
             if (mainClickArea) {
                 // Use setTimeout to ensure event listeners are attached
                 setTimeout(() => mainClickArea.click(), 0);
             } else {
                 console.error("Initial load: Active item found but '.chat-item-main' is missing. Cannot load history automatically.");
                 clearChatWindow(true, "Error: Could not load initially selected chat.", true);
                 setActiveChatItem(null); // Reset state
             }
         } else {
             // No chat is active, show the initial welcome message and enable input
             console.log("Initial load: No active chat found. Displaying welcome message.");
             clearChatWindow(true);
             setActiveChatItem(null); // Set internal state, deselect visually
             messageInput.disabled = false; // Explicitly enable input for the "New Chat" state
             sendButton.disabled = messageInput.value.trim() === ''; // Set button state
         }
        // Focus input only if it's not disabled
        if (!messageInput.disabled) {
             messageInput.focus();
        }
    }

    // Add tooltip to potentially truncated sidebar items
     chatList.addEventListener('mouseover', (event) => {
        const mainArea = event.target.closest('.chat-item-main');
        if (mainArea) {
            const listItem = mainArea.closest('.list-group-item');
            const titleSpan = mainArea.querySelector('.chat-title-text');
            const titleInput = mainArea.querySelector('.chat-title-input'); // Check within mainArea

             if (titleSpan && !titleSpan.classList.contains('d-none') && titleSpan.offsetWidth < titleSpan.scrollWidth) {
                  // Only show tooltip if text is actually overflowing/truncated
                  const fullTitle = titleInput?.dataset.originalTitle || titleSpan.textContent.trim(); // Use full title
                  // Use mainArea for tooltip to avoid interfering with icons
                  mainArea.title = fullTitle;
             } else {
                  mainArea.removeAttribute('title'); // Remove if not truncated or if input is shown
             }
        }
     });
     chatList.addEventListener('mouseout', (event) => {
         const mainArea = event.target.closest('.chat-item-main');
         if (mainArea) {
             mainArea.removeAttribute('title'); // Remove tooltip on mouseout
         }
     });


    // --- Run Initialization ---
    initializeChatView();

});