// Updated o_s_container_tab.js to work with existing backend APIs

document.addEventListener('DOMContentLoaded', function() {
    // Initialize containers when tab is clicked
    const containersTabLink = document.querySelector('a[href="#tab-containers"]');
    if (containersTabLink) {
        containersTabLink.addEventListener('click', function() {
            setTimeout(() => {
                if (document.getElementById('containersList').innerHTML.trim() === '') {
                    initializeContainersFromAPI();
                }
            }, 100);
        });
    }
    
    // Also initialize immediately if containers tab is already active
    if (window.location.hash === '#tab-containers' || document.querySelector('#tab-containers.active')) {
        initializeContainersFromAPI();
    }
});

// Global variables
let containersData = [];
let currentWorkflowId = null;

/**
 * Initialize containers using backend APIs
 */
function initializeContainersFromAPI() {
    console.log('Initializing containers with workflow API');
    
    const containersLoading = document.getElementById('containersLoading');
    const containersList = document.getElementById('containersList');
    const noContainersMessage = document.getElementById('noContainersMessage');
    
    // Show loading
    if (containersLoading) {
        containersLoading.style.display = 'block';
    }
    
    // Load containers with workflow data
    fetch(`/masters/api/entry/${window.currentEntryId}/containers-with-workflow`)
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            containersData = data.containers;
            
            if (data.containers && data.containers.length > 0) {
                renderContainersWithProgress(data.containers);
                
                if (containersList) {
                    containersList.style.display = 'block';
                }
                if (noContainersMessage) {
                    noContainersMessage.style.display = 'none';
                }
            } else {
                if (containersList) {
                    containersList.innerHTML = '<div class="alert alert-info">No containers found for this shipment.</div>';
                }
                if (noContainersMessage) {
                    noContainersMessage.style.display = 'block';
                }
            }
        } else {
            throw new Error(data.error || 'Failed to load containers');
        }
    })
    .catch(error => {
        console.error('Error loading containers:', error);
        showAlert('error', `An error occurred while loading containers: ${error.message}`);
    })
    .finally(() => {
        if (containersLoading) {
            containersLoading.style.display = 'none';
        }
    });
}

/**
 * Render containers with progress information
 */
/**
 * Render containers with simplified progress information
 */
function renderContainersWithProgress(containers) {
    const containersList = document.getElementById('containersList');
    
    let html = `
        <div class="workflow-summary mb-3">
            <div class="row">
                <div class="col-md-8">
                    <h5 class="mb-3">Container Workflow Progress</h5>
                </div>
                
            </div>
        </div>
    `;
    
    containers.forEach((container, index) => {
        const progress = container.progress || { completed_steps: 0, total_steps: 0, percentage: 0 };
        const statusColor = progress.percentage === 100 ? 'success' : progress.percentage > 0 ? 'primary' : 'secondary';
        const statusText = progress.percentage === 100 ? 'Complete' : progress.percentage > 0 ? 'In Progress' : 'Not Started';
        
        html += `
            <div class="card shadow-sm mb-4">
                <div class="card-header bg-light">
                    <div class="d-flex justify-content-between align-items-center">
                        <div class="d-flex align-items-center">
                            <i class="ri-container-line me-2 text-primary fs-18"></i>
                            <div>
                                <h6 class="mb-1">${container.container_number}</h6>
                                <small class="text-muted">${container.container_size}ft ${container.container_type}</small>
                                ${container.remarks ? `<small class="text-muted ms-2">- ${container.remarks}</small>` : ''}
                            </div>
                        </div>
                        <div class="d-flex align-items-center gap-3">
                            <div class="workflow-status text-end">
                                <div class="fw-medium text-${statusColor}">
                                    ${progress.completed_steps}/${progress.total_steps} Steps
                                </div>
                                <div class="small text-${statusColor}">${statusText}</div>
                                <div class="progress mt-1" style="width: 120px; height: 6px;">
                                    <div class="progress-bar bg-${statusColor}" 
                                         style="width: ${progress.percentage}%"></div>
                                </div>
                            </div>
                            <button type="button" class="btn btn-sm btn-primary" 
                                    onclick="viewContainerWorkflow(${container.id})" 
                                    data-bs-toggle="tooltip" 
                                    title="Manage Workflow">
                                <i class="ri-list-check-line"></i> Manage Steps
                            </button>
                        </div>
                    </div>
                </div>
                
                <div id="containerWorkflow${container.id}" class="card-body border-top" style="display: none;">
                    <div class="text-center py-3">
                        <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
                        <span class="ms-2">Loading workflow details...</span>
                    </div>
                </div>
            </div>
        `;
    });
    
    containersList.innerHTML = html;
    initializeTooltips();
}


/**
 * View detailed workflow progress for a container
 */
function viewContainerWorkflow(containerId) {
    const workflowDiv = document.getElementById(`containerWorkflow${containerId}`);
    
    if (workflowDiv.style.display === 'none') {
        workflowDiv.style.display = 'block';
        
        // Load detailed progress if not already loaded
        if (workflowDiv.innerHTML.includes('Loading workflow details...')) {
            loadContainerWorkflowDetails(containerId);
        }
    } else {
        workflowDiv.style.display = 'none';
    }
}

/**
 * Load detailed workflow progress for a container
 */
function loadContainerWorkflowDetails(containerId) {
    const workflowDiv = document.getElementById(`containerWorkflow${containerId}`);
    
    fetch(`/masters/api/container/${containerId}/workflow-progress`)
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            renderContainerWorkflowDetails(containerId, data.progress);
        } else {
            workflowDiv.innerHTML = `
                <div class="alert alert-warning">
                    <i class="ri-alert-line me-2"></i>
                    ${data.error || 'No workflow assigned to this container.'}
                </div>
            `;
        }
    })
    .catch(error => {
        console.error('Error loading workflow details:', error);
        workflowDiv.innerHTML = `
            <div class="alert alert-danger">
                <i class="ri-error-warning-line me-2"></i>
                Failed to load workflow details. Please try again.
            </div>
        `;
    });
}

function renderContainerWorkflowDetails(containerId, progress) {
    const workflowDiv = document.getElementById(`containerWorkflow${containerId}`);
    
    let html = `
        <div class="workflow-progress-details">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h6 class="mb-0">Workflow Progress</h6>
                <div class="d-flex align-items-center gap-2">
                    <span class="badge badge-soft-info">Workflow: ${progress.workflow_name}</span>
                    <span class="badge badge-soft-${progress.percentage === 100 ? 'success' : 'warning'}">
                        ${progress.completed_steps}/${progress.total_steps} Steps Complete
                    </span>
                </div>
            </div>
            
            <div class="progress mb-4" style="height: 10px;">
                <div class="progress-bar bg-${progress.percentage === 100 ? 'success' : 'primary'}" 
                     style="width: ${progress.percentage}%"></div>
            </div>
            
            <div class="steps-list">
    `;
    
    progress.steps.forEach((step, index) => {
        const stepStatusColor = step.completed ? 'success' : 'secondary';
        const stepIcon = step.completed ? 'ri-check-circle-fill' : 'ri-circle-line';
        
        // Debug logging
        console.log(`Step ${step.step_number}: has_documents = ${step.has_documents}, mandatory_total = ${step.mandatory_total}`);
        
        html += `
            <div class="step-item mb-3">
                <div class="card shadow-none border ${step.completed ? 'border-success' : ''}">
                    <div class="card-header ${step.completed ? 'bg-soft-success' : 'bg-light'}">
                        <div class="d-flex justify-content-between align-items-center">
                            <div class="d-flex align-items-center">
                                <i class="${stepIcon} text-${stepStatusColor} me-2 fs-18"></i>
                                <div>
                                    <h6 class="mb-1">Step ${step.step_number}: ${step.step_name}</h6>
                                    ${step.description ? `<small class="text-muted">${step.description}</small>` : ''}
                                    ${step.has_documents ? `<br><small class="text-info">Mandatory Documents: ${step.mandatory_uploaded}/${step.mandatory_total} uploaded</small>` : ''}
                                </div>
                            </div>
                            <div class="d-flex align-items-center gap-2">
                                <span class="badge badge-soft-${stepStatusColor}">
                                    ${step.completed ? 'Completed' : 'Pending'}
                                </span>
                                
                                ${step.completed ? `
                                    <button type="button" class="btn btn-sm btn-outline-warning" 
                                            onclick="markStepIncomplete(${containerId}, ${step.step_id})" 
                                            data-bs-toggle="tooltip" 
                                            title="Mark as Incomplete">
                                        <i class="ri-close-circle-line"></i> Undo
                                    </button>
                                ` : `
                                    <button type="button" class="btn btn-sm btn-success" 
                                            onclick="markStepComplete(${containerId}, ${step.step_id})" 
                                            data-bs-toggle="tooltip" 
                                            title="Mark Step as Complete">
                                        <i class="ri-check-circle-line"></i> Complete
                                    </button>
                                `}
                                
                                <!-- Show document management button if there are documents for this step -->
                                ${step.has_documents ? `
                                    <button type="button" class="btn btn-sm btn-outline-primary" 
                                            onclick="manageStepDocuments(${containerId}, ${step.step_id})" 
                                            data-bs-toggle="tooltip" 
                                            title="Manage Documents (${step.mandatory_uploaded}/${step.mandatory_total} uploaded)">
                                        <i class="ri-file-list-line"></i> Documents
                                    </button>
                                ` : `
                                    <!-- No documents required for this step -->
                                    <span class="text-muted small">No docs required</span>
                                `}
                            </div>
                        </div>
                    </div>
                    
                    <!-- Step completion info -->
                    ${step.completed && step.completed_at ? `
                        <div class="card-body bg-soft-success border-top py-2">
                            <small class="text-muted">
                                <i class="ri-check-circle-line text-success me-1"></i>
                                ${step.manually_completed ? 'Manually completed' : 'Auto-completed'} on ${new Date(step.completed_at).toLocaleString()}
                                ${step.completed_by ? ` by ${step.completed_by}` : ''}
                                ${step.completion_notes ? `<br><strong>Notes:</strong> ${step.completion_notes}` : ''}
                            </small>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    });
    
    html += `
            </div>
        </div>
    `;
    
    workflowDiv.innerHTML = html;
    initializeTooltips();
}


/**
 * Mark step as complete manually
 */
function markStepComplete(containerId, stepId) {
    showStepCompletionModal(containerId, stepId, 'complete');
}

/**
 * Mark step as incomplete
 */
function markStepIncomplete(containerId, stepId) {
    if (!confirm('Are you sure you want to mark this step as incomplete?')) {
        return;
    }
    
    // Show a simple loading state in the UI
    const button = document.querySelector(`button[onclick="markStepIncomplete(${containerId}, ${stepId})"]`);
    let originalButtonText = null;
    
    if (button) {
        originalButtonText = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<i class="ri-loader-2-line spinner-border spinner-border-sm me-1"></i> Processing...';
    }
    
    fetch(`/masters/api/container/${containerId}/step/${stepId}/update-status`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            action: 'incomplete',
            notes: '',
            entry_id: window.currentEntryId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('success', 'Step marked as incomplete successfully!');
            
            // Refresh container progress
            setTimeout(() => {
                refreshContainerProgress(containerId);
                
                // Also refresh the main containers list to update progress bars
                setTimeout(() => {
                    initializeContainersFromAPI();
                }, 1000);
            }, 500);
            
        } else {
            showAlert('error', data.error || 'Failed to update step status');
            
            // Reset button if there was an error
            if (button && originalButtonText) {
                button.disabled = false;
                button.innerHTML = originalButtonText;
            }
        }
    })
    .catch(error => {
        console.error('Error updating step status:', error);
        showAlert('error', 'An error occurred while updating the step status');
        
        // Reset button
        if (button && originalButtonText) {
            button.disabled = false;
            button.innerHTML = originalButtonText;
        }
    });
}


/**
 * Show modal for step completion with optional notes
 */
function showStepCompletionModal(containerId, stepId, action) {
    const modalHtml = `
        <div class="modal fade" id="stepCompletionModal" tabindex="-1" aria-labelledby="stepCompletionModalLabel" aria-hidden="true">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content border-0">
                    <div class="modal-header p-3 bg-soft-${action === 'complete' ? 'success' : 'warning'}">
                        <h5 class="modal-title" id="stepCompletionModalLabel">
                            <i class="ri-${action === 'complete' ? 'check-circle' : 'close-circle'}-line me-2"></i>
                            Mark Step as Complete
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        <div class="alert alert-success mb-4">
                            <i class="ri-information-line me-2"></i>
                            You are about to mark this workflow step as completed. This will update the overall workflow progress.
                        </div>
                        
                        <form id="stepCompletionForm">
                            <input type="hidden" name="container_id" value="${containerId}">
                            <input type="hidden" name="step_id" value="${stepId}">
                            <input type="hidden" name="action" value="${action}">
                            
                            <div class="mb-3">
                                <label for="completionNotes" class="form-label">
                                    Completion Notes <span class="text-muted">(Optional)</span>
                                </label>
                                <textarea class="form-control" id="completionNotes" name="notes" rows="3" 
                                          placeholder="Enter any notes about this step completion..."></textarea>
                                <small class="form-text text-muted">
                                    These notes will be saved with the completion record for future reference.
                                </small>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-success" onclick="submitStepCompletion()">
                            <i class="ri-check-line me-1"></i> Mark as Complete
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing modal if present
    const existingModal = document.getElementById('stepCompletionModal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Add modal to DOM
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Initialize modal
    const modal = new bootstrap.Modal(document.getElementById('stepCompletionModal'));
    modal.show();
    
    // Clean up modal on hide
    document.getElementById('stepCompletionModal').addEventListener('hidden.bs.modal', function () {
        this.remove();
    });
}

/**
 * Submit step completion form
 */
function submitStepCompletion() {
    const form = document.getElementById('stepCompletionForm');
    const formData = new FormData(form);
    
    const containerId = formData.get('container_id');
    const stepId = formData.get('step_id');
    const action = formData.get('action');
    const notes = formData.get('notes');
    
    // Call the API directly instead of using updateStepStatus
    const submitButton = document.querySelector('#stepCompletionModal .btn-success');
    let originalText = null;
    
    if (submitButton) {
        originalText = submitButton.innerHTML;
        submitButton.disabled = true;
        submitButton.innerHTML = '<i class="ri-loader-2-line spinner-border spinner-border-sm me-1"></i> Processing...';
    }
    
    fetch(`/masters/api/container/${containerId}/step/${stepId}/update-status`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            action: action,
            notes: notes,
            entry_id: window.currentEntryId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('success', `Step marked as ${action === 'complete' ? 'complete' : 'incomplete'} successfully!`);
            
            // Close modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('stepCompletionModal'));
            if (modal) {
                modal.hide();
            }
            
            // Refresh container progress
            setTimeout(() => {
                refreshContainerProgress(containerId);
                
                // Also refresh the main containers list to update progress bars
                setTimeout(() => {
                    initializeContainersFromAPI();
                }, 1000);
            }, 500);
            
        } else {
            showAlert('error', data.error || 'Failed to update step status');
            
            // Reset button if there was an error
            if (submitButton && originalText) {
                submitButton.disabled = false;
                submitButton.innerHTML = originalText;
            }
        }
    })
    .catch(error => {
        console.error('Error updating step status:', error);
        showAlert('error', 'An error occurred while updating the step status');
        
        // Reset button
        if (submitButton && originalText) {
            submitButton.disabled = false;
            submitButton.innerHTML = originalText;
        }
    });
}

/**
 * Update step status via API
 */
function updateStepStatus(containerId, stepId, action, notes = '') {
    const submitButton = document.querySelector('#stepCompletionModal .btn-success');
    let originalText = null;
    
    if (submitButton) {
        originalText = submitButton.innerHTML;
        submitButton.disabled = true;
        submitButton.innerHTML = '<i class="ri-loader-2-line spinner-border spinner-border-sm me-1"></i> Processing...';
    }
    
    fetch(`/masters/api/container/${containerId}/step/${stepId}/update-status`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            action: action,
            notes: notes,
            entry_id: window.currentEntryId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('success', `Step marked as ${action === 'complete' ? 'complete' : 'incomplete'} successfully!`);
            
            // Close modal if it exists
            const modal = bootstrap.Modal.getInstance(document.getElementById('stepCompletionModal'));
            if (modal) {
                modal.hide();
            }
            
            // Refresh container progress
            setTimeout(() => {
                refreshContainerProgress(containerId);
                
                // Also refresh the main containers list to update progress bars
                setTimeout(() => {
                    initializeContainersFromAPI();
                }, 1000);
            }, 500);
            
        } else {
            showAlert('error', data.error || 'Failed to update step status');
            
            // Reset button if there was an error and button exists
            if (submitButton && originalText) {
                submitButton.disabled = false;
                submitButton.innerHTML = originalText;
            }
        }
    })
    .catch(error => {
        console.error('Error updating step status:', error);
        showAlert('error', 'An error occurred while updating the step status');
        
        // Reset button if it exists
        if (submitButton && originalText) {
            submitButton.disabled = false;
            submitButton.innerHTML = originalText;
        }
    });
}



/**
 * Updated manageStepDocuments function to work with existing API structure
 */
function manageStepDocuments(containerId, stepId) {
    console.log(`Managing documents for container ${containerId}, step ${stepId}`);
    
    // Fetch the step details and required documents using the new API endpoint
    fetch(`/masters/api/container/${containerId}/step/${stepId}/documents`)
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showStepDocumentModal(containerId, stepId, data.step_info);
        } else {
            showAlert('error', data.error || 'Failed to load step document information');
        }
    })
    .catch(error => {
        console.error('Error loading step documents:', error);
        showAlert('error', 'An error occurred while loading document information');
    });
}

/**
 * Show modal with step document management interface
 */
function showStepDocumentModal(containerId, stepId, stepInfo) {
    const modalHtml = `
        <div class="modal fade" id="stepDocumentModal" tabindex="-1" aria-labelledby="stepDocumentModalLabel" aria-hidden="true">
            <div class="modal-dialog modal-lg modal-dialog-centered">
                <div class="modal-content border-0">
                    <div class="modal-header p-3 bg-soft-primary">
                        <h5 class="modal-title" id="stepDocumentModalLabel">
                            <i class="ri-file-list-line me-2"></i>
                            Manage Documents - ${stepInfo.step_name}
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        <!-- Step Information -->
                        <div class="alert alert-info mb-4">
                            <div class="d-flex align-items-center">
                                <i class="ri-information-line fs-20 me-2"></i>
                                <div>
                                    <h6 class="mb-1">Step ${stepInfo.step_number}: ${stepInfo.step_name}</h6>
                                    ${stepInfo.description ? `<p class="mb-1">${stepInfo.description}</p>` : ''}
                                    <p class="mb-0">
                                        Required Documents: ${stepInfo.mandatory_total} | 
                                        Uploaded: ${stepInfo.mandatory_uploaded} | 
                                        Status: ${stepInfo.completed ? '<span class="badge badge-soft-success">Complete</span>' : '<span class="badge badge-soft-warning">Pending</span>'}
                                    </p>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Required Documents List -->
                        <div class="card shadow-none border mb-4">
                            <div class="card-header bg-light">
                                <h6 class="card-title mb-0">Required Documents</h6>
                            </div>
                            <div class="card-body">
                                <div id="requiredDocumentsList">
                                    ${generateRequiredDocumentsList(stepInfo.required_documents || [])}
                                </div>
                            </div>
                        </div>
                        
                        <!-- Document Upload Section -->
                        <div class="card shadow-none border">
                            <div class="card-header bg-light">
                                <h6 class="card-title mb-0">Upload New Document</h6>
                            </div>
                            <div class="card-body">
                                <form id="stepDocumentUploadForm" enctype="multipart/form-data">
                                    <input type="hidden" name="container_id" value="${containerId}">
                                    <input type="hidden" name="step_id" value="${stepId}">
                                    <input type="hidden" name="entry_id" value="${window.currentEntryId}">
                                    
                                    <div class="row">
                                        <div class="col-md-6">
                                            <div class="mb-3">
                                                <label for="stepDocumentType" class="form-label">Document Type <span class="text-danger">*</span></label>
                                                <select class="form-select" id="stepDocumentType" name="container_document_id" required>
                                                    <option value="">Select Document Type</option>
                                                    ${generateDocumentTypeOptions(stepInfo.required_documents || [])}
                                                </select>
                                            </div>
                                        </div>
                                        <div class="col-md-6">
                                            <div class="mb-3">
                                                <label for="stepDocumentFile" class="form-label">Select File <span class="text-danger">*</span></label>
                                                <input type="file" class="form-control" id="stepDocumentFile" name="document_file" required>
                                                <small class="form-text text-muted">Max file size: 10MB</small>
                                            </div>
                                        </div>
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label for="stepDocumentNarration" class="form-label">Description (Optional)</label>
                                        <textarea class="form-control" id="stepDocumentNarration" name="narration" rows="2" placeholder="Enter document description or notes"></textarea>
                                    </div>
                                    
                                    <div class="d-flex justify-content-end">
                                        <button type="submit" class="btn btn-primary" id="uploadStepDocumentBtn">
                                            <i class="ri-upload-line me-1"></i>Upload Document
                                        </button>
                                    </div>
                                </form>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                        <button type="button" class="btn btn-success" onclick="refreshContainerProgress(${containerId})">
                            <i class="ri-refresh-line me-1"></i>Refresh Progress
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing modal if present
    const existingModal = document.getElementById('stepDocumentModal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Add modal to DOM
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Initialize modal
    const modal = new bootstrap.Modal(document.getElementById('stepDocumentModal'));
    modal.show();
    
    // Setup form submission
    setupStepDocumentUploadForm(containerId, stepId);
    
    // Clean up modal on hide
    document.getElementById('stepDocumentModal').addEventListener('hidden.bs.modal', function () {
        this.remove();
    });
}

/**
 * Generate HTML for required documents list using your existing data structure
 */
function generateRequiredDocumentsList(requiredDocs) {
    if (!requiredDocs || requiredDocs.length === 0) {
        return '<p class="text-muted mb-0">No specific document requirements defined for this step.</p>';
    }
    
    let html = '<div class="table-responsive"><table class="table table-sm table-bordered">';
    html += '<thead class="table-light"><tr><th>Document Type</th><th>Required</th><th>Status</th><th>Uploaded Files</th><th>Actions</th></tr></thead><tbody>';
    
    requiredDocs.forEach(reqDoc => {
        const hasUploaded = reqDoc.uploaded_documents && reqDoc.uploaded_documents.length > 0;
       const statusClass = hasUploaded ? 'success' : 'danger';
    const statusText = hasUploaded ? 'Uploaded' : 'Not Uploaded';
        
        html += `
            <tr>
                <td>
                    <strong>${reqDoc.document_name}</strong>
                    <br><small class="text-muted">${reqDoc.document_code}</small>
                </td>
                <td>${reqDoc.is_mandatory ? '<span class="badge badge-soft-danger">Mandatory</span>' : '<span class="badge badge-soft-info">Optional</span>'}</td>
                <td><span class="badge badge-soft-${statusClass}">${statusText}</span></td>
                <td>
        `;
        
        if (hasUploaded) {
            html += '<div class="uploaded-files">';
            reqDoc.uploaded_documents.forEach(uploadedDoc => {
                html += `
                    <div class="d-flex align-items-center justify-content-between border rounded p-2 mb-1">
                        <div>
                            <i class="ri-file-text-line me-1"></i>
                            <small>${uploadedDoc.original_filename}</small>
                            ${uploadedDoc.narration ? `<br><small class="text-muted">${uploadedDoc.narration}</small>` : ''}
                        </div>
                        <div class="d-flex gap-1">
                            <button type="button" class="btn btn-sm btn-soft-primary" onclick="viewStepDocument(${uploadedDoc.id})" title="Download">
                                <i class="ri-download-line"></i>
                            </button>
                            <button type="button" class="btn btn-sm btn-soft-danger" onclick="deleteStepDocument(${uploadedDoc.id}, ${reqDoc.container_id || 'null'})" title="Delete">
                                <i class="ri-delete-bin-line"></i>
                            </button>
                        </div>
                    </div>
                `;
            });
            html += '</div>';
        } else {
            html += '<span class="text-muted">Not uploaded</span>';
        }
        
        html += `
                </td>
                <td>
                    <button type="button" class="btn btn-sm btn-soft-success upload-for-doc" 
                            data-doc-id="${reqDoc.id}" 
                            title="Upload for this document type">
                        <i class="ri-upload-line"></i>
                    </button>
                </td>
            </tr>
        `;
    });
    
    html += '</tbody></table></div>';
    return html;
}

/**
 * Generate document type options for the upload form
 */
function generateDocumentTypeOptions(requiredDocs) {
    if (!requiredDocs || requiredDocs.length === 0) {
        return '<option value="">No documents required</option>';
    }
    
    let options = '';
    requiredDocs.forEach(doc => {
        const mandatoryText = doc.is_mandatory ? ' (Required)' : ' (Optional)';
        const uploadedText = doc.uploaded_documents && doc.uploaded_documents.length > 0 ? ' ✓' : '';
        options += `<option value="${doc.id}">${doc.document_name}${mandatoryText}${uploadedText}</option>`;
    });
    
    return options;
}

/**
 * Setup form submission for step document upload using your existing API
 */
function setupStepDocumentUploadForm(containerId, stepId) {
    const form = document.getElementById('stepDocumentUploadForm');
    if (!form) return;
    
    // Add click handlers for quick upload buttons
    form.addEventListener('click', function(event) {
        if (event.target.closest('.upload-for-doc')) {
            const button = event.target.closest('.upload-for-doc');
            const docId = button.getAttribute('data-doc-id');
            const docSelect = document.getElementById('stepDocumentType');
            if (docSelect) {
                docSelect.value = docId;
            }
        }
    });
    
    form.addEventListener('submit', function(event) {
        event.preventDefault();
        
        const formData = new FormData(form);
        const submitButton = document.getElementById('uploadStepDocumentBtn');
        
        // Show loading state
        const originalButtonText = submitButton.innerHTML;
        submitButton.disabled = true;
        submitButton.innerHTML = '<i class="ri-loader-2-line spinner-border spinner-border-sm me-1"></i> Uploading...';
        
        // Upload document using your existing API endpoint
        fetch('/masters/container-step-document/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert('success', 'Document uploaded successfully!');
                
                // Close modal after short delay
                setTimeout(() => {
                    const modal = bootstrap.Modal.getInstance(document.getElementById('stepDocumentModal'));
                    if (modal) modal.hide();
                    
                    // Refresh the container progress to show updated status
                    refreshContainerProgress(containerId);
                }, 1500);
                
            } else {
                showAlert('error', data.error || 'Failed to upload document');
                
                // Reset button state
                submitButton.disabled = false;
                submitButton.innerHTML = originalButtonText;
            }
        })
        .catch(error => {
            console.error('Error uploading document:', error);
            showAlert('error', 'An error occurred while uploading the document');
            
            // Reset button state
            submitButton.disabled = false;
            submitButton.innerHTML = originalButtonText;
        });
    });
}

/**
 * View/download uploaded step document using your existing API
 */
function viewStepDocument(documentId) {
    const url = `/masters/container-step-document/${documentId}/download`;
    window.open(url, '_blank');
}

/**
 * Enhanced delete function using your existing API endpoint
 */
function deleteStepDocument(documentId, containerId) {
    if (!confirm('Are you sure you want to delete this document?')) {
        return;
    }
    
    fetch(`/masters/container-step-document/${documentId}/delete`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('success', 'Document deleted successfully!');
            
            // Find the current modal and refresh its content
            const modal = document.getElementById('stepDocumentModal');
            if (modal) {
                // Extract container and step info from the modal
                const form = modal.querySelector('#stepDocumentUploadForm');
                if (form) {
                    const containerIdInput = form.querySelector('input[name="container_id"]');
                    const stepIdInput = form.querySelector('input[name="step_id"]');
                    
                    if (containerIdInput && stepIdInput) {
                        const containerId = containerIdInput.value;
                        const stepId = stepIdInput.value;
                        
                        // Close current modal and reopen with updated data
                        const modalInstance = bootstrap.Modal.getInstance(modal);
                        modalInstance.hide();
                        
                        // Reopen after a short delay
                        setTimeout(() => {
                            manageStepDocuments(containerId, stepId);
                        }, 500);
                    }
                }
            }
            
            // Also refresh the container progress
            setTimeout(() => {
                if (containerId && containerId !== 'null') {
                    refreshContainerProgress(containerId);
                }
            }, 1000);
            
        } else {
            showAlert('error', data.error || 'Failed to delete document');
        }
    })
    .catch(error => {
        console.error('Error deleting document:', error);
        showAlert('error', 'An error occurred while deleting the document');
    });
}








/**
 * Upload document for workflow step
 */
function uploadStepDocument(event, containerId, stepId, documentId) {
    event.preventDefault();
    
    const form = event.target;
    const formData = new FormData(form);
    const submitButton = form.querySelector('button[type="submit"]');
    
    // Show loading state
    const originalButtonText = submitButton.innerHTML;
    submitButton.disabled = true;
    submitButton.innerHTML = '<i class="ri-loader-2-line spinner-border spinner-border-sm me-1"></i> Uploading...';
    
    fetch('/masters/container-step-document/upload', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('success', 'Document uploaded successfully!');
            
            // Reset form
            form.reset();
            
            // Refresh the container display to show updated progress
            setTimeout(() => {
                refreshContainerProgress(containerId);
            }, 1500);
            
        } else {
            showAlert('error', data.error || 'Failed to upload document');
        }
    })
    .catch(error => {
        console.error('Error uploading document:', error);
        showAlert('error', 'An error occurred while uploading the document');
    })
    .finally(() => {
        // Reset button state
        submitButton.disabled = false;
        submitButton.innerHTML = originalButtonText;
    });
}

/**
 * Delete uploaded step document
 */
function deleteStepDocument(documentId, containerId) {
    if (!confirm('Are you sure you want to delete this document?')) {
        return;
    }
    
    fetch(`/masters/container-step-document/${documentId}/delete`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('success', 'Document deleted successfully!');
            
            // Refresh the container progress
            setTimeout(() => {
                refreshContainerProgress(containerId);
            }, 1500);
            
        } else {
            showAlert('error', data.error || 'Failed to delete document');
        }
    })
    .catch(error => {
        console.error('Error deleting document:', error);
        showAlert('error', 'An error occurred while deleting the document');
    });
}

/**
 * Refresh progress for a specific container
 */
function refreshContainerProgress(containerId) {
    const workflowDiv = document.getElementById(`containerWorkflow${containerId}`);
    if (workflowDiv && workflowDiv.style.display === 'block') {
        workflowDiv.innerHTML = `
            <div class="text-center py-3">
                <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
                <span class="ms-2">Refreshing progress...</span>
            </div>
        `;
        loadContainerWorkflowDetails(containerId);
    }
}

/**
 * Refresh all containers
 */
function refreshContainers() {
    initializeContainersFromAPI();
}

/**
 * Update workflow info display
 */
function updateWorkflowInfo(workflow) {
    const workflowInfoDiv = document.getElementById('workflowInfo');
    const workflowDetailsDiv = document.getElementById('workflowDetails');
    
    if (workflow && workflowDetailsDiv) {
        workflowDetailsDiv.innerHTML = `
            <p class="mb-1"><strong>Code:</strong> ${workflow.workflow_code}</p>
            <p class="mb-1"><strong>Name:</strong> ${workflow.workflow_name}</p>
            <p class="mb-0"><strong>Steps:</strong> ${workflow.step_count || 0} step(s)</p>
        `;
        if (workflowInfoDiv) {
            workflowInfoDiv.style.display = 'block';
        }
    } else {
        if (workflowInfoDiv) {
            workflowInfoDiv.style.display = 'none';
        }
    }
}

/**
 * Handle workflow selection
 */
function handleWorkflowSelection(workflowId) {
    console.log('Workflow selected:', workflowId);
    
    if (!workflowId) {
        // Clear workflow selection
        const workflowInfo = document.getElementById('workflowInfo');
        const containersList = document.getElementById('containersList');
        
        if (workflowInfo) workflowInfo.style.display = 'none';
        if (containersList) containersList.innerHTML = '';
        return;
    }
    
    // Show loading state
    const containersLoading = document.getElementById('containersLoading');
    const containersList = document.getElementById('containersList');
    
    if (containersLoading) {
        containersLoading.style.display = 'block';
    }
    if (containersList) {
        containersList.style.display = 'none';
    }
    
    // Save the workflow selection to database
    console.log('Saving workflow selection to database...');
    
    fetch(`/masters/api/entry/${window.currentEntryId}/save-workflow`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            workflow_id: workflowId
        })
    })
    .then(response => {
        console.log('Fetch response status:', response.status);
        console.log('Fetch response ok:', response.ok);
        
        // CRITICAL: Check if response is ok first
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`HTTP ${response.status}: ${text}`);
            });
        }
        
        return response.json();
    })
    .then(data => {
        console.log('Save workflow response:', data);
        
        // Check if the server responded with success
        if (data && data.success) {
            // Update workflow info display
            if (data.workflow) {
                updateWorkflowInfo(data.workflow);
            }
            currentWorkflowId = workflowId;
            
            showAlert('success', 'Workflow saved successfully!');
            
            // Now refresh containers to show updated progress
            // Increased delay to ensure DB is properly updated
            setTimeout(() => {
                initializeContainersFromAPI();
            }, 1500);
            
        } else {
            // Server returned success: false
            throw new Error(data?.error || 'Server returned unsuccessful response');
        }
    })
    .catch(error => {
        console.error('Error saving workflow:', error);
        showAlert('error', `Failed to save workflow: ${error.message}`);
        
        // Reset workflow selection on error
        const workflowSelect = document.getElementById('selected_workflow_id');
        if (workflowSelect) {
            workflowSelect.value = '';
        }
    })
    .finally(() => {
        if (containersLoading) {
            containersLoading.style.display = 'none';
        }
    });
}

/**
 * Show alert message
 */
function showAlert(type, message) {
    const alertClass = type === 'success' ? 'alert-success' : type === 'info' ? 'alert-info' : 'alert-danger';
    const iconClass = type === 'success' ? 'ri-check-double-line' : type === 'info' ? 'ri-information-line' : 'ri-error-warning-line';
    
    const alertHtml = `
        <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
            <i class="${iconClass}"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    `;
    
    const containersTab = document.getElementById('tab-containers');
    if (containersTab) {
        const cardBody = containersTab.querySelector('.card-body');
        if (cardBody) {
            cardBody.insertAdjacentHTML('afterbegin', alertHtml);
            
            // Auto-hide after 5 seconds
            setTimeout(() => {
                const alert = cardBody.querySelector('.alert');
                if (alert) {
                    const closeBtn = alert.querySelector('.btn-close');
                    if (closeBtn) closeBtn.click();
                }
            }, 5000);
        }
    }
}


/**
 * Initialize tooltips
 */
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Add CSS for better styling
const stepStyles = `
<style>
.workflow-progress-details .progress {
    border-radius: 10px;
}

.workflow-progress-details .progress-bar {
    border-radius: 10px;
}

.step-item .card-header.bg-soft-success {
    border-left: 3px solid #28a745;
}

.step-item .card:hover {
    box-shadow: 0 0.125rem 0.75rem rgba(0, 0, 0, 0.1);
    transition: all 0.3s ease;
}
</style>
`;

document.head.insertAdjacentHTML('beforeend', stepStyles);