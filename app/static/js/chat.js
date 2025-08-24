// Update chat.js to ensure it uses consistent routes

// Chat functionality
let mediaRecorder = null;
let audioChunks = [];
let recordingTimer = null;
let currentThreadId = null;
let currentModule = null;
let currentReferenceId = null;
let currentUserId = null;
let currentUserName = null;
let messagePollInterval = null;
let unreadMessages = {};

function openChat(moduleName, referenceId) {
    // Set current context
    currentModule = moduleName;
    currentReferenceId = referenceId;

    // Clear reply if it was active
    cancelReply();
    
    // Reset notification badge
    const notificationBadge = document.querySelector(`[data-entry-id="${referenceId}"] .chat-notification-badge`);
    if (notificationBadge) {
        notificationBadge.classList.add('d-none');
        notificationBadge.textContent = '0';
    }

    // Show chat modal
    const chatModal = new bootstrap.Modal(document.getElementById('chatModal'));
    chatModal.show();

    // Initialize chat thread
    initializeChat(moduleName, referenceId);
    
    // Mark messages as read
    markMessagesAsRead(moduleName, referenceId);
}

function markMessagesAsRead(moduleName, referenceId) {
    fetch(`/chat/mark-messages-read/${moduleName}/${referenceId}`, { 
        method: 'POST',
        headers: {
            'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content || '',
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log('Messages marked as read');
        }
    })
    .catch(error => {
        console.error('Error marking messages as read:', error);
    });
}

// Initialize chat for a specific module and reference
function initializeChat(moduleName, referenceId) {
    console.log('Initializing chat:', { moduleName, referenceId });
    
    // Reset current context
    currentModule = moduleName;
    currentReferenceId = referenceId;

    // Get or create chat thread
    fetch(`/chat/thread/${moduleName}/${referenceId}`)
        .then(response => {
            console.log('Thread response status:', response.status);
            if (!response.ok) {
                throw new Error('Failed to initialize chat');
            }
            return response.json();
        })
        .then(data => {
            console.log('Thread data received:', data);
            currentThreadId = data.thread_id;
            document.getElementById('threadId').value = currentThreadId;
            
            // Load messages after getting thread
            loadMessages();
            
            // Start polling for new messages
            startMessagePolling();
        })
        .catch(error => {
            console.error('Error initializing chat:', error);
            showErrorMessage('Failed to initialize chat');
        });
}

function startMessagePolling() {
    // Clear any existing interval first
    if (messagePollInterval) {
        clearInterval(messagePollInterval);
    }

    messagePollInterval = setInterval(() => {
        if (currentThreadId) {
            checkAndLoadNewMessages();
        }
    }, 5000); // Check every 5 seconds
}

function checkAndLoadNewMessages() {
    // Only fetch messages if the chat modal is open
    const chatModal = document.getElementById('chatModal');
    if (!chatModal || !chatModal.classList.contains('show')) {
        return;
    }

    fetch(`/chat/check-new-messages/${currentModule}/${currentReferenceId}`)
        .then(response => response.json())
        .then(data => {
            if (data.new_messages_exist) {
                loadMessages(); // Only load messages if new ones exist
                
                // Auto-mark as read since the chat is open
                markMessagesAsRead(currentModule, currentReferenceId);
            }
        })
        .catch(error => {
            console.error('Error checking for new messages:', error);
        });
}

// Check for new messages across all chat buttons
function checkNewMessages() {
    const chatButtons = document.querySelectorAll('[data-entry-id]');
    
    chatButtons.forEach(button => {
        const entryId = button.getAttribute('data-entry-id');
        const moduleName = button.getAttribute('data-module-name');
        
        if (!entryId || !moduleName) return;
        
        const badge = button.querySelector('.chat-notification-badge');
        
        if (badge) {
            fetch(`/chat/check-new-messages/${moduleName}/${entryId}`)
                .then(res => res.json())
                .then(data => {
                    if (data.success && data.unread_count > 0) {
                        // Show the actual count of unread messages
                        badge.textContent = data.unread_count > 9 ? '9+' : data.unread_count;
                        badge.classList.remove('d-none');
                    } else {
                        badge.classList.add('d-none');
                    }
                })
                .catch(error => {
                    console.error('Error checking new messages:', error);
                });
        }
    });
    
    // Also update topbar notifications
    if (typeof window.updateTopbarNotifications === 'function') {
        window.updateTopbarNotifications();
    }
}

// Stop polling when modal is closed
document.getElementById('chatModal')?.addEventListener('hidden.bs.modal', () => {
    if (messagePollInterval) {
        clearInterval(messagePollInterval);
        messagePollInterval = null;
    }
});

// Load messages for current thread
function loadMessages() {
    if (!currentThreadId) {
        console.error('No thread ID available');
        return;
    }

    const messageContainer = document.getElementById('messageContainer');
    if (!messageContainer) {
        console.error('Message container not found');
        return;
    }

    messageContainer.innerHTML = `
        <div class="text-center my-3">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading messages...</span>
            </div>
        </div>
    `;

    fetch(`/chat/messages/${currentThreadId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to fetch messages');
            }
            return response.json();
        })
        .then(data => {
            messageContainer.innerHTML = '';

            if (data.messages && data.messages.length > 0) {
                data.messages.forEach(message => {
                    // Get current user ID from meta tag if not already set
                    if (!currentUserId) {
                        const userIdMeta = document.querySelector('meta[name="user-id"]');
                        if (userIdMeta) {
                            currentUserId = parseInt(userIdMeta.content);
                        }
                    }
                    
                    const messageData = {
                        ...message,
                        is_sender: parseInt(message.sender.id) === currentUserId
                    };
                    const messageHTML = formatMessage(messageData);
                    messageContainer.insertAdjacentHTML('beforeend', messageHTML);
                });

                scrollToBottom();
            } else {
                messageContainer.innerHTML = `
                    <div class="text-center text-muted my-3">
                        <p>No messages yet. Start a conversation!</p>
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Error loading messages:', error);
            messageContainer.innerHTML = `
                <div class="text-center text-danger my-3">
                    <p>Unable to load messages. Please try again later.</p>
                </div>
            `;
        });
} 

// Handle file selection
function handleFileSelect(input) {
    const files = Array.from(input.files);
    const previewContainer = document.getElementById('filePreviewContainer');
    const filePreview = document.getElementById('filePreview');

    if (!previewContainer || !filePreview) return;

    previewContainer.innerHTML = '';
    if (files.length > 0) {
        filePreview.classList.remove('d-none');
        files.forEach(file => {
            const preview = document.createElement('div');
            preview.className = 'file-preview-item d-flex align-items-center gap-2 bg-light p-2 rounded';
            preview.innerHTML = `
                <i class="ri-file-line me-1"></i>
                <span>${file.name}</span>
                <button type="button" class="btn-close" onclick="removeFile('${file.name}')"></button>
            `;
            previewContainer.appendChild(preview);
        });
    } else {
        filePreview.classList.add('d-none');
    }
}

// Remove file from preview
function removeFile(fileName) {
    const input = document.getElementById('fileInput');
    if (!input || !input.files || input.files.length === 0) return;
    
    const dt = new DataTransfer();

    Array.from(input.files)
        .filter(file => file.name !== fileName)
        .forEach(file => dt.items.add(file));

    input.files = dt.files;
    handleFileSelect(input);
}

function clearFilePreview() {
    const filePreview = document.getElementById('filePreview');
    const filePreviewContainer = document.getElementById('filePreviewContainer');
    const fileInput = document.getElementById('fileInput');

    if (filePreview) {
        filePreview.classList.add('d-none');
    }

    if (filePreviewContainer) {
        filePreviewContainer.innerHTML = '';
    }

    if (fileInput) {
        fileInput.value = ''; // Clear the file input
    }
}

// Handle reply to message
function replyToMessage(messageId, messageText) {
    document.getElementById('parentMessageId').value = messageId;
    
    const replyPreview = document.getElementById('replyPreview');
    const replyPreviewText = document.getElementById('replyPreviewText');
    
    if (replyPreview && replyPreviewText) {
        replyPreviewText.textContent = messageText;
        replyPreview.classList.remove('d-none');
        
        // Focus on the message input
        const messageInput = document.getElementById('messageInput');
        if (messageInput) messageInput.focus();
    }
}

// Cancel reply
function cancelReply() {
    const parentMessageId = document.getElementById('parentMessageId');
    const replyPreview = document.getElementById('replyPreview');
    
    if (parentMessageId) parentMessageId.value = '';
    if (replyPreview) replyPreview.classList.add('d-none');
}

// Format message for display
function formatMessage(msg) {
    // Check if message has attachments and properly handle if it doesn't
    const hasAttachments = msg.attachments && msg.attachments.length > 0;
    
    // Determine role-based styling
    const isCustomer = msg.sender && msg.sender.role === 'customer';
    const isCompanyUser = msg.sender && ['user', 'base_user'].includes(msg.sender.role);
    
    // Set role-specific colors and classes
    let roleClass = '';
    let roleLabel = '';
    let roleColor = '';
    
    if (isCustomer) {
        roleClass = 'role-customer';
        roleLabel = 'Customer';
        roleColor = '#e3f2fd'; // Light blue background
    } else if (isCompanyUser) {
        roleClass = 'role-company';
        roleLabel = msg.sender.role === 'user' ? 'CHA Admin' : 'CHA User';
        roleColor = '#f3e5f5'; // Light purple background
    }
    
    // Generate attachment HTML if attachments exist
    let attachmentsHtml = '';
    if (hasAttachments) {
        attachmentsHtml = `
            <div class="mt-1">
                ${msg.attachments.map(att => {
                    // Make sure attachment and its properties exist before trying to access them
                    if (!att) return '';
                    
                    if (att.file_type === 'voice' || att.file_type === 'audio') {
                        return `
                            <div class="audio-attachment">
                                <audio controls class="w-100">
                                    <source src="/chat/attachment/${att.file_path}" type="audio/mpeg">
                                    Your browser does not support audio playback.
                                </audio>
                            </div>
                        `;
                    } else if (att.file_type === 'image') {
                        return `
                            <div class="image-attachment">
                                <a href="/chat/attachment/${att.file_path}" target="_blank">
                                    <img src="/chat/attachment/${att.file_path}" 
                                         class="img-thumbnail" style="max-width: 200px; max-height: 200px;">
                                </a>
                            </div>
                        `;
                    } else {
                        return `
                            <div class="file-attachment">
                                <a href="/chat/attachment/${att.file_path}" target="_blank" 
                                   class="btn btn-sm ${msg.is_sender ? 'btn-outline-primary' : 'btn-outline-info'}">
                                    <i class="ri-file-line me-1"></i>${att.file_name || 'Attachment'}
                                </a>
                            </div>
                        `;
                    }
                }).join('')}
            </div>
        `;
    }
    
    // Generate reply HTML if needed
    let replyHtml = '';
    if (msg.parent_message_id && msg.parent_message) {
        // Get parent message details
        const parentMsg = msg.parent_message;
        const parentSenderName = parentMsg.sender && parentMsg.sender.name ? parentMsg.sender.name : 
                                parentMsg.sender && parentMsg.sender.username ? parentMsg.sender.username : 'Unknown User';
        
        // Truncate parent message if too long
        const parentMessageText = parentMsg.message || '';
        const truncatedText = parentMessageText.length > 100 ? 
            parentMessageText.substring(0, 100) + '...' : parentMessageText;
        
        replyHtml = `
            <div class="reply-preview mb-1 p-2 rounded bg-light ${msg.is_sender ? 'text-primary' : 'text-info'}">
                <div class="text-muted small mb-1">
                    <i class="ri-reply-line me-1"></i>Replying to ${parentSenderName}
                </div>
                <div class="parent-message-text small">${truncatedText}</div>
            </div>
        `;
    }

    // Get sender name
    const senderName = msg.sender && msg.sender.name ? msg.sender.name : 
                      msg.sender && msg.sender.username ? msg.sender.username : 'Unknown User';

    return `
        <div class="chat-message d-flex ${msg.is_sender ? 'justify-content-end' : 'justify-content-start'} mb-2">
            <div class="message-content p-2 rounded bg-white border ${msg.is_sender ? 'border-primary text-primary' : 'border-info text-info'}" style="max-width: 70%;">
                ${replyHtml}
                
                <!-- Sender Name and Role Label -->
                <div class="message-header mb-1">
                    <span class="sender-name fw-bold">${senderName}</span>
                    ${roleLabel ? `<span class="role-label ${roleClass} ms-2">${roleLabel}</span>` : ''}
                </div>
                
                <div class="message-text">${msg.message || ''}</div>
                ${attachmentsHtml}
                <div class="message-time text-muted mt-1 d-flex justify-content-between align-items-center">
                    <span class="small">${new Date(msg.created_at).toLocaleString()}</span>
                    <button class="btn btn-sm ${msg.is_sender ? 'btn-outline-primary' : 'btn-outline-info'}" onclick="replyToMessage(${msg.id}, '${msg.message ? msg.message.replace(/'/g, "\\'") : ''}')">
                        <i class="ri-reply-line"></i>
                    </button>
                </div>
            </div>
        </div>
    `;
}

// Scroll chat to bottom
function scrollToBottom() {
    const messageContainer = document.getElementById('messageContainer');
    if (messageContainer) {
        messageContainer.scrollTop = messageContainer.scrollHeight;
    }
}

function showErrorMessage(message) {
    if (typeof Swal !== 'undefined') {
        Swal.fire({
            icon: 'error',
            title: 'Chat Error',
            text: message,
            toast: true,
            position: 'top-end',
            showConfirmButton: false,
            timer: 3000
        });
    } else {
        console.error('Chat Error:', message);
        alert('Chat Error: ' + message);
    }
}


async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = (event) => {
            audioChunks.push(event.data);
        };

        mediaRecorder.onstop = () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/mp3' });
            const file = new File([audioBlob], 'voice-message.mp3', { type: 'audio/mp3' });

            const dt = new DataTransfer();
            dt.items.add(file);
            document.getElementById('fileInput').files = dt.files;
            handleFileSelect(document.getElementById('fileInput'));
        };

        mediaRecorder.start();
        document.getElementById('voiceRecording').classList.remove('d-none');

        let seconds = 0;
        recordingTimer = setInterval(() => {
            seconds++;
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = seconds % 60;
            document.getElementById('recordingTime').textContent =
                `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;

            document.querySelector('#voiceRecording .progress-bar').style.width =
                `${Math.min((seconds / 300) * 100, 100)}%`; // Max 5 minutes
        }, 1000);
    } catch (err) {
        console.error('Error accessing microphone:', err);
        alert('Could not access microphone');
    }
}

// Stop voice recording
function stopRecording() {
    if (mediaRecorder) {
        mediaRecorder.stop();
        mediaRecorder.stream.getTracks().forEach(track => track.stop());
        clearInterval(recordingTimer);
        document.getElementById('voiceRecording').classList.add('d-none');
    }
}


// Initialize event listeners when DOM is fully loaded
document.addEventListener('DOMContentLoaded', () => {
    // Get user info from meta tags
    const userIdMeta = document.querySelector('meta[name="user-id"]');
    const userNameMeta = document.querySelector('meta[name="user-name"]');
    
    if (userIdMeta && userNameMeta) {
        currentUserId = parseInt(userIdMeta.content);
        currentUserName = userNameMeta.content;
    } else {
        console.warn('User meta tags not found. Chat functionality may be limited.');
    }
    
    // Set up message form submit handler
    const messageForm = document.getElementById('messageForm');
    if (messageForm) {
        messageForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const messageInput = document.getElementById('messageInput');
            const fileInput = document.getElementById('fileInput');
            
            if (!messageInput) return;
            
            const formData = new FormData();
            
            // Add message text
            formData.append('message', messageInput.value || '');
            
            // Add parent message ID if replying
            const parentMessageId = document.getElementById('parentMessageId')?.value;
            if (parentMessageId) {
                formData.append('parent_message_id', parentMessageId);
            }
            
            // Add file if present
            if (fileInput && fileInput.files.length > 0) {
                formData.append('file', fileInput.files[0]);
                console.log("Attaching file:", fileInput.files[0].name);
            }
            
            try {
                const response = await fetch(`/chat/send-message/${currentModule}/${currentReferenceId}`, {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();
                if (data.success) {
                    // Clear form
                    messageForm.reset();
                    
                    // Clear file preview - properly reset the file input and preview container
                    const filePreview = document.getElementById('filePreview');
                    const filePreviewContainer = document.getElementById('filePreviewContainer');
                    
                    if (filePreview) filePreview.classList.add('d-none');
                    if (filePreviewContainer) filePreviewContainer.innerHTML = '';
                    if (fileInput) fileInput.value = '';
                    
                    // Clear reply preview
                    cancelReply();

                    // Refresh chat
                    loadMessages();
                } else {
                    throw new Error(data.error || 'Failed to send message');
                }
            } catch (err) {
                console.error('Error sending message:', err);
                showErrorMessage('Failed to send message');
            }
        });
    }
    
    // Check for new messages on page load and periodically
    checkNewMessages();
    setInterval(checkNewMessages, 15000);

    document.addEventListener('visibilitychange', function() {
        if (!document.hidden) {
            checkNewMessages();
        }
    });
});

window.addEventListener('focus', function() {
    checkNewMessages();
});

// Update role checking if needed
function canAccessChat(userRole) {
    return userRole === 'customer' || ['user', 'base_user'].includes(userRole);
}

// Update UI to show appropriate role labels
function getRoleDisplayName(role) {
    const roleNames = {
        'user': 'CHA Admin',
        'base_user': 'CHA User', 
        'customer': 'Customer'
    };
    return roleNames[role] || role;
}

// Enhanced message rendering with role labels
function renderMessage(message) {
    const isSender = message.sender_id === currentUserId;
    const messageClass = isSender ? 'message-sent' : 'message-received';
    
    // Add role label
    const roleLabel = getRoleDisplayName(message.sender.role);
    const roleClass = message.sender.role === 'customer' ? 'role-customer' : 'role-company';
    
    return `
        <div class="message ${messageClass}">
            <div class="message-header">
                <span class="sender-name">${message.sender.name}</span>
                <span class="role-label ${roleClass}">${roleLabel}</span>
                <span class="timestamp">${formatTime(message.created_at)}</span>
            </div>
            <div class="message-content">${message.message}</div>
        </div>
    `;
}

// Function to fetch parent message content
async function getParentMessageContent(parentMessageId) {
    try {
        const response = await fetch(`/chat/message/${parentMessageId}`);
        if (response.ok) {
            const data = await response.json();
            return data.message;
        }
    } catch (error) {
        console.error('Error fetching parent message:', error);
    }
    return null;
}

// Enhanced formatMessage function with async parent message fetching
async function formatMessageAsync(msg) {
    // Check if message has attachments and properly handle if it doesn't
    const hasAttachments = msg.attachments && msg.attachments.length > 0;
    
    // Determine role-based styling
    const isCustomer = msg.sender && msg.sender.role === 'customer';
    const isCompanyUser = msg.sender && ['user', 'base_user'].includes(msg.sender.role);
    
    // Set role-specific colors and classes
    let roleClass = '';
    let roleLabel = '';
    let roleColor = '';
    
    if (isCustomer) {
        roleClass = 'role-customer';
        roleLabel = 'Customer';
        roleColor = '#e3f2fd'; // Light blue background
    } else if (isCompanyUser) {
        roleClass = 'role-company';
        roleLabel = msg.sender.role === 'user' ? 'CHA Admin' : 'CHA User';
        roleColor = '#f3e5f5'; // Light purple background
    }
    
    // Generate attachment HTML if attachments exist
    let attachmentsHtml = '';
    if (hasAttachments) {
        attachmentsHtml = `
            <div class="mt-1">
                ${msg.attachments.map(att => {
                    // Make sure attachment and its properties exist before trying to access them
                    if (!att) return '';
                    
                    if (att.file_type === 'voice' || att.file_type === 'audio') {
                        return `
                            <div class="audio-attachment">
                                <audio controls class="w-100">
                                    <source src="/chat/attachment/${att.file_path}" type="audio/mpeg">
                                    Your browser does not support audio playback.
                                </audio>
                            </div>
                        `;
                    } else if (att.file_type === 'image') {
                        return `
                            <div class="image-attachment">
                                <a href="/chat/attachment/${att.file_path}" target="_blank">
                                    <img src="/chat/attachment/${att.file_path}" 
                                         class="img-thumbnail" style="max-width: 200px; max-height: 200px;">
                                </a>
                            </div>
                        `;
                    } else {
                        return `
                            <div class="file-attachment">
                                <a href="/chat/attachment/${att.file_path}" target="_blank" 
                                   class="btn btn-sm ${msg.is_sender ? 'btn-outline-primary' : 'btn-outline-info'}">
                                    <i class="ri-file-line me-1"></i>${att.file_name || 'Attachment'}
                                </a>
                            </div>
                        `;
                    }
                }).join('')}
            </div>
        `;
    }
    
    // Generate reply HTML if needed
    let replyHtml = '';
    if (msg.parent_message_id && msg.parent_message) {
        // Get parent message details
        const parentMsg = msg.parent_message;
        const parentSenderName = parentMsg.sender && parentMsg.sender.name ? parentMsg.sender.name : 
                                parentMsg.sender && parentMsg.sender.username ? parentMsg.sender.username : 'Unknown User';
        
        // Truncate parent message if too long
        const parentMessageText = parentMsg.message || '';
        const truncatedText = parentMessageText.length > 100 ? 
            parentMessageText.substring(0, 100) + '...' : parentMessageText;
        
        replyHtml = `
            <div class="reply-preview mb-1 p-2 rounded bg-light ${msg.is_sender ? 'text-primary' : 'text-info'}">
                <div class="text-muted small mb-1">
                    <i class="ri-reply-line me-1"></i>Replying to ${parentSenderName}
                </div>
                <div class="parent-message-text small">${truncatedText}</div>
            </div>
        `;
    }

    // Get sender name
    const senderName = msg.sender && msg.sender.name ? msg.sender.name : 
                      msg.sender && msg.sender.username ? msg.sender.username : 'Unknown User';

    return `
        <div class="chat-message d-flex ${msg.is_sender ? 'justify-content-end' : 'justify-content-start'} mb-2">
            <div class="message-content p-2 rounded bg-white border ${msg.is_sender ? 'border-primary text-primary' : 'border-info text-info'}" style="max-width: 70%;">
                ${replyHtml}
                
                <!-- Sender Name and Role Label -->
                <div class="message-header mb-1">
                    <span class="sender-name fw-bold">${senderName}</span>
                    ${roleLabel ? `<span class="role-label ${roleClass} ms-2">${roleLabel}</span>` : ''}
                </div>
                
                <div class="message-text">${msg.message || ''}</div>
                ${attachmentsHtml}
                <div class="message-time text-muted mt-1 d-flex justify-content-between align-items-center">
                    <span class="small">${new Date(msg.created_at).toLocaleString()}</span>
                    <button class="btn btn-sm ${msg.is_sender ? 'btn-outline-primary' : 'btn-outline-info'}" onclick="replyToMessage(${msg.id}, '${msg.message ? msg.message.replace(/'/g, "\\'") : ''}')">
                        <i class="ri-reply-line"></i>
                    </button>
                </div>
            </div>
        </div>
    `;
}


