// Items Tab JavaScript - Enhanced with modal editing and SweetAlert deletion

// Calculate line total for manual item form
function calculateLineTotal() {
    const quantity = parseFloat(document.getElementById('quantity').value) || 0;
    const price = parseFloat(document.getElementById('net_price').value) || 0;
    const total = quantity * price;
    
    document.getElementById('line_total_display').value = total > 0 ? total.toFixed(2) : '';
    document.getElementById('line_total').value = total;
}

// Calculate line total for edit form
function calculateEditLineTotal() {
    const quantity = parseFloat(document.getElementById('edit_quantity').value) || 0;
    const price = parseFloat(document.getElementById('edit_net_price').value) || 0;
    const total = quantity * price;
    
    document.getElementById('edit_line_total_display').value = total > 0 ? total.toFixed(2) : '';
    document.getElementById('edit_line_total').value = total;
}

// Filter PO items in the pull from PO modal
function filterPOItems() {
    const poSearch = document.getElementById('po_search').value.toLowerCase();
    const materialSearch = document.getElementById('material_search').value.toLowerCase();
    const supplierFilter = document.getElementById('supplier_filter').value;
    
    const rows = document.querySelectorAll('.po-item-row');
    
    rows.forEach(row => {
        const poNumber = row.dataset.poNumber.toLowerCase();
        const material = row.dataset.material;
        const supplier = row.dataset.supplier;
        
        const matchesPO = !poSearch || poNumber.includes(poSearch);
        const matchesMaterial = !materialSearch || material.includes(materialSearch);
        const matchesSupplier = !supplierFilter || supplier === supplierFilter;
        
        if (matchesPO && matchesMaterial && matchesSupplier) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
            // Uncheck hidden items
            const checkbox = row.querySelector('.po-item-checkbox');
            if (checkbox) checkbox.checked = false;
        }
    });
    
    updateSelection();
}

// Toggle all visible PO items
function toggleAllPOItems() {
    const selectAll = document.getElementById('selectAllPO');
    const visibleCheckboxes = Array.from(document.querySelectorAll('.po-item-checkbox'))
        .filter(cb => cb.closest('.po-item-row').style.display !== 'none');
    
    visibleCheckboxes.forEach(checkbox => {
        checkbox.checked = selectAll.checked;
    });
    
    updateSelection();
}

// Update selection count and button state
function updateSelection() {
    const selectedCheckboxes = document.querySelectorAll('.po-item-checkbox:checked');
    const count = selectedCheckboxes.length;
    
    // Update summary
    const summary = document.getElementById('selectionSummary');
    const countSpan = document.getElementById('selectedCount');
    const countBtn = document.getElementById('selectedCountBtn');
    const addBtn = document.getElementById('addSelectedItemsBtn');
    
    if (count > 0) {
        summary.style.display = 'block';
        countSpan.textContent = count;
        countBtn.textContent = count;
        addBtn.disabled = false;
    } else {
        summary.style.display = 'none';
        countBtn.textContent = '0';
        addBtn.disabled = true;
    }
    
    // Update select all checkbox state
    const selectAll = document.getElementById('selectAllPO');
    const visibleCheckboxes = Array.from(document.querySelectorAll('.po-item-checkbox'))
        .filter(cb => cb.closest('.po-item-row').style.display !== 'none');
    const visibleChecked = visibleCheckboxes.filter(cb => cb.checked);
    
    if (visibleChecked.length === 0) {
        selectAll.checked = false;
        selectAll.indeterminate = false;
    } else if (visibleChecked.length === visibleCheckboxes.length) {
        selectAll.checked = true;
        selectAll.indeterminate = false;
    } else {
        selectAll.checked = false;
        selectAll.indeterminate = true;
    }
}

// Edit item function - now uses modal instead of separate page
async function editItem(itemId) {
    try {
        // Show loading state
        const modal = new bootstrap.Modal(document.getElementById('editItemModal'));
        modal.show();
        
        // Set loading state in modal
        const modalTitle = document.querySelector('#editItemModal .modal-title');
        const submitButton = document.querySelector('#editItemModal .btn-primary');
        
        if (modalTitle) modalTitle.textContent = 'Loading Item...';
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Loading...';
        }
        
        // Fetch item data
        const response = await fetch(`/customer_portal/api/shipment-item/${itemId}`);
        if (!response.ok) {
            throw new Error(`Failed to fetch item: ${response.status}`);
        }
        
        const item = await response.json();
        console.log("Item data for editing:", item);
        
        // Update modal UI
        if (modalTitle) modalTitle.textContent = 'Edit Item';
        if (submitButton) {
            submitButton.disabled = false;
            submitButton.innerHTML = '<i class="ri-save-line me-1"></i> Update Item';
        }
        
        // Populate form fields
        populateEditForm(item);
        
    } catch (error) {
        console.error('Error in editItem:', error);
        Swal.fire({
            title: 'Error',
            text: 'Failed to load item data: ' + error.message,
            icon: 'error'
        });
        
        // Close modal on error
        const modal = bootstrap.Modal.getInstance(document.getElementById('editItemModal'));
        if (modal) modal.hide();
    }
}

// Populate edit form with item data
function populateEditForm(item) {
    // Set the item ID in hidden field
    document.getElementById('edit_item_id').value = item.id;
    
    // Set the form action URL
    const form = document.getElementById('editItemForm');
    form.action = `/customer_portal/api/shipment-item/${item.id}/edit`;
    
    // Populate all fields
    document.getElementById('edit_material_code').value = item.material_code || '';
    document.getElementById('edit_material_name').value = item.material_name || '';
    document.getElementById('edit_quantity').value = item.quantity || '';
    document.getElementById('edit_order_unit').value = item.order_unit || '';
    document.getElementById('edit_net_price').value = item.net_price || '';
    document.getElementById('edit_supplier_name').value = item.supplier_name || '';
    document.getElementById('edit_po_number').value = item.po_number || '';
    document.getElementById('edit_remarks').value = item.remarks || '';
    
    // Handle delivery date
    if (item.delivery_date) {
        try {
            // Assuming delivery_date comes as YYYY-MM-DD format
            document.getElementById('edit_delivery_date').value = item.delivery_date;
        } catch (error) {
            console.error("Error setting delivery date:", error);
        }
    }
    
    // Calculate and display line total
    calculateEditLineTotal();
}

// Handle edit form submission
async function handleEditFormSubmit(event) {
    event.preventDefault();
    
    const form = event.target;
    const formData = new FormData(form);
    const itemId = document.getElementById('edit_item_id').value;
    
    try {
        // Show loading state
        const submitButton = form.querySelector('.btn-primary');
        const originalText = submitButton.innerHTML;
        submitButton.disabled = true;
        submitButton.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Updating...';
        
        const response = await fetch(`/customer_portal/api/shipment-item/${itemId}/edit`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Show success message and reload page
            Swal.fire({
                title: 'Success!',
                text: result.message || 'Item updated successfully',
                icon: 'success',
                timer: 1500,
                showConfirmButton: false
            }).then(() => {
                window.location.reload();
            });
        } else {
            throw new Error(result.error || 'Failed to update item');
        }
        
    } catch (error) {
        console.error('Error updating item:', error);
        Swal.fire({
            title: 'Error',
            text: error.message || 'Failed to update item',
            icon: 'error'
        });
        
        // Reset button state
        const submitButton = form.querySelector('.btn-primary');
        submitButton.disabled = false;
        submitButton.innerHTML = '<i class="ri-save-line me-1"></i> Update Item';
    }
}

// Delete item function with SweetAlert confirmation
function deleteItem(itemId, materialCode) {
    Swal.fire({
        title: 'Delete Item',
        text: `Are you sure you want to delete item "${materialCode}"?`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        cancelButtonColor: '#3085d6',
        confirmButtonText: 'Yes, delete it!',
        cancelButtonText: 'Cancel',
        reverseButtons: true
    }).then(async (result) => {
        if (result.isConfirmed) {
            try {
                // Show loading
                Swal.fire({
                    title: 'Deleting...',
                    text: 'Please wait while we delete the item.',
                    allowOutsideClick: false,
                    showConfirmButton: false,
                    willOpen: () => {
                        Swal.showLoading();
                    }
                });
                
                const response = await fetch(`/customer_portal/api/shipment-item/${itemId}/delete`, {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });
                
                const result = await response.json();
                
                if (result.success) {
                    Swal.fire({
                        title: 'Deleted!',
                        text: result.message || 'Item has been deleted successfully.',
                        icon: 'success',
                        timer: 1500,
                        showConfirmButton: false
                    }).then(() => {
                        window.location.reload();
                    });
                } else {
                    throw new Error(result.error || 'Failed to delete item');
                }
                
            } catch (error) {
                console.error('Error deleting item:', error);
                Swal.fire({
                    title: 'Error',
                    text: error.message || 'Failed to delete item',
                    icon: 'error'
                });
            }
        }
    });
}

// Reset manual item form when modal is closed
function resetManualItemForm() {
    const form = document.getElementById('manualItemForm');
    if (form) {
        form.reset();
        document.getElementById('line_total_display').value = '';
        document.getElementById('line_total').value = '';
    }
}

// Reset edit item form when modal is closed
function resetEditItemForm() {
    const form = document.getElementById('editItemForm');
    if (form) {
        form.reset();
        document.getElementById('edit_line_total_display').value = '';
        document.getElementById('edit_line_total').value = '';
    }
}

// Reset PO form when modal is closed
function resetPOForm() {
    const form = document.getElementById('pullFromPOForm');
    if (form) {
        form.reset();
        document.getElementById('po_search').value = '';
        document.getElementById('material_search').value = '';
        document.getElementById('supplier_filter').value = '';
        
        // Reset all checkboxes
        document.querySelectorAll('.po-item-checkbox').forEach(cb => cb.checked = false);
        document.getElementById('selectAllPO').checked = false;
        document.getElementById('selectAllPO').indeterminate = false;
        
        // Show all rows
        document.querySelectorAll('.po-item-row').forEach(row => row.style.display = '');
        
        updateSelection();
    }
}



function viewMaterialDocuments(materialId) {
    currentViewMaterialId = materialId;
    const modal = new bootstrap.Modal(document.getElementById('materialDocumentsModal'));
    modal.show();
    
    // Show loading state
    const existingDocuments = document.getElementById('materialExistingDocuments');
    const requiredDocuments = document.getElementById('materialRequiredDocuments');
    const materialInfo = document.getElementById('materialHSInfo');
    const alertSection = document.getElementById('materialAlertSection');
    
    existingDocuments.innerHTML = '<div class="text-center py-3"><div class="spinner-border text-primary" role="status"></div><p class="mt-2">Loading documents...</p></div>';
    requiredDocuments.innerHTML = '<div class="text-center py-3"><div class="spinner-border text-primary" role="status"></div><p class="mt-2">Loading required documents...</p></div>';
    materialInfo.style.display = 'none';
    if (alertSection) alertSection.style.display = 'none';
    
    // Use your ORIGINAL function call
    loadMaterialDocumentsForView(materialId);
    
    // ONLY ADD: Alert check after loading
    setTimeout(() => {
        checkMaterialAlertForModal(materialId);
    }, 1000);
}



// Function to check material alerts for modal display
function checkMaterialAlertForModal(materialId) {
    const currentShipmentId = getCurrentShipmentId();
    if (!currentShipmentId || !materialId) return;
    
    fetch(`/customer_portal/api/material-document-alerts/${materialId}/${currentShipmentId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                displayMaterialAlertsInModal(data);
            }
        })
        .catch(error => {
            console.error('Error checking material alerts for modal:', error);
        });
}


// Function to display alerts in modal
function displayMaterialAlertsInModal(alertData) {
    const alertSection = document.getElementById('materialAlertSection');
    const alertMessage = document.getElementById('alertMessage');
    
    if (!alertSection || !alertMessage) return;
    
    if (alertData.has_alerts && alertData.expiring_documents.length > 0) {
        alertSection.style.display = 'block';
        
        const expiringCount = alertData.expiring_documents.filter(doc => doc.is_expiring).length;
        const dateSource = alertData.date_source === 'eta' ? 'ETA' : 'deadline';
        const comparisonDate = new Date(alertData.comparison_date).toLocaleDateString();
        
        alertMessage.innerHTML = `
            <strong>${expiringCount}</strong> document(s) expire before the shipment ${dateSource} 
            (<strong>${comparisonDate}</strong>). Please ensure document validity extends beyond the shipment arrival date.
        `;
        
        // Highlight expiring documents with red border
        setTimeout(() => {
            highlightExpiringDocuments(alertData.expiring_documents);
        }, 500);
    } else {
        alertSection.style.display = 'none';
    }
}


// Function to highlight expiring documents
function highlightExpiringDocuments(expiringDocuments) {
    expiringDocuments.forEach(doc => {
        if (doc.is_expiring) {
            const documentCard = document.querySelector(`[data-document-id="${doc.document_id}"] .document-card`);
            if (documentCard) {
                documentCard.style.borderLeft = '3px solid #dc3545';
                documentCard.style.backgroundColor = 'rgba(220, 53, 69, 0.05)';
                
                // Add warning icon to expiry date
                const expiryDate = documentCard.querySelector('.expiry-date');
                if (expiryDate && !expiryDate.querySelector('.ri-error-warning-line')) {
                    expiryDate.style.color = '#dc3545';
                    expiryDate.style.fontWeight = 'bold';
                    expiryDate.innerHTML += ' <i class="ri-error-warning-line" title="Expires before shipment date"></i>';
                }
            }
        }
    });
}

// Utility functions remain the same
function getCurrentShipmentId() {
    console.log('🔍 Getting current shipment ID...');
    
    // Method 1: From URL
    const urlParts = window.location.pathname.split('/');
    const lastPart = urlParts[urlParts.length - 1];
    if (lastPart && !isNaN(lastPart)) {
        console.log('✅ Shipment ID from URL:', lastPart);
        return lastPart;
    }
    
    // Method 2: From hidden input
    const shipmentInput = document.querySelector('input[name="id"], input[name="order_id"]');
    if (shipmentInput && shipmentInput.value) {
        console.log('✅ Shipment ID from input:', shipmentInput.value);
        return shipmentInput.value;
    }
    
    // Method 3: From data attribute
    const shipmentContainer = document.querySelector('[data-shipment-id]');
    if (shipmentContainer) {
        const id = shipmentContainer.getAttribute('data-shipment-id');
        console.log('✅ Shipment ID from data attribute:', id);
        return id;
    }
    
    console.error('❌ Could not determine current shipment ID');
    return null;
}


function initializeMaterialAlerts() {
    console.log('🚀 Initializing material alerts...');
    
    const currentShipmentId = getCurrentShipmentId();
    if (!currentShipmentId) {
        console.error('❌ No shipment ID found, cannot initialize alerts');
        return;
    }
    
    console.log('📋 Shipment ID:', currentShipmentId);
    
    // Find all material buttons
    const materialButtons = document.querySelectorAll('.view-documents-btn, .btn-outline-info[onclick*="viewMaterialDocuments"]');
    console.log('🔎 Found material buttons:', materialButtons.length);
    
    if (materialButtons.length === 0) {
        console.warn('⚠️ No material buttons found - may need to wait for DOM');
        return;
    }
    
    // Initial check
    checkAllMaterialAlerts();
    
    // Periodic checking every 30 seconds
    setInterval(checkAllMaterialAlerts, 30000);
    
    console.log('✅ Material alerts initialized successfully');
}



function checkAllMaterialAlerts() {
    const currentShipmentId = getCurrentShipmentId();
    if (!currentShipmentId) {
        console.error('❌ No shipment ID for alert checking');
        return;
    }
    
    console.log('🔄 Checking all material alerts for shipment:', currentShipmentId);
    
    const materialButtons = document.querySelectorAll('.view-documents-btn, .btn-outline-info[onclick*="viewMaterialDocuments"]');
    console.log('📊 Checking', materialButtons.length, 'materials');
    
    materialButtons.forEach((button, index) => {
        const onclick = button.getAttribute('onclick');
        if (onclick) {
            const materialIdMatch = onclick.match(/viewMaterialDocuments\((\d+)\)/);
            if (materialIdMatch && materialIdMatch[1]) {
                const materialId = materialIdMatch[1];
                console.log(`🔍 Checking material ${index + 1}/${materialButtons.length}: ID ${materialId}`);
                checkMaterialAlert(materialId, currentShipmentId);
            }
        }
    });
}

function checkMaterialAlert(materialId, shipmentId) {
    console.log(`🔍 Checking alerts for material ${materialId} in shipment ${shipmentId}`);
    
    fetch(`/customer_portal/api/material-document-alerts/${materialId}/${shipmentId}`)
        .then(response => {
            console.log(`📡 API Response for material ${materialId}:`, response.status);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            console.log(`📊 Alert data for material ${materialId}:`, data);
            
            if (data.success) {
                console.log(`${data.has_alerts ? '🔴' : '✅'} Material ${materialId} has alerts:`, data.has_alerts);
                
                if (data.has_alerts) {
                    console.log(`⚠️ Expiring documents for material ${materialId}:`, data.expiring_documents.filter(d => d.is_expiring));
                }
                
                updateMaterialAlertIcon(materialId, data.has_alerts);
            } else {
                console.error(`❌ API error for material ${materialId}:`, data.message);
            }
        })
        .catch(error => {
            console.error(`❌ Error checking material ${materialId} alerts:`, error);
        });
}


function updateMaterialAlertIcon(materialId, hasAlerts) {
    const alertIcon = document.getElementById(`material-alert-${materialId}`);
    
    console.log(`🎯 Updating alert icon for material ${materialId}:`, {
        hasAlerts,
        iconExists: !!alertIcon,
        iconElement: alertIcon
    });
    
    if (alertIcon) {
        alertIcon.style.display = hasAlerts ? 'inline-block' : 'none';
        
        if (hasAlerts) {
            console.log(`🔴 Showing alert icon for material ${materialId}`);
            
            // Initialize tooltip if not already done
            if (!alertIcon.hasAttribute('data-bs-original-title')) {
                new bootstrap.Tooltip(alertIcon);
            }
        } else {
            console.log(`✅ Hiding alert icon for material ${materialId}`);
        }
    } else {
        console.error(`❌ Alert icon not found for material ${materialId} - ID: material-alert-${materialId}`);
        
        // Try to find any similar elements
        const similarElements = document.querySelectorAll(`[id*="material-alert"], [id*="${materialId}"]`);
        console.log('🔍 Similar elements found:', similarElements);
    }
}


function loadMaterialDocumentsForView(materialId) {
    fetch(`/masters/get-material-documents?material_id=${materialId}`)
        .then(response => response.json())
        .then(data => {
            displayMaterialDocumentsForView(data);
        })
        .catch(error => {
            console.error('Error:', error);
            document.getElementById('materialExistingDocuments').innerHTML = 
                '<div class="text-center text-danger"><p>Error loading documents</p></div>';
            document.getElementById('materialRequiredDocuments').innerHTML = '';
        });
}

function displayMaterialDocumentsForView(data) {
    const existingContainer = document.getElementById('materialExistingDocuments');
    const requiredContainer = document.getElementById('materialRequiredDocuments');
    const materialInfo = document.getElementById('materialHSInfo');
    
    if (!data.hs_code) {
        existingContainer.innerHTML = '<div class="text-center text-warning"><p>No HS code connected to this material</p></div>';
        requiredContainer.innerHTML = '';
        materialInfo.style.display = 'none';
        return;
    }

    // Show material and HS code information
    materialInfo.style.display = 'block';
    document.getElementById('materialInfoTitle').textContent = `Material: ${data.material_code || 'Unknown'} - ${data.material_name || 'Unknown'}`;
    document.getElementById('materialInfoDetails').textContent = `HS Code: ${data.hs_code.code} - ${data.hs_code.description || 'No description'}`;

    let progressHtml = '';
    if (data.required_documents.length > 0) {
        const totalRequired = data.required_documents.filter(doc => doc.is_mandatory).length;
        const uploadedRequired = data.uploaded_documents.filter(doc => 
            data.required_documents.find(req => req.id === doc.document_id && req.is_mandatory)
        ).length;
        
        const progressPercentage = totalRequired > 0 ? Math.round((uploadedRequired / totalRequired) * 100) : 100;
        
        progressHtml = `
            <div class="mb-4">
                <h6>Document Completion Status</h6>
                <div class="progress" style="height: 20px;">
                    <div class="progress-bar ${progressPercentage < 100 ? 'bg-warning' : 'bg-success'}" role="progressbar" 
                        style="width: ${progressPercentage}%;" aria-valuenow="${progressPercentage}" 
                        aria-valuemin="0" aria-valuemax="100">
                        ${uploadedRequired} of ${totalRequired} required documents
                    </div>
                </div>
                <small class="text-muted mt-1 d-block">
                    ${progressPercentage < 100 ? 
                        `${totalRequired - uploadedRequired} required document(s) still missing.` : 
                        'All required documents have been uploaded.'}
                </small>
            </div>
        `;
    }

    // Display uploaded documents using YOUR ORIGINAL field names
    if (data.uploaded_documents && data.uploaded_documents.length > 0) {
        let documentsHtml = progressHtml + '<div class="row">';
        
        data.uploaded_documents.forEach(doc => {
            documentsHtml += `
                <div class="col-md-6 mb-3" data-document-id="${doc.id}">
                    <div class="card h-100 document-card">
                        <div class="card-body">
                            <h6 class="card-title">${doc.document_category_name || 'Unknown Category'}</h6>
                            <p class="card-text small text-muted">${doc.issuing_body_name || 'Unknown Issuing Body'}</p>
                            <p class="card-text">
                                <strong>File:</strong> ${doc.file_name}<br>
                                <strong>Expiry:</strong> 
                                <span class="expiry-date">
                                    ${doc.expiry_date ? new Date(doc.expiry_date).toLocaleDateString() : 'No expiry date'}
                                </span><br>
                                <strong>Uploaded:</strong> ${doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleDateString() : 'Unknown'}
                            </p>
                            <div class="d-flex gap-2">
                        
                                <a href="/masters/download-material-document/${doc.id}" class="btn btn-sm btn-outline-success">
                                    <i class="ri-eye-line me-1"></i>View
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
        
        documentsHtml += '</div>';
        existingContainer.innerHTML = documentsHtml;
    } else {
        existingContainer.innerHTML = progressHtml + '<div class="text-center text-info"><p>No documents uploaded yet</p></div>';
    }

    // Display required documents using YOUR ORIGINAL field names
    if (data.required_documents && data.required_documents.length > 0) {
        let requiredHtml = `<div class="row">`;
        
        data.required_documents.forEach(doc => {
            const hasUpload = data.uploaded_documents.some(upload => upload.document_id === doc.id);
            
            requiredHtml += `
                <div class="col-12 mb-3">
                    <div class="card ${hasUpload ? 'border-success' : 'border-warning'}">
                        <div class="card-body">
                            <h6 class="card-title">
                                ${doc.display_name || 'Unknown Document'}
                                ${doc.is_mandatory ? '<span class="badge badge-soft-danger ms-2">Required</span>' : 
                                    '<span class="badge badge-soft-info ms-2">Optional</span>'}
                                ${hasUpload ? 
                                    '<span class="badge badge-soft-success ms-2">Uploaded</span>' : 
                                    '<span class="badge badge-soft-warning ms-2">Missing</span>'}
                            </h6>
                            <p class="text-muted small">Issuing Body: ${doc.issuing_body_name}</p>
                            ${doc.sample_file_path ? `
                            <div class="mb-3">
                                <button type="button" class="btn btn-sm btn-outline-info" onclick="viewMaterialSampleDocument('${doc.sample_file_path}')">
                                    <i class="ri-file-text-line me-1"></i>View Sample Document
                                </button>
                            </div>
                            ` : ''}
                            
                            ${hasUpload ? `
                            <div class="alert alert-success">
                                <i class="ri-check-line me-2"></i>
                                Document has been uploaded
                            </div>
                            ` : `
                            <div class="alert alert-warning">
                                <i class="ri-alert-line me-2"></i>
                                Document not uploaded yet
                            </div>
                            `}
                        </div>
                    </div>
                </div>
            `;
        });
        
        requiredHtml += '</div>';
        requiredContainer.innerHTML = requiredHtml;
    } else {
        requiredContainer.innerHTML = `
            <div class="alert alert-info">
                <i class="ri-information-line me-2"></i>
                No documents are required for this HS code.
            </div>
        `;
    }
}



function viewMaterialDocument(documentId) {
    // Open document in new tab
    window.open(`/masters/download-material-document/${documentId}`, '_blank');
}

function downloadMaterialDocument(documentId) {
    // Download document
    window.open(`/masters/download-material-document/${documentId}`, '_blank');
}

function viewMaterialSampleDocument(path) {
    if (!path) {
        showAlert('No sample file available', 'warning');
        return;
    }
    
    // Open the sample document in a new tab
    window.open(`/masters/view-sample-document/${encodeURIComponent(path)}`, '_blank');
}


// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize selection count for PO modal
    updateSelection();

    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    });
    
    // Add event listeners for modal resets
    const addManualModal = document.getElementById('addManualItemModal');
    if (addManualModal) {
        addManualModal.addEventListener('hidden.bs.modal', resetManualItemForm);
    }
    
    const editItemModal = document.getElementById('editItemModal');
    if (editItemModal) {
        editItemModal.addEventListener('hidden.bs.modal', resetEditItemForm);
    }
    
    const pullFromPOModal = document.getElementById('pullFromPOModal');
    if (pullFromPOModal) {
        pullFromPOModal.addEventListener('hidden.bs.modal', resetPOForm);
    }
    
    // Add event listener for edit form submission
    const editItemForm = document.getElementById('editItemForm');
    if (editItemForm) {
        editItemForm.addEventListener('submit', handleEditFormSubmit);
    }
    
    // Add form validation feedback
    const forms = document.querySelectorAll('.needs-validation');
    forms.forEach(form => {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });

    setTimeout(initializeMaterialAlerts, 1000);

    
    // Make edit and delete functions globally available
    window.editItem = editItem;
    window.deleteItem = deleteItem;
});

function forceInitializeAlerts() {
    console.log('🔄 Force initializing alerts...');
    
    // Try immediate initialization
    initializeMaterialAlerts();
    
    // Try after 1 second
    setTimeout(() => {
        console.log('🔄 Retry initialization after 1s...');
        initializeMaterialAlerts();
    }, 1000);
    
    // Try after 3 seconds
    setTimeout(() => {
        console.log('🔄 Retry initialization after 3s...');
        initializeMaterialAlerts();
    }, 3000);
}


document.addEventListener('DOMContentLoaded', function() {
    console.log('📄 DOM loaded, starting alert initialization...');
    forceInitializeAlerts();
});

document.addEventListener('shown.bs.tab', function(event) {
    if (event.target.getAttribute('href') === '#tab-items' || 
        event.target.getAttribute('data-bs-target') === '#tab-items') {
        setTimeout(initializeMaterialAlerts, 500);
    }
});



