// Enhanced notification handler for real-time topbar notifications

// Global function to update topbar notifications in real-time
function updateTopbarNotifications() {
    fetch('/chat/notifications/get-all')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateNotificationBadges(data.notifications);
                updateNotificationDropdown(data.notifications);
            }
        })
        .catch(error => {
            console.error('Error updating topbar notifications:', error);
        });
}

// Function to update notification badges
function updateNotificationBadges(notifications) {
    const countBadge = document.getElementById('topbar-notification-count');
    const textBadge = document.getElementById('topbar-notification-badge');
    
    if (notifications.total_count > 0) {
        // Show and update count badge
        if (countBadge) {
            countBadge.textContent = notifications.total_count;
            countBadge.style.display = 'inline';
        }
        
        // Show and update text badge
        if (textBadge) {
            textBadge.textContent = `${notifications.total_count} New`;
            textBadge.style.display = 'inline';
        }
        
        // Update tab counts
        updateTabCounts(notifications);
    } else {
        // Hide badges when no notifications
        if (countBadge) {
            countBadge.style.display = 'none';
        }
        if (textBadge) {
            textBadge.style.display = 'none';
        }
    }
}

// Function to update tab counts
function updateTabCounts(notifications) {
    // Update "All" tab count
    const allTab = document.querySelector('a[href="#all-noti-tab"]');
    if (allTab) {
        allTab.textContent = `All (${notifications.total_count})`;
    }
    
    // Update "Messages" tab count
    const messagesTab = document.querySelector('a[href="#messages-tab"]');
    if (messagesTab) {
        messagesTab.textContent = `Messages (${notifications.chat_count})`;
    }
    
    // Update "Alerts" tab count
    const alertsTab = document.querySelector('a[href="#alerts-tab"]');
    if (alertsTab) {
        const alertsCount = notifications.questionnaire_count + notifications.safety_count;
        alertsTab.textContent = `Alerts (${alertsCount})`;
    }
}

// Function to update notification dropdown content
function updateNotificationDropdown(notifications) {
    const allTab = document.getElementById('all-noti-tab');
    const messagesTab = document.getElementById('messages-tab');
    
    if (!allTab || !messagesTab) return;
    
    // Update "All" tab content
    if (notifications.total_count > 0) {
        let allContent = '';
        
        // Add chat notifications
        notifications.chat_notifications.forEach(notification => {
            allContent += `
                <div class="text-reset notification-item d-block dropdown-item position-relative chat-notification-item" 
                     data-message-id="${notification.id}" 
                     data-thread-id="${notification.thread_id}"
                     data-module="${notification.module_name}"
                     data-entry-id="${notification.entry_id}">
                    <div class="d-flex">
                        <div class="avatar-xs me-3">
                            <span class="avatar-title bg-soft-primary text-primary rounded-circle fs-16">
                                <i class="ri-message-2-line"></i>
                            </span>
                        </div>
                        <div class="flex-1">
                            <a href="javascript:void(0)" class="stretched-link chat-notification-link">
                                <h6 class="mt-0 mb-2 lh-base">New message from <b>${notification.sender_name}</b></h6>
                                <p class="mb-1 text-muted">${notification.message}</p>
                                <p class="mb-0 fs-11 fw-medium text-uppercase text-muted">
                                    <span><i class="mdi mdi-clock-outline"></i> ${formatDateTime(notification.timestamp)}</span>
                                    <span class="ms-2"><i class="ri-file-text-line"></i> ${notification.docserial}</span>
                                </p>
                            </a>
                        </div>
                    </div>
                </div>
            `;
        });
        
        // Add questionnaire notifications
        if (notifications.questionnaire_reviews.length > 0) {
            allContent += `
                <div class="text-reset notification-item d-block dropdown-item">
                    <div class="d-flex">
                        <div class="flex-shrink-0 avatar-xs me-3">
                            <span class="avatar-title bg-soft-warning text-warning rounded-circle fs-16">
                                <i class="ri-questionnaire-line"></i>
                            </span>
                        </div>
                        <div class="flex-1">
                            <a href="/main/list_responses" class="stretched-link">
                                <h6 class="mt-0 mb-2 fs-13 lh-base">You have <b class="text-danger">${notifications.questionnaire_reviews.length}</b> RIR responses pending review</h6>
                            </a>
                            <p class="mb-0 fs-11 fw-medium text-uppercase text-muted">
                                <span><i class="mdi mdi-clock-outline"></i> Review Required</span>
                            </p>
                        </div>
                    </div>
                </div>
            `;
        }
        
        // Add safety notifications
        if (notifications.monthly_safety_reviews.length > 0) {
            allContent += `
                <div class="text-reset notification-item d-block dropdown-item">
                    <div class="d-flex">
                        <div class="flex-shrink-0 avatar-xs me-3">
                            <span class="avatar-title bg-soft-info text-info rounded-circle fs-16">
                                <i class="ri-shield-check-line"></i>
                            </span>
                        </div>
                        <div class="flex-1">
                            <a href="/main/monthly_safety_reviews" class="stretched-link">
                                <h6 class="mt-0 mb-2 fs-13 lh-base">You have <b class="text-danger">${notifications.monthly_safety_reviews.length}</b> monthly safety reviews pending</h6>
                            </a>
                            <p class="mb-0 fs-11 fw-medium text-uppercase text-muted">
                                <span><i class="mdi mdi-clock-outline"></i> Review Required</span>
                            </p>
                        </div>
                    </div>
                </div>
            `;
        }
        
        allTab.innerHTML = `<div data-simplebar style="max-height: 300px;" class="pe-2">${allContent}</div>`;
    } else {
        // Show "no notifications" message
        allTab.innerHTML = `
            <div class="w-100 text-center py-4">
                <div class="avatar-md mx-auto mb-4">
                    <div class="avatar-title bg-light text-secondary rounded-circle fs-24">
                        <i class="ri-notification-off-line"></i>
                    </div>
                </div>
                <h5 class="mb-1">No Notifications</h5>
                <p class="text-muted">You're all caught up! No pending notifications.</p>
            </div>
        `;
    }
    
    // Update "Messages" tab content
    if (notifications.chat_count > 0) {
        let messagesContent = '';
        notifications.chat_notifications.forEach(notification => {
            messagesContent += `
                <div class="text-reset notification-item d-block dropdown-item position-relative chat-notification-item" 
                     data-message-id="${notification.id}" 
                     data-thread-id="${notification.thread_id}"
                     data-module="${notification.module_name}"
                     data-entry-id="${notification.entry_id}">
                    <div class="d-flex">
                        <div class="avatar-xs me-3">
                            <span class="avatar-title bg-soft-primary text-primary rounded-circle fs-16">
                                <i class="ri-message-2-line"></i>
                            </span>
                        </div>
                        <div class="flex-1">
                            <a href="javascript:void(0)" class="stretched-link chat-notification-link">
                                <h6 class="mt-0 mb-2 lh-base">New message from <b>${notification.sender_name}</b></h6>
                                <p class="mb-1 text-muted">${notification.message}</p>
                                <p class="mb-0 fs-11 fw-medium text-uppercase text-muted">
                                    <span><i class="mdi mdi-clock-outline"></i> ${formatDateTime(notification.timestamp)}</span>
                                    <span class="ms-2"><i class="ri-file-text-line"></i> ${notification.docserial}</span>
                                </p>
                            </a>
                        </div>
                    </div>
                </div>
            `;
        });
        messagesTab.innerHTML = `<div data-simplebar style="max-height: 300px;" class="pe-2">${messagesContent}</div>`;
    } else {
        messagesTab.innerHTML = `
            <div class="w-100 text-center py-4">
                <div class="avatar-md mx-auto mb-4">
                    <div class="avatar-title bg-light text-secondary rounded-circle fs-24">
                        <i class="ri-message-2-line"></i>
                    </div>
                </div>
                <h5 class="mb-1">No Messages</h5>
                <p class="text-muted">No new chat messages.</p>
            </div>
        `;
    }
}

// Helper function to format date/time
function formatDateTime(timestamp) {
    if (!timestamp) return 'N/A';
    const date = new Date(timestamp);
    return date.toLocaleString('en-US', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Function to update notification count (for when items are removed)
function updateNotificationCount() {
    const countBadge = document.getElementById('topbar-notification-count');
    const textBadge = document.getElementById('topbar-notification-badge');
    
    // Count remaining notification items
    const remainingNotifications = document.querySelectorAll('.notification-item').length;
    
    if (remainingNotifications > 0) {
        if (countBadge) {
            countBadge.textContent = remainingNotifications;
        }
        if (textBadge) {
            textBadge.textContent = `${remainingNotifications} New`;
        }
    } else {
        // Hide notification badges if no notifications
        if (countBadge) {
            countBadge.style.display = 'none';
        }
        if (textBadge) {
            textBadge.style.display = 'none';
        }
        
        // Show "no notifications" message
        const allTab = document.getElementById('all-noti-tab');
        if (allTab) {
            allTab.innerHTML = `
                <div class="w-100 text-center py-4">
                    <div class="avatar-md mx-auto mb-4">
                        <div class="avatar-title bg-light text-secondary rounded-circle fs-24">
                            <i class="ri-notification-off-line"></i>
                        </div>
                    </div>
                    <h5 class="mb-1">No Notifications</h5>
                    <p class="text-muted">You're all caught up! No pending notifications.</p>
                </div>
            `;
        }
    }
}

// Function to mark a specific chat message as read
function markChatMessageAsRead(messageId, threadId) {
    fetch(`/chat/message/${messageId}/mark-read`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content || ''
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log('Message marked as read');
        }
    })
    .catch(error => {
        console.error('Error marking message as read:', error);
    });
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    
    // Handle chat notification clicks
    document.addEventListener('click', function(e) {
        if (e.target.closest('.chat-notification-link')) {
            e.preventDefault();
            
            const notificationItem = e.target.closest('.chat-notification-item');
            const moduleName = notificationItem.dataset.module;
            const entryId = notificationItem.dataset.entryId;
            const messageId = notificationItem.dataset.messageId;
            const threadId = notificationItem.dataset.threadId;
            
            // Mark this specific message as read
            markChatMessageAsRead(messageId, threadId);
            
            // Open the chat modal
            openChat(moduleName, entryId);
            
            // Remove the notification item from the dropdown
            notificationItem.remove();
            
            // Update notification count
            updateNotificationCount();
        }
    });
    
    // Initialize real-time updates
    updateTopbarNotifications();
    
    // Check for new notifications every 15 seconds (same as chat badges)
    setInterval(updateTopbarNotifications, 15000);
    
    // Check when page becomes visible
    document.addEventListener('visibilitychange', function() {
        if (!document.hidden) {
            updateTopbarNotifications();
        }
    });
    
    // Check when window gains focus
    window.addEventListener('focus', function() {
        updateTopbarNotifications();
    });
});

// Make the function globally available
window.updateTopbarNotifications = updateTopbarNotifications;
