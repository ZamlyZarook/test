// Document Management JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Get entry ID from global variable first, then try other methods
    const entryId = extractEntryId();
    
    // Initialize document management if entry ID is available
    if (entryId) {
        // Don't load documents via API since they're passed from server
        setupDocumentEventListeners(entryId);
    }
    
    // Enhanced function to extract entry ID
    function extractEntryId() {
        // First check the global variable set in the template
        if (window.currentEntryId) {
            return window.currentEntryId;
        }
        
        // Fallback to hidden fields if global variable is not set
        const shipmentIdField = document.getElementById('shipmentId');
        if (shipmentIdField && shipmentIdField.value) {
            return shipmentIdField.value;
        }
        
        // Last resort, try URL
        const urlMatch = window.location.pathname.match(/\/shipments\/(\d+)/);
        if (urlMatch && urlMatch[1]) {
            return urlMatch[1];
        }
        
        console.error('Could not determine entry ID');
        return null;
    }

    // Upload document function
    // Handle document form submission (both create and update)
    function uploadDocument(event) {
        event.preventDefault();
        
        // Get entry ID
        const entryId = extractEntryId();
        if (!entryId) {
            Swal.fire({
                title: 'Error',
                text: 'Could not determine entry ID. Please reload the page and try again.',
                icon: 'error'
            });
            return;
        }

        const form = event.target;
        const formData = new FormData(form);
        
        // Append entry ID to form data
        formData.append('shipment_id', entryId);
        
        // Check if this is an edit (update) or a new document
        const documentId = document.getElementById('documentId').value;
        
        // Show loading state in the button
        const saveButton = document.getElementById('saveDocument');
        const originalText = saveButton.textContent;
        saveButton.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> ' + 
                             (documentId ? 'Updating...' : 'Uploading...');
        saveButton.disabled = true;
        
        // For new documents, submit normally and let server handle redirect
        if (!documentId) {
            // Change form action and method for normal submission
            form.action = `/masters/entries/${entryId}/documents`;
            form.method = 'POST';
            
            // Add a hidden field to indicate we want to return to attachments tab
            const hiddenTab = document.createElement('input');
            hiddenTab.type = 'hidden';
            hiddenTab.name = 'redirect_tab';
            hiddenTab.value = 'attachments';
            form.appendChild(hiddenTab);
            
            // Submit the form normally
            form.submit();
            return;
        }
        
        // For updates, we still need to use fetch because browsers don't support PUT in forms
        const fetchOptions = {
            method: 'PUT',
            body: formData,
            headers: {
                'X-HTTP-Method-Override': 'PUT'
            }
        };
        
        fetch(`/masters/entries/${entryId}/documents/${documentId}`, fetchOptions)
        .then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.message || `HTTP error! status: ${response.status}`);
                }).catch(e => {
                    throw new Error(`HTTP error! status: ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                // Close modal and show success message
                const modal = bootstrap.Modal.getInstance(document.getElementById('documentModal'));
                if (modal) {
                    modal.hide();
                }
                
                Swal.fire({
                    title: 'Success',
                    text: 'Document updated successfully',
                    icon: 'success',
                    timer: 1500,
                    showConfirmButton: false
                }).then(() => {
                    // Reload the current page
                    window.location.reload();
                });
            } else {
                throw new Error(data.message || 'Failed to process document');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            Swal.fire({
                title: 'Error',
                text: error.message || 'An error occurred while processing the document',
                icon: 'error'
            });
        })
        .finally(() => {
            // Reset button state
            saveButton.innerHTML = originalText;
            saveButton.disabled = false;
        });
    }

    // Set up document event listeners
    function setupDocumentEventListeners(entryId) {
        // Document form submission - this is the ONLY place we add the submit listener
        const documentForm = document.getElementById('documentForm');
        if (documentForm) {
            // Remove any existing listeners first to prevent duplicates
            const newUploadDocument = uploadDocument.bind(this); // Bind to preserve context
            documentForm.addEventListener('submit', newUploadDocument);
        }
        
        // Document file input change
        const documentFileInput = document.getElementById('documentFile');
        if (documentFileInput) {
            documentFileInput.addEventListener('change', handleDocumentFileSelect);
        }
        
        // Document upload button (opens the modal)
        const uploadDocumentBtn = document.querySelector('[data-bs-target="#documentModal"]');
        if (uploadDocumentBtn) {
            uploadDocumentBtn.addEventListener('click', function() {
                resetDocumentForm();
                
                // Set modal title and button text
                const modalTitle = document.getElementById('documentModalLabel');
                const submitButton = document.getElementById('saveDocument');
                
                if (modalTitle) modalTitle.textContent = 'Upload Document';
                if (submitButton) submitButton.textContent = 'Upload Document';
                
                // Hide edit-only fields
                const editOnlyFields = document.querySelectorAll('.edit-only-fields');
                editOnlyFields.forEach(field => field.classList.add('d-none'));
                
                // Make file input required in add mode
                if (documentFileInput) documentFileInput.setAttribute('required', 'required');
            });
        }
        
        // Delete document button in modal
        const deleteDocumentBtn = document.getElementById('deleteDocument');
        if (deleteDocumentBtn) {
            deleteDocumentBtn.addEventListener('click', function() {
                const documentId = this.getAttribute('data-document-id');
                deleteDocument(entryId, documentId);
            });
        }
        
        // Add event delegation for document actions
        const documentsTable = document.getElementById('documentsTable');
        if (documentsTable) {
            documentsTable.addEventListener('click', function(event) {
                // Edit document
                if (event.target.closest('.edit-document')) {
                    event.preventDefault();
                    const btn = event.target.closest('.edit-document');
                    const documentId = btn.getAttribute('data-id');
                    editDocument(entryId, documentId);
                }
                
                // Delete document
                if (event.target.closest('.delete-document')) {
                    event.preventDefault();
                    const btn = event.target.closest('.delete-document');
                    const documentId = btn.getAttribute('data-id');
                    confirmDeleteDocument(documentId);
                }
            });
        }
    }
    
    // Load documents for a given entry (no longer needed since data comes from server)
    function loadDocuments(entryId) {
        // This function is no longer needed since documents are passed directly from the server
        // The document list is already rendered in the HTML template
        console.log('loadDocuments called but not needed - documents already loaded from server');
    }
    
    // Handle document file selection
    function handleDocumentFileSelect(event) {
        const file = event.target.files[0];
        const filePreview = document.getElementById('filePreview');
        
        if (!file || !filePreview) {
            if (filePreview) filePreview.classList.add('d-none');
            return;
        }
        
        // Show file preview
        filePreview.classList.remove('d-none');
        
        // Get file icon based on type
        const fileIcon = document.getElementById('fileIcon');
        if (fileIcon) {
            fileIcon.className = getFileIconClass(file.name) + ' fs-24 me-2';
        }
        
        // Set file details
        const fileName = document.getElementById('fileName');
        const fileSize = document.getElementById('fileSize');
        
        if (fileName) fileName.textContent = file.name;
        if (fileSize) fileSize.textContent = formatFileSize(file.size);
    }
    
    // Edit document
    function editDocument(entryId, documentId) {
        // Reset form
        resetDocumentForm();
        
        // Set document ID in form
        document.getElementById('documentId').value = documentId;
        
        // Show loading in modal
        const modal = new bootstrap.Modal(document.getElementById('documentModal'));
        modal.show();
        
        // Show loading state
        const modalTitle = document.getElementById('documentModalLabel');
        const submitButton = document.getElementById('saveDocument');
        
        if (modalTitle) modalTitle.textContent = 'Loading...';
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Loading...';
        }
        
        // Fetch document details
        fetch(`/masters/entries/${entryId}/documents/${documentId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success && data.document) {
                    const doc = data.document;
                    
                    // Fill form fields
                    document.getElementById('documentType').value = doc.document_type;
                    document.getElementById('documentDescription').value = doc.description || '';
                    document.getElementById('isConfidential').checked = doc.is_confidential;
                    
                    // Set upload info for edit-only fields
                    document.getElementById('uploadedBy').value = doc.uploaded_by_name || 'System';
                    
                    // Format date
                    if (doc.created_at) {
                        const uploadDate = new Date(doc.created_at);
                        document.getElementById('uploadDate').value = uploadDate.toLocaleDateString('en-US', {
                            day: '2-digit',
                            month: 'short',
                            year: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit'
                        });
                    }
                    
                    // Set modal title and button text
                    if (modalTitle) modalTitle.textContent = 'Edit Document';
                    if (submitButton) {
                        submitButton.textContent = 'Update Document';
                        submitButton.disabled = false;
                    }
                    
                    // Show edit-only fields
                    const editOnlyFields = document.querySelectorAll('.edit-only-fields');
                    editOnlyFields.forEach(field => field.classList.remove('d-none'));
                    
                    // Make file input optional in edit mode
                    const fileInput = document.getElementById('documentFile');
                    if (fileInput) fileInput.removeAttribute('required');
                } else {
                    throw new Error(data.message || 'Failed to load document details');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                Swal.fire({
                    title: 'Error',
                    text: 'Error loading document details',
                    icon: 'error'
                });
                
                // Close modal on error
                modal.hide();
            });
    }

    // Confirm document deletion
    function confirmDeleteDocument(documentId) {
        // Set document ID in delete button
        const deleteButton = document.getElementById('deleteDocument');
        if (deleteButton) {
            deleteButton.setAttribute('data-document-id', documentId);
            
            // Show delete confirmation modal
            const modal = new bootstrap.Modal(document.getElementById('deleteDocumentModal'));
            modal.show();
        }
    }
    
    // Delete document function
    function deleteDocument(entryId, documentId) {
        // Show loading state in delete button
        const deleteButton = document.getElementById('deleteDocument');
        const originalText = deleteButton.textContent;
        deleteButton.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Deleting...';
        deleteButton.disabled = true;
        
        // Just submit a form directly instead of using fetch
        // This will let the server handle the redirect properly
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/masters/entries/${entryId}/document/${documentId}/delete`;
        form.style.display = 'none';
        
        // Add CSRF token if needed (check if your app uses CSRF protection)
        // const csrfToken = document.querySelector('meta[name=csrf-token]');
        // if (csrfToken) {
        //     const csrfInput = document.createElement('input');
        //     csrfInput.type = 'hidden';
        //     csrfInput.name = 'csrf_token';
        //     csrfInput.value = csrfToken.content;
        //     form.appendChild(csrfInput);
        // }
        
        document.body.appendChild(form);
        
        // Close the modal first
        const modal = bootstrap.Modal.getInstance(document.getElementById('deleteDocumentModal'));
        if (modal) {
            modal.hide();
        }
        
        // Show a brief success message and then submit
        Swal.fire({
            title: 'Deleting...',
            text: 'Please wait while we delete the document',
            icon: 'info',
            timer: 1000,
            showConfirmButton: false,
            timerProgressBar: true
        }).then(() => {
            // Submit the form - this will cause a page redirect
            form.submit();
        });
    }
    
    // Reset document form
    function resetDocumentForm() {
        const form = document.getElementById('documentForm');
        if (!form) return;
        
        form.reset();
        document.getElementById('documentId').value = '';
        
        const filePreview = document.getElementById('filePreview');
        if (filePreview) filePreview.classList.add('d-none');
        
        // Reset edit-only fields
        const editOnlyFields = document.querySelectorAll('.edit-only-fields');
        editOnlyFields.forEach(field => field.classList.add('d-none'));
        
        // Reset file input
        const documentFileInput = document.getElementById('documentFile');
        if (documentFileInput) documentFileInput.value = '';
        
        // Reset validation states
        const invalidFields = form.querySelectorAll('.is-invalid');
        invalidFields.forEach(field => field.classList.remove('is-invalid'));
    }
    
    // Helper function to get file icon class based on file extension
    function getFileIconClass(filename) {
        if (!filename) return 'ri-file-text-line';
        
        const ext = filename.split('.').pop().toLowerCase();
        
        if (['jpg', 'jpeg', 'png', 'gif', 'svg'].includes(ext)) {
            return 'ri-image-line text-success';
        } else if (ext === 'pdf') {
            return 'ri-file-pdf-line text-danger';
        } else if (['doc', 'docx'].includes(ext)) {
            return 'ri-file-word-line text-info';
        } else if (['xls', 'xlsx', 'csv'].includes(ext)) {
            return 'ri-file-excel-line text-success';
        } else if (['ppt', 'pptx'].includes(ext)) {
            return 'ri-file-ppt-line text-warning';
        } else if (['zip', 'rar', 'tar', 'gz', '7z'].includes(ext)) {
            return 'ri-file-zip-line text-primary';
        } else if (['txt', 'log'].includes(ext)) {
            return 'ri-file-text-line text-secondary';
        } else {
            return 'ri-file-line text-muted';
        }
    }
    
    // Helper function to format file size
    function formatFileSize(bytes) {
        if (!bytes || isNaN(bytes)) return '0 Bytes';
        
        const units = ['Bytes', 'KB', 'MB', 'GB'];
        let i = 0;
        
        while (bytes >= 1024 && i < units.length - 1) {
            bytes /= 1024;
            i++;
        }
        
        return bytes.toFixed(2) + ' ' + units[i];
    }
    
    // Helper function to format date
    function formatDate(dateString) {
        if (!dateString) return 'N/A';
        
        const date = new Date(dateString);
        
        if (isNaN(date.getTime())) return dateString;
        
        const day = date.getDate();
        const month = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][date.getMonth()];
        const year = date.getFullYear();
        
        return `${day} ${month}, ${year}`;
    }
});