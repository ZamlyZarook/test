// o_s_demurrage_tab.js - Updated with Bearer Support

// Global variables
let demurrageRecords = [];
let containers = [];
let reasons = [];
let bearers = []; // NEW: Add bearers array
let isEditingDemurrage = false;
let currentDemurrageId = null;
let dataLoaded = false;
let demurrageFromDate = null;
let autoCalculationEnabled = true;


// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    initializeDemurrageTab();
});

function initializeDemurrageTab() {
    // Load data when demurrage tab is activated
    const demurrageTab = document.querySelector('a[href="#tab-demurrage"]');
    if (demurrageTab) {
        demurrageTab.addEventListener('shown.bs.tab', function() {
            loadDemurrageData();
        });
    }

    // Check if demurrage tab is already active on page load
    const demurrageTabPane = document.getElementById('tab-demurrage');
    if (demurrageTabPane && demurrageTabPane.classList.contains('active')) {
        console.log('Demurrage tab is already active, loading data...');
        setTimeout(() => {
            loadDemurrageData();
        }, 100);
    }

    // Add demurrage button event
    const addDemurrageBtn = document.getElementById('addDemurrageBtn');
    if (addDemurrageBtn) {
        addDemurrageBtn.addEventListener('click', function() {
            openDemurrageModal();
        });
    }

    // Form submission
    const demurrageForm = document.getElementById('demurrageForm');
    if (demurrageForm) {
        demurrageForm.addEventListener('submit', handleDemurrageSubmit);
    }

    // Modal events
    const demurrageModal = document.getElementById('demurrageModal');
    if (demurrageModal) {
        demurrageModal.addEventListener('hidden.bs.modal', resetDemurrageForm);
    }

    initializeDemurrageModalTabs();

    // NEW: Add bearing percentage validation
    const bearingPercentageInput = document.getElementById('bearingPercentage');
    if (bearingPercentageInput) {
        bearingPercentageInput.addEventListener('input', function() {
            const value = parseFloat(this.value);
            if (value < 0) this.value = 0;
            if (value > 100) this.value = 100;
        });
    }
}

function loadDemurrageData() {
    const shipmentId = document.getElementById('shipmentId').value;
    if (!shipmentId) return;

    console.log('Loading demurrage data for shipment:', shipmentId);

    // Reset global variables before loading
    containers = [];
    reasons = [];
    bearers = []; // NEW: Reset bearers
    demurrageRecords = [];

    // NEW: Load bearers along with other data
    Promise.all([
        loadContainers(shipmentId),
        loadReasons(),
        loadBearers(), // NEW: Load bearers
        loadDemurrageRecords(shipmentId)
    ]).then(() => {
        dataLoaded = true;
        console.log('All demurrage data loaded successfully');
        console.log('Final data state:', {
            containers: containers.length,
            reasons: reasons.length,
            bearers: bearers.length, // NEW: Log bearers count
            demurrageRecords: demurrageRecords.length
        });
        renderDemurrageTable();
    }).catch(error => {
        console.error('Error loading demurrage data:', error);
        dataLoaded = false;
        Swal.fire('Error', 'Failed to load demurrage data', 'error');
    });
}

function loadContainers(shipmentId) {
    return fetch(`/masters/api/demurrage/containers/${shipmentId}`)
        .then(response => {
            console.log('Containers API response status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Containers API response data:', data);
            if (data.success) {
                containers = data.data || [];
                console.log('Containers loaded successfully:', containers.length);
                populateContainerDropdown();
            } else {
                console.warn('No containers found:', data.message);
                containers = [];
                populateContainerDropdown();
            }
        })
        .catch(error => {
            console.error('Error loading containers:', error);
            containers = [];
            populateContainerDropdown();
        });
}

function loadReasons() {
    return fetch('/masters/api/demurrage/reasons')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                reasons = data.data || [];
                console.log('Reasons loaded:', reasons.length);
                populateReasonsDropdown();
            } else {
                console.warn('No reasons found:', data.message);
                reasons = [];
                populateReasonsDropdown();
            }
        })
        .catch(error => {
            console.error('Error loading reasons:', error);
            reasons = [];
            populateReasonsDropdown();
        });
}

// NEW: Load bearers function
function loadBearers() {
    return fetch('/masters/api/demurrage/bearers')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                bearers = data.data || [];
                console.log('Bearers loaded:', bearers.length);
                populateBearersDropdown();
            } else {
                console.warn('No bearers found:', data.message);
                bearers = [];
                populateBearersDropdown();
            }
        })
        .catch(error => {
            console.error('Error loading bearers:', error);
            bearers = [];
            populateBearersDropdown();
        });
}

function loadDemurrageRecords(shipmentId) {
    return fetch(`/masters/api/demurrage/shipment/${shipmentId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                demurrageRecords = data.data || [];
                console.log('Demurrage records loaded:', demurrageRecords.length);
                updateTotalAmount(data.total_amount || 0);
            } else {
                console.warn('No demurrage records found:', data.message);
                demurrageRecords = [];
                updateTotalAmount(0);
            }
        })
        .catch(error => {
            console.error('Error loading demurrage records:', error);
            demurrageRecords = [];
            updateTotalAmount(0);
        });
}

function populateContainerDropdown() {
    const containerSelect = document.getElementById('containerId');
    if (!containerSelect) return;

    containerSelect.innerHTML = '<option value="">Select Container</option>';

    // Get containers already used in demurrageRecords
    const usedContainers = new Set(
        demurrageRecords.map(rec => `${rec.container_type}_${rec.container_id}`)
    );

    containers.forEach(container => {
        const key = `${container.container_type}_${container.id}`;
        if (!usedContainers.has(key) || (isEditingDemurrage && currentDemurrageId && key === getCurrentEditingContainerKey())) {
            const option = document.createElement('option');
            option.value = key;
            option.textContent = `${container.container_number} (${container.size_type})`;
            option.dataset.containerId = container.id;
            option.dataset.containerType = container.container_type;
            containerSelect.appendChild(option);
        }
    });
}

function populateReasonsDropdown() {
    const reasonSelect = document.getElementById('reasonId');
    if (!reasonSelect) return;

    reasonSelect.innerHTML = '<option value="">Select Reason</option>';
    
    reasons.forEach(reason => {
        const option = document.createElement('option');
        option.value = reason.id;
        option.textContent = reason.reason_name;
        reasonSelect.appendChild(option);
    });
    
    console.log('Reasons dropdown populated with', reasons.length, 'reasons');
}

// NEW: Populate bearers dropdown
function populateBearersDropdown() {
    const bearerSelect = document.getElementById('bearerId');
    if (!bearerSelect) return;

    bearerSelect.innerHTML = '<option value="">Select Bearer</option>';
    
    bearers.forEach(bearer => {
        const option = document.createElement('option');
        option.value = bearer.id;
        option.textContent = bearer.name;
        bearerSelect.appendChild(option);
    });
    
    console.log('Bearers dropdown populated with', bearers.length, 'bearers');
}

function getCurrentEditingContainerKey() {
    const record = demurrageRecords.find(r => r.id === currentDemurrageId);
    if (!record) return null;
    return `${record.container_type}_${record.container_id}`;
}

function renderDemurrageTable() {
    const tableBody = document.querySelector('#demurrageTable tbody');
    const noContainersDiv = document.getElementById('noContainersForDemurrage');
    const tableContainer = document.getElementById('demurrageTableContainer');
    const addBtn = document.getElementById('addDemurrageBtn');

    if (!tableBody) return;

    // Check if no containers exist
    if (containers.length === 0) {
        noContainersDiv.style.display = 'block';
        tableContainer.style.display = 'none';
        addBtn.disabled = true;
        return;
    } else {
        noContainersDiv.style.display = 'none';
        tableContainer.style.display = 'block';
        addBtn.disabled = false;
    }

    tableBody.innerHTML = '';

    if (demurrageRecords.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="8" class="text-center text-muted">
                    <i class="ri-inbox-line fs-2 mb-2"></i>
                    <p class="mb-0">No demurrage records found</p>
                </td>
            </tr>
        `;
        return;
    }

    // Updated table rendering with View button
    demurrageRecords.forEach(record => {
        // Bearer information
        let bearerInfo = '';
        if (record.bearer_name || record.bearing_percentage !== null) {
            const bearerName = record.bearer_name || 'Not specified';
            const percentage = record.bearing_percentage !== null ? `${record.bearing_percentage}%` : '';
            
            if (percentage) {
                bearerInfo = `
                    <div>
                        <small class="text-muted">Bearer:</small> ${bearerName}<br>
                        <small class="text-muted">Bearing:</small> <span class="badge bg-info-subtle text-info">${percentage}</span>
                    </div>
                `;
            } else {
                bearerInfo = `<div><small class="text-muted">Bearer:</small> ${bearerName}</div>`;
            }
        } else {
            bearerInfo = '<span class="text-muted">-</span>';
        }

        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${record.container_number}</td>
            <td>${formatDate(record.demurrage_date)}</td>
            <td>${record.reason_name}</td>
            <td>${record.currency_code}</td>
            <td class="text-end">${formatAmount(record.amount)}</td>
            <td>${bearerInfo}</td>
            <td>
                <div class="d-flex gap-1">
                    <button class="btn btn-outline-info view-demurrage-btn btn-sm" data-demurrage-id="${record.id}" title="View Details" type="button">
                        <i class="ri-eye-line"></i>
                    </button>
                    <button class="btn btn-outline-primary edit-demurrage-btn btn-sm" data-demurrage-id="${record.id}" title="Edit" type="button">
                        <i class="ri-edit-line"></i>
                    </button>
                    <button class="btn btn-outline-danger delete-demurrage-btn btn-sm" data-demurrage-id="${record.id}" title="Delete" type="button">
                        <i class="ri-delete-bin-line"></i>
                    </button>
                </div>
            </td>
        `;
        tableBody.appendChild(row);
    });

    addTableEventListeners();
}

// Update addTableEventListeners function
function addTableEventListeners() {
    const viewButtons = document.querySelectorAll('.view-demurrage-btn');
    const editButtons = document.querySelectorAll('.edit-demurrage-btn');
    const deleteButtons = document.querySelectorAll('.delete-demurrage-btn');

    // NEW: View button event listeners
    viewButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            const demurrageId = parseInt(this.dataset.demurrageId);
            viewDemurrageDetails(demurrageId);
        });
    });

    editButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            const demurrageId = parseInt(this.dataset.demurrageId);
            editDemurrage(demurrageId);
        });
    });

    deleteButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            const demurrageId = parseInt(this.dataset.demurrageId);
            deleteDemurrage(demurrageId);
        });
    });
}

// NEW: View demurrage details function
function viewDemurrageDetails(demurrageId) {
    console.log('Viewing demurrage details for ID:', demurrageId);
    
    // Show loading
    Swal.fire({
        title: 'Loading Details...',
        html: '<div class="spinner-border text-primary" role="status"></div>',
        showConfirmButton: false,
        allowOutsideClick: false
    });
    
    fetch(`/masters/api/demurrage/${demurrageId}/details`)
        .then(response => response.json())
        .then(data => {
            Swal.close();
            if (data.success) {
                showDemurrageDetailsModal(data.data);
            } else {
                Swal.fire('Error', data.message, 'error');
            }
        })
        .catch(error => {
            Swal.close();
            console.error('Error loading demurrage details:', error);
            Swal.fire('Error', 'Failed to load demurrage details', 'error');
        });
}

function updateTotalAmount(totalAmount) {
    const totalElement = document.getElementById('totalDemurrageAmount');
    if (totalElement) {
        totalElement.textContent = formatAmount(totalAmount || 0);
    }
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-GB');
}

function formatAmount(amount) {
    return parseFloat(amount || 0).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function initializeDemurrageModalTabs() {
    const demurrageModal = document.getElementById('demurrageModal');
    if (!demurrageModal) return;

    demurrageModal.addEventListener('shown.bs.modal', function() {
        console.log('Demurrage modal opened, initializing tabs...');
        
        const detailsTabLink = demurrageModal.querySelector('a[href="#demurrage-details"]');
        const detailsTabPane = demurrageModal.querySelector('#demurrage-details');
        
        if (detailsTabLink && detailsTabPane) {
            demurrageModal.querySelectorAll('.nav-link').forEach(link => {
                link.classList.remove('active');
                link.setAttribute('aria-selected', 'false');
            });
            
            demurrageModal.querySelectorAll('.tab-pane').forEach(pane => {
                pane.classList.remove('active', 'show');
            });
            
            detailsTabLink.classList.add('active');
            detailsTabLink.setAttribute('aria-selected', 'true');
            detailsTabPane.classList.add('active', 'show');
            
            console.log('Details tab activated successfully');
        }
    });

    demurrageModal.addEventListener('show.bs.modal', function() {
        setTimeout(() => {
            const detailsTabLink = demurrageModal.querySelector('a[href="#demurrage-details"]');
            const detailsTabPane = demurrageModal.querySelector('#demurrage-details');
            
            if (detailsTabLink && detailsTabPane) {
                detailsTabLink.classList.add('active');
                detailsTabLink.setAttribute('aria-selected', 'true');
                detailsTabPane.classList.add('active', 'show');
            }
        }, 100);
    });
}

function openDemurrageModal(recordId = null) {
    console.log('openDemurrageModal called with:', recordId, typeof recordId);
    
    if (!dataLoaded) {
        console.log('Data not loaded yet, loading now...');
        loadDemurrageData().then(() => {
            openDemurrageModal(recordId);
        }).catch(error => {
            console.error('Error loading data:', error);
            Swal.fire('Error', 'Failed to load required data', 'error');
        });
        return;
    }

    const modal = new bootstrap.Modal(document.getElementById('demurrageModal'));
    const modalTitle = document.getElementById('demurrageModalTitle');
    const saveBtn = document.getElementById('saveDemurrageBtn');

    resetDemurrageForm();

    if (recordId && typeof recordId === 'number') {
        isEditingDemurrage = true;
        currentDemurrageId = recordId;
        console.log('Set currentDemurrageId to:', currentDemurrageId, typeof currentDemurrageId);    
        modalTitle.textContent = 'Edit Demurrage';
        saveBtn.innerHTML = '<i class="ri-save-line me-1"></i>Update Demurrage';
        
        const record = demurrageRecords.find(r => r.id === recordId);
        if (record) {
            populateFormForEdit(record);
        } else {
            console.error('Record not found for ID:', recordId);
            Swal.fire('Error', 'Demurrage record not found', 'error');
            return;
        }
    } else {
        isEditingDemurrage = false;
        currentDemurrageId = null;
        console.log('Add mode - currentDemurrageId set to null');
        modalTitle.textContent = 'Add Demurrage';
        saveBtn.innerHTML = '<i class="ri-save-line me-1"></i>Save Demurrage';
        
        document.getElementById('demurrageDate').value = new Date().toISOString().split('T')[0];
    }

    modal.show();
}

function populateFormForEdit(record) {
    document.getElementById('demurrageId').value = record.id;
    document.getElementById('containerId').value = `${record.container_type}_${record.container_id}`;
    document.getElementById('demurrageDate').value = record.demurrage_date;
    document.getElementById('demurrageAmount').value = record.amount;
    document.getElementById('currencyId').value = record.currency_id;
    document.getElementById('reasonId').value = record.reason_id;
    
    // NEW: Populate bearer fields
    if (record.bearing_percentage !== null) {
        document.getElementById('bearingPercentage').value = record.bearing_percentage;
    }
    if (record.bearer_id) {
        document.getElementById('bearerId').value = record.bearer_id;
    }
    
    console.log('Form populated for edit with record:', record.id);
}

function resetDemurrageForm() {
    const form = document.getElementById('demurrageForm');
    if (form) {
        form.reset();
        form.classList.remove('was-validated');
    }
    
    document.getElementById('demurrageId').value = '';
    isEditingDemurrage = false;
    currentDemurrageId = null;
    
    document.getElementById('demurrageDate').value = new Date().toISOString().split('T')[0];
    
    console.log('Form reset - currentDemurrageId set to null');
}

function handleDemurrageSubmit(event) {
    event.preventDefault();
    console.log('handleDemurrageSubmit - isEditingDemurrage:', isEditingDemurrage);
    console.log('handleDemurrageSubmit - currentDemurrageId:', currentDemurrageId, typeof currentDemurrageId);

    const form = event.target;
    
    if (!form.checkValidity()) {
        form.classList.add('was-validated');
        return;
    }

    const formData = new FormData(form);
    const containerSelect = document.getElementById('containerId');
    const selectedOption = containerSelect.options[containerSelect.selectedIndex];
    
    if (!selectedOption || !selectedOption.dataset.containerId) {
        Swal.fire('Error', 'Please select a valid container', 'error');
        return;
    }

    const data = {
        shipment_id: parseInt(formData.get('shipment_id')),
        container_id: parseInt(selectedOption.dataset.containerId),
        container_type: selectedOption.dataset.containerType,
        demurrage_date: formData.get('demurrage_date'),
        amount: parseFloat(formData.get('amount')),
        currency_id: parseInt(formData.get('currency_id')),
        reason_id: parseInt(formData.get('reason_id'))
    };

    // NEW: Add bearer fields to data
    const bearingPercentage = formData.get('bearing_percentage');
    const bearerId = formData.get('bearer_id');
    
    if (bearingPercentage && bearingPercentage.trim() !== '') {
        data.bearing_percentage = parseFloat(bearingPercentage);
    }
    
    if (bearerId && bearerId.trim() !== '') {
        data.bearer_id = parseInt(bearerId);
    }

    const saveBtn = document.getElementById('saveDemurrageBtn');
    const originalText = saveBtn.innerHTML;
    saveBtn.innerHTML = '<i class="ri-loader-4-line spinner-border spinner-border-sm me-1"></i>Saving...';
    saveBtn.disabled = true;

    const url = isEditingDemurrage && currentDemurrageId ? `/masters/api/demurrage/${currentDemurrageId}` : '/masters/api/demurrage';
    console.log('API URL:', url);
    console.log('Request data:', data);
    
    const method = isEditingDemurrage ? 'PUT' : 'POST';

    fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => {
        console.log('Response status:', response.status);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log('Response data:', data);
        if (data.success) {
            const modal = bootstrap.Modal.getInstance(document.getElementById('demurrageModal'));
            modal.hide();
            
            Swal.fire({
                icon: 'success',
                title: 'Success!',
                text: data.message,
                timer: 2000,
                showConfirmButton: false
            });
            
            loadDemurrageData();
        } else {
            throw new Error(data.message);
        }
    })
    .catch(error => {
        console.error('Error saving demurrage:', error);
        Swal.fire('Error', error.message || 'Failed to save demurrage record', 'error');
    })
    .finally(() => {
        saveBtn.innerHTML = originalText;
        saveBtn.disabled = false;
    });
}

function editDemurrage(demurrageId) {
    console.log('editDemurrage called with:', demurrageId, typeof demurrageId);
    
    if (typeof demurrageId !== 'number' || isNaN(demurrageId)) {
        console.error('Invalid demurrage ID:', demurrageId);
        Swal.fire('Error', 'Invalid demurrage record selected', 'error');
        return;
    }
    
    openDemurrageModal(demurrageId);
}

function deleteDemurrage(demurrageId) {
    console.log('deleteDemurrage called with:', demurrageId, typeof demurrageId);
    
    if (typeof demurrageId !== 'number' || isNaN(demurrageId)) {
        console.error('Invalid demurrage ID:', demurrageId);
        Swal.fire('Error', 'Invalid demurrage record selected', 'error');
        return;
    }
    
    const record = demurrageRecords.find(r => r.id === demurrageId);
    if (!record) {
        console.error('Record not found for ID:', demurrageId);
        Swal.fire('Error', 'Demurrage record not found', 'error');
        return;
    }

    Swal.fire({
        title: 'Delete Demurrage Record?',
        text: `Are you sure you want to delete the demurrage record for container ${record.container_number}?`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        cancelButtonColor: '#3085d6',
        confirmButtonText: 'Yes, delete it!',
        cancelButtonText: 'Cancel'
    }).then((result) => {
        if (result.isConfirmed) {
            performDeleteDemurrage(demurrageId);
        }
    });
}

function performDeleteDemurrage(demurrageId) {
    console.log('performDeleteDemurrage called with:', demurrageId);
    
    fetch(`/masters/api/demurrage/${demurrageId}`, {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => {
        console.log('Delete response status:', response.status);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log('Delete response data:', data);
        if (data.success) {
            Swal.fire({
                icon: 'success',
                title: 'Deleted!',
                text: data.message,
                timer: 2000,
                showConfirmButton: false
            });
            
            loadDemurrageData();
        } else {
            throw new Error(data.message);
        }
    })
    .catch(error => {
        console.error('Error deleting demurrage:', error);
        Swal.fire('Error', error.message || 'Failed to delete demurrage record', 'error');
    });
}

// --- Attachments Tab Logic (unchanged from original) ---
let currentDemurrageAttachmentId = null;
let demurrageAttachments = [];

document.addEventListener('DOMContentLoaded', function() {
    // Attachments tab events
    const addAttachmentBtn = document.getElementById('addAttachmentBtn');
    const cancelAttachmentBtn = document.getElementById('cancelAttachmentBtn');
    const saveAttachmentBtn = document.getElementById('saveAttachmentBtn');
    const attachmentsTabLink = document.querySelector('a[href="#demurrage-attachments"]');

    if (addAttachmentBtn) {
        addAttachmentBtn.addEventListener('click', showAttachmentForm);
    }
    if (cancelAttachmentBtn) {
        cancelAttachmentBtn.addEventListener('click', hideAttachmentForm);
    }
    if (saveAttachmentBtn) {
        saveAttachmentBtn.addEventListener('click', saveAttachment);
    }
    if (attachmentsTabLink) {
        attachmentsTabLink.addEventListener('shown.bs.tab', function() {
            const demurrageId = document.getElementById('demurrageId').value;
            if (demurrageId) {
                loadDemurrageAttachments(demurrageId);
            }
        });
    }
});

// Rest of the attachment functions remain the same...
function showAttachmentForm() {
    document.getElementById('attachmentForm').style.display = 'block';
    document.getElementById('addAttachmentBtn').style.display = 'none';
    clearAttachmentForm();
}

function hideAttachmentForm() {
    document.getElementById('attachmentForm').style.display = 'none';
    document.getElementById('addAttachmentBtn').style.display = 'inline-block';
    clearAttachmentForm();
    currentDemurrageAttachmentId = null;
    
    const formTitle = document.querySelector('#attachmentForm .card-body h6') || 
                     document.querySelector('#attachmentForm h6');
    if (formTitle) {
        formTitle.textContent = 'Add Attachment';
    }
    
    const saveBtn = document.getElementById('saveAttachmentBtn');
    saveBtn.innerHTML = '<i class="ri-save-line me-1"></i>Save Attachment';
    
    const fileNote = document.getElementById('fileUpdateNote');
    if (fileNote) {
        fileNote.style.display = 'none';
    }
}

function clearAttachmentForm() {
    document.getElementById('attachmentFile').value = '';
    document.getElementById('attachmentDate').value = '';
    document.getElementById('attachmentComment').value = '';
    
    const fileNote = document.getElementById('fileUpdateNote');
    if (fileNote) {
        fileNote.style.display = 'none';
    }
}

function saveAttachment() {
    const demurrageId = document.getElementById('demurrageId').value;
    if (!demurrageId) {
        Swal.fire('Error', 'Please save the demurrage details first.', 'error');
        return;
    }
    
    const fileInput = document.getElementById('attachmentFile');
    const dateInput = document.getElementById('attachmentDate');
    const commentInput = document.getElementById('attachmentComment');

    if (!fileInput.files.length && !currentDemurrageAttachmentId) {
        Swal.fire('Error', 'Please select a file.', 'error');
        return;
    }
    if (!dateInput.value) {
        Swal.fire('Error', 'Please select a date.', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('date', dateInput.value);
    formData.append('comment', commentInput.value);
    if (fileInput.files.length) {
        formData.append('file', fileInput.files[0]);
    }

    let url, method;
    if (currentDemurrageAttachmentId) {
        url = `/masters/demurrage/${demurrageId}/update-attachment/${currentDemurrageAttachmentId}`;
        method = 'POST';
    } else {
        url = `/masters/demurrage/${demurrageId}/upload-attachment`;
        method = 'POST';
    }

    const saveBtn = document.getElementById('saveAttachmentBtn');
    const originalText = saveBtn.innerHTML;
    saveBtn.innerHTML = '<i class="ri-loader-4-line spinner-border spinner-border-sm me-1"></i>Saving...';
    saveBtn.disabled = true;

    fetch(url, {
        method: method,
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            Swal.fire('Success', data.message, 'success');
            hideAttachmentForm();
            loadDemurrageAttachments(demurrageId);
        } else {
            Swal.fire('Error', data.error || data.message, 'error');
        }
    })
    .catch(error => {
        console.error('Error saving attachment:', error);
        Swal.fire('Error', 'Failed to save attachment', 'error');
    })
    .finally(() => {
        saveBtn.innerHTML = originalText;
        saveBtn.disabled = false;
    });
}


function loadDemurrageAttachments(demurrageId) {
    fetch(`/masters/api/demurrage/${demurrageId}/attachments`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                demurrageAttachments = data.data;
                renderAttachmentsTable();
            } else {
                console.error('Error loading attachments:', data.message);
            }
        })
        .catch(error => {
            console.error('Error loading attachments:', error);
        });
}


function renderAttachmentsTable() {
    const tbody = document.querySelector('#attachmentsTable tbody');
    tbody.innerHTML = '';
    
    if (!demurrageAttachments.length) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" class="text-center text-muted py-4">
                    <i class="ri-attachment-line fs-2 mb-2 d-block"></i>
                    <p class="mb-0">No attachments found</p>
                </td>
            </tr>
        `;
        return;
    }
    
    demurrageAttachments.forEach(att => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>
                <div class="d-flex align-items-center">
                    <i class="ri-file-text-line fs-16 me-2 text-primary"></i>
                    <div>
                        <div class="fw-medium">${att.file_name}</div>
                        <small class="text-muted">Uploaded: ${att.created_at || 'Unknown'}</small>
                    </div>
                </div>
            </td>
            <td>${formatDate(att.date)}</td>
            <td>${att.comment || '-'}</td>
            <td>
                <div class="d-flex gap-1">
                    <button class="btn btn-sm btn-info" onclick="viewAttachment(${att.id})" title="View Attachment">
                        <i class="ri-eye-line"></i>
                    </button>
                    <button class="btn btn-sm btn-warning" onclick="editAttachment(${att.id})" title="Edit">
                        <i class="ri-edit-line"></i>
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="deleteAttachment(${att.id})" title="Delete">
                        <i class="ri-delete-bin-line"></i>
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

window.viewAttachment = function(attachmentId) {
    console.log('Viewing demurrage attachment ID:', attachmentId);
    // Use the new view route pattern
    window.open(`/masters/view-demurrage-document/${attachmentId}`, '_blank');
};


window.editAttachment = function(id) {
    const att = demurrageAttachments.find(a => a.id === id);
    if (!att) {
        console.error('Attachment not found:', id);
        return;
    }
    
    currentDemurrageAttachmentId = id;
    document.getElementById('attachmentForm').style.display = 'block';
    document.getElementById('addAttachmentBtn').style.display = 'none';
    document.getElementById('attachmentDate').value = att.date;
    document.getElementById('attachmentComment').value = att.comment || '';
    
    // Update form title and button text for editing
    const formTitle = document.querySelector('#attachmentForm .card-body h6') || 
                     document.querySelector('#attachmentForm h6');
    if (formTitle) {
        formTitle.textContent = 'Edit Attachment';
    }
    
    const saveBtn = document.getElementById('saveAttachmentBtn');
    saveBtn.innerHTML = '<i class="ri-save-line me-1"></i>Update Attachment';
    
    // Add note about file re-upload
    let fileNote = document.getElementById('fileUpdateNote');
    if (!fileNote) {
        fileNote = document.createElement('small');
        fileNote.id = 'fileUpdateNote';
        fileNote.className = 'text-muted';
        fileNote.innerHTML = '<i class="ri-information-line"></i> Leave file empty to keep current file, or select a new file to replace it.';
        
        const fileInput = document.getElementById('attachmentFile');
        fileInput.parentNode.appendChild(fileNote);
    }
    fileNote.style.display = 'block';
    
    // File input is left blank for security; user can re-upload if needed
    document.getElementById('attachmentFile').value = '';
};

// Update the deleteAttachment function
window.deleteAttachment = function(attachmentId) {
    const demurrageId = document.getElementById('demurrageId').value;
    const att = demurrageAttachments.find(a => a.id === attachmentId);
    if (!att) {
        console.error('Attachment not found:', attachmentId);
        return;
    }
    
    Swal.fire({
        title: 'Delete Attachment?',
        text: `Are you sure you want to delete "${att.file_name}"?`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        cancelButtonColor: '#3085d6',
        confirmButtonText: 'Yes, delete it!',
        cancelButtonText: 'Cancel'
    }).then(result => {
        if (result.isConfirmed) {
            // Use the new delete route pattern
            fetch(`/masters/demurrage/${demurrageId}/delete-attachment/${attachmentId}`, { 
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    Swal.fire('Deleted!', data.message, 'success');
                    loadDemurrageAttachments(demurrageId);
                } else {
                    Swal.fire('Error', data.error || data.message, 'error');
                }
            })
            .catch(error => {
                console.error('Error deleting attachment:', error);
                Swal.fire('Error', 'Failed to delete attachment', 'error');
            });
        }
    });
};




// Add this function to load demurrage from date
function loadDemurrageFromDate(shipmentId) {
    return fetch(`/masters/api/demurrage/shipment/${shipmentId}/demurrage-from`)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.data.demurrage_from) {
                demurrageFromDate = data.data.demurrage_from;
                console.log('Demurrage from date loaded:', demurrageFromDate);
            } else {
                demurrageFromDate = null;
                console.warn('No demurrage from date found for shipment');
            }
        })
        .catch(error => {
            console.error('Error loading demurrage from date:', error);
            demurrageFromDate = null;
        });
}

// Update the loadDemurrageData function to include demurrage from date
function loadDemurrageData() {
    const shipmentId = document.getElementById('shipmentId').value;
    if (!shipmentId) return;

    console.log('Loading demurrage data for shipment:', shipmentId);

    // Reset global variables before loading
    containers = [];
    reasons = [];
    bearers = [];
    demurrageRecords = [];

    Promise.all([
        loadContainers(shipmentId),
        loadReasons(),
        loadBearers(),
        loadDemurrageRecords(shipmentId),
        loadDemurrageFromDate(shipmentId) // Add this
    ]).then(() => {
        dataLoaded = true;
        console.log('All demurrage data loaded successfully');
        renderDemurrageTable();
        setupAutoCalculation(); // Add this
    }).catch(error => {
        console.error('Error loading demurrage data:', error);
        dataLoaded = false;
        Swal.fire('Error', 'Failed to load demurrage data', 'error');
    });
}

// Add auto-calculation setup function
function setupAutoCalculation() {
    const calculateBtn = document.getElementById('calculateRateBtn');
    const manualOverrideCheck = document.getElementById('manualOverride');
    const containerSelect = document.getElementById('containerId');
    const reasonSelect = document.getElementById('reasonId');
    const dateInput = document.getElementById('demurrageDate');
    const amountInput = document.getElementById('demurrageAmount');
    const currencySelect = document.getElementById('currencyId');

    // Calculate button click
    if (calculateBtn) {
        calculateBtn.addEventListener('click', performRateCalculation);
    }

    // Manual override toggle
    if (manualOverrideCheck) {
        manualOverrideCheck.addEventListener('change', function() {
            autoCalculationEnabled = !this.checked;
            console.log('Auto calculation enabled:', autoCalculationEnabled);
            
            if (this.checked) {
                // Hide calculation details when manual override is enabled
                hideCalculationDetails();
            }
        });
    }

    // Auto-trigger calculation on field changes
    [containerSelect, reasonSelect, dateInput].forEach(element => {
        if (element) {
            element.addEventListener('change', function() {
                if (autoCalculationEnabled && this.value) {
                    setTimeout(performRateCalculation, 300); // Small delay to ensure all values are set
                }
            });
        }
    });
}

// Main rate calculation function
function performRateCalculation() {
    const shipmentId = document.getElementById('shipmentId').value;
    const containerSelect = document.getElementById('containerId');
    const reasonSelect = document.getElementById('reasonId');
    const dateInput = document.getElementById('demurrageDate');
    const amountInput = document.getElementById('demurrageAmount');
    const currencySelect = document.getElementById('currencyId');
    const calculateBtn = document.getElementById('calculateRateBtn');

    // Validate required fields
    if (!shipmentId) {
        showCalculationError('Shipment ID is required');
        return;
    }

    if (!demurrageFromDate) {
        showCalculationError('This shipment is not in demurrage.');
        return;
    }

    if (!containerSelect.value) {
        showCalculationError('Please select a container');
        return;
    }

    if (!reasonSelect.value) {
        showCalculationError('Please select a reason');
        return;
    }

    if (!dateInput.value) {
        showCalculationError('Please select a demurrage date');
        return;
    }

    // Validate date logic
    const demurrageDate = new Date(dateInput.value);
    const fromDate = new Date(demurrageFromDate);
    
    if (demurrageDate <= fromDate) {
        showCalculationError('Demurrage date must be after the demurrage from date');
        return;
    }

    // Extract container data
    const selectedOption = containerSelect.options[containerSelect.selectedIndex];
    const containerId = selectedOption.dataset.containerId;
    const containerType = selectedOption.dataset.containerType;

    // Prepare request data
    const requestData = {
        shipment_id: parseInt(shipmentId),
        container_id: parseInt(containerId),
        container_type: containerType,
        reason_id: parseInt(reasonSelect.value),
        demurrage_date: dateInput.value
    };

    // Show loading state
    if (calculateBtn) {
        calculateBtn.disabled = true;
        calculateBtn.innerHTML = '<i class="ri-loader-4-line spinner-border spinner-border-sm"></i> Calculating...';
    }

    // Make API call
    fetch('/masters/api/demurrage/calculate-rate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Update amount field
            amountInput.value = data.data.calculated_amount;
            
            // Update currency if different
            if (currencySelect && data.data.currency_id) {
                currencySelect.value = data.data.currency_id;
            }
            
            // Show calculation details
            showCalculationDetails(data.data);
            
            console.log('Rate calculation successful:', data.data);
        } else {
            showCalculationError(data.message);
        }
    })
    .catch(error => {
        console.error('Error calculating rate:', error);
        showCalculationError('Failed to calculate rate. Please try again.');
    })
    .finally(() => {
        // Reset button state
        if (calculateBtn) {
            calculateBtn.disabled = false;
            calculateBtn.innerHTML = '<i class="ri-calculator-line"></i> Calculate';
        }
    });
}

// Show calculation details
function showCalculationDetails(calculationData) {
    const detailsPanel = document.getElementById('calculationDetails');
    const breakdownDiv = document.getElementById('calculationBreakdown');
    
    if (!detailsPanel || !breakdownDiv) return;

    const details = calculationData.calculation_details;
    
    let breakdownHtml = `
        <div class="row mb-2">
            <div class="col-6"><small><strong>From Date:</strong></div>
            <div class="col-6"><small>${details.demurrage_from}</small></div>
        </div>
        <div class="row mb-2">
            <div class="col-6"><small><strong>To Date:</strong></div>
            <div class="col-6"><small>${details.demurrage_date}</small></div>
        </div>
        <div class="row mb-2">
            <div class="col-6"><small><strong>Total Days:</strong></div>
            <div class="col-6"><small>${details.total_days}</small></div>
        </div>
        <div class="row mb-2">
            <div class="col-6"><small><strong>Chargeable Days:</strong></div>
            <div class="col-6"><small>${details.chargeable_days}</small></div>
        </div>
    `;

    if (details.excluded_days > 0) {
        breakdownHtml += `
            <div class="row mb-2">
                <div class="col-6"><small><strong>Excluded Days:</strong></div>
                <div class="col-6"><small>${details.excluded_days}</small></div>
            </div>
        `;
    }

    breakdownHtml += `
        <div class="row mb-2">
            <div class="col-6"><small><strong>Rate Card:</strong></div>
            <div class="col-6"><small>${details.rate_card_name}</small></div>
        </div>
        <hr class="my-2">
        <h6 class="text-primary mb-2">Tier Breakdown:</h6>
    `;

    details.tier_breakdown.forEach(tier => {
        breakdownHtml += `
            <div class="row mb-1">
                <div class="col-4"><small>Tier ${tier.tier}:</small></div>
                <div class="col-3"><small>${tier.days} days</small></div>
                <div class="col-5"><small>@${formatAmount(tier.rate)} = ${formatAmount(tier.amount)}</small></div>
            </div>
        `;
    });

    breakdownHtml += `
        <hr class="my-2">
        <div class="row">
            <div class="col-6"><strong>Total Amount:</strong></div>
            <div class="col-6"><strong>${calculationData.currency_code} ${formatAmount(calculationData.calculated_amount)}</strong></div>
        </div>
    `;

    breakdownDiv.innerHTML = breakdownHtml;
    detailsPanel.style.display = 'block';
}

// Hide calculation details
function hideCalculationDetails() {
    const detailsPanel = document.getElementById('calculationDetails');
    if (detailsPanel) {
        detailsPanel.style.display = 'none';
    }
}

// Show calculation error
function showCalculationError(message) {
    const detailsPanel = document.getElementById('calculationDetails');
    const breakdownDiv = document.getElementById('calculationBreakdown');
    
    if (detailsPanel && breakdownDiv) {
        breakdownDiv.innerHTML = `
            <div class="alert alert-danger alert-sm mb-0">
                <i class="ri-error-warning-line me-1"></i>
                ${message}
            </div>
        `;
        detailsPanel.style.display = 'block';
    } else {
        // Fallback to toast or alert
        Swal.fire({
            icon: 'warning',
            title: 'Calculation Error',
            text: message,
            timer: 3000,
            showConfirmButton: false
        });
    }
}

// Update the resetDemurrageForm function
function resetDemurrageForm() {
    const form = document.getElementById('demurrageForm');
    if (form) {
        form.reset();
        form.classList.remove('was-validated');
    }
    
    document.getElementById('demurrageId').value = '';
    isEditingDemurrage = false;
    currentDemurrageId = null;
    
    document.getElementById('demurrageDate').value = new Date().toISOString().split('T')[0];
    
    // Reset calculation state
    const manualOverrideCheck = document.getElementById('manualOverride');
    if (manualOverrideCheck) {
        manualOverrideCheck.checked = false;
    }
    autoCalculationEnabled = true;
    
    hideCalculationDetails();
    
    console.log('Form reset - currentDemurrageId set to null');
}

// Helper function for amount formatting (if not already exists)
function formatAmount(amount) {
    return parseFloat(amount || 0).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

// NEW: Show demurrage details modal
function showDemurrageDetailsModal(demurrageData) {
    const modal = new bootstrap.Modal(document.getElementById('demurrageDetailsModal'));
    const contentDiv = document.getElementById('demurrageDetailsContent');
    
    // Generate invoice-style content
    const content = generateDemurrageInvoiceContent(demurrageData);
    contentDiv.innerHTML = content;
    
    // Setup print and download handlers
    setupModalHandlers(demurrageData);
    
    modal.show();
}

// NEW: Generate invoice-style content
function generateDemurrageInvoiceContent(data) {
    const currentDate = new Date().toLocaleDateString();
    
    return `
        <div id="demurrageInvoiceContent" class="invoice-content">
            <!-- Header -->
            <div class="row mb-4">
                <div class="col-12">
                    <div class="text-center border-bottom pb-3">
                        <h3 class="text-primary mb-1">DEMURRAGE CALCULATION STATEMENT</h3>
                        <p class="text-muted mb-0">Detailed Breakdown of Charges</p>
                    </div>
                </div>
            </div>
            
            <!-- Shipment & Container Information -->
            <div class="row mb-4">
                <div class="col-md-6">
                    <div class="card bg-light">
                        <div class="card-body p-3">
                            <h6 class="card-title text-primary mb-3">Shipment Information</h6>
                            <table class="table table-sm table-borderless mb-0">
                                <tr>
                                    <td><strong>Import ID:</strong></td>
                                    <td>${data.shipment_info.import_id}</td>
                                </tr>
                                <tr>
                                    <td><strong>Customer:</strong></td>
                                    <td>${data.shipment_info.customer}</td>
                                </tr>
                                <tr>
                                    <td><strong>BL Number:</strong></td>
                                    <td>${data.shipment_info.bl_no}</td>
                                </tr>
                            </table>
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="card bg-light">
                        <div class="card-body p-3">
                            <h6 class="card-title text-primary mb-3">Container Information</h6>
                            <table class="table table-sm table-borderless mb-0">
                                <tr>
                                    <td><strong>Container #:</strong></td>
                                    <td>${data.container_info.container_number}</td>
                                </tr>
                                <tr>
                                    <td><strong>Size:</strong></td>
                                    <td>${data.container_info.size}</td>
                                </tr>
                                <tr>
                                    <td><strong>Type:</strong></td>
                                    <td>${data.container_info.type}</td>
                                </tr>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Calculation Summary -->
            <div class="row mb-4">
                <div class="col-12">
                    <div class="card border-primary">
                        <div class="card-header bg-primary text-white">
                            <h6 class="card-title mb-0">Calculation Summary</h6>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-md-4">
                                    <div class="text-center p-3 bg-light rounded">
                                        <h4 class="text-primary mb-1">${data.calculation_info.total_days}</h4>
                                        <p class="text-muted mb-0">Total Days</p>
                                        <small class="text-muted">${data.calculation_info.demurrage_from} to ${data.calculation_info.demurrage_date}</small>
                                    </div>
                                </div>
                                <div class="col-md-4">
                                    <div class="text-center p-3 bg-light rounded">
                                        <h4 class="text-success mb-1">${data.calculation_info.chargeable_days}</h4>
                                       <p class="text-muted mb-0">Chargeable Days</p>
                                       <small class="text-muted">Excluding ${data.calculation_info.excluded_days} days</small>
                                   </div>
                               </div>
                               <div class="col-md-4">
                                   <div class="text-center p-3 bg-light rounded">
                                       <h4 class="text-danger mb-1">${data.calculation_info.currency} ${formatAmount(data.calculation_info.total_amount)}</h4>
                                       <p class="text-muted mb-0">Total Amount</p>
                                       <small class="text-muted">Rate Card: ${data.calculation_info.rate_card}</small>
                                   </div>
                               </div>
                           </div>
                           
                           <div class="row mt-3">
                               <div class="col-md-6">
                                   <p class="mb-1"><strong>Reason:</strong> ${data.calculation_info.reason}</p>
                                   <p class="mb-0"><strong>Currency:</strong> ${data.calculation_info.currency}</p>
                               </div>
                               <div class="col-md-6">
                                   ${data.bearer_info.bearer_name ? `
                                       <p class="mb-1"><strong>Bearer:</strong> ${data.bearer_info.bearer_name}</p>
                                       ${data.bearer_info.bearing_percentage ? `<p class="mb-0"><strong>Bearing:</strong> ${data.bearer_info.bearing_percentage}%</p>` : ''}
                                   ` : ''}
                               </div>
                           </div>
                       </div>
                   </div>
               </div>
           </div>
           
           <!-- Detailed Tier Breakdown -->
           <div class="row mb-4">
               <div class="col-12">
                   <div class="card">
                       <div class="card-header bg-warning text-dark">
                           <h6 class="card-title mb-0">Detailed Tier Breakdown</h6>
                       </div>
                       <div class="card-body p-0">
                           <div class="table-responsive">
                               <table class="table table-bordered mb-0">
                                   <thead class="table-light">
                                       <tr>
                                           <th class="text-center">Tier</th>
                                           <th>Day Range</th>
                                           <th>Date Range</th>
                                           <th class="text-center">Days</th>
                                           <th class="text-end">Rate/Day</th>
                                           <th class="text-end">Amount</th>
                                       </tr>
                                   </thead>
                                   <tbody>
                                       ${data.tier_breakdown.map(tier => `
                                           <tr>
                                               <td class="text-center">
                                                   <span class="badge bg-primary">${tier.tier_name}</span>
                                               </td>
                                               <td>
                                                   <strong>${tier.day_range_display}</strong>
                                               </td>
                                               <td>
                                                   ${tier.start_date}${tier.end_date ? ` to ${tier.end_date}` : '+'}
                                               </td>
                                               <td class="text-center">
                                                   <span class="badge bg-info">${tier.days_in_tier}</span>
                                               </td>
                                               <td class="text-end">
                                                   ${data.calculation_info.currency} ${formatAmount(tier.rate_per_day)}
                                               </td>
                                               <td class="text-end">
                                                   <strong>${data.calculation_info.currency} ${formatAmount(tier.tier_amount)}</strong>
                                               </td>
                                           </tr>
                                       `).join('')}
                                   </tbody>
                                   <tfoot class="table-dark">
                                       <tr>
                                           <td colspan="5" class="text-end"><strong>TOTAL DEMURRAGE AMOUNT:</strong></td>
                                           <td class="text-end">
                                               <strong class="fs-5">${data.calculation_info.currency} ${formatAmount(data.calculation_info.total_amount)}</strong>
                                           </td>
                                       </tr>
                                   </tfoot>
                               </table>
                           </div>
                       </div>
                   </div>
               </div>
           </div>
           
           <!-- Footer -->
           <div class="row">
               <div class="col-12">
                   <div class="text-center text-muted border-top pt-3">
                       <p class="mb-1">This statement was generated on ${currentDate}</p>
                       <p class="mb-0">Demurrage ID: ${data.demurrage_id}</p>
                   </div>
               </div>
           </div>
       </div>
   `;
}

// NEW: Setup modal handlers for print and download
function setupModalHandlers(demurrageData) {
   // Print handler
   document.getElementById('printDemurrageBtn').onclick = function() {
       printDemurrageDetails();
   };
   
   // Download handler
   document.getElementById('downloadDemurrageBtn').onclick = function() {
       downloadDemurragePDF(demurrageData);
   };
}

// NEW: Print demurrage details
function printDemurrageDetails() {
   const printContent = document.getElementById('demurrageInvoiceContent').innerHTML;
   const originalContent = document.body.innerHTML;
   
   // Create print styles
   const printStyles = `
       <style>
           @media print {
               body { margin: 0; padding: 20px; font-family: Arial, sans-serif; }
               .invoice-content { max-width: 100%; }
               .card { border: 1px solid #ddd !important; margin-bottom: 20px; }
               .card-header { background-color: #f8f9fa !important; }
               .bg-primary { background-color: #0d6efd !important; color: white !important; }
               .bg-warning { background-color: #ffc107 !important; }
               .bg-light { background-color: #f8f9fa !important; }
               .table-bordered { border: 1px solid #dee2e6 !important; }
               .table-bordered td, .table-bordered th { border: 1px solid #dee2e6 !important; }
               .badge { display: inline-block; padding: 0.25em 0.5em; border-radius: 0.25rem; }
               .bg-primary.badge { background-color: #0d6efd !important; color: white !important; }
               .bg-info.badge { background-color: #0dcaf0 !important; color: black !important; }
               .text-primary { color: #0d6efd !important; }
               .text-success { color: #198754 !important; }
               .text-danger { color: #dc3545 !important; }
               .text-muted { color: #6c757d !important; }
               .border-top { border-top: 1px solid #dee2e6 !important; }
               .border-bottom { border-bottom: 1px solid #dee2e6 !important; }
           }
       </style>
   `;
   
   document.body.innerHTML = printStyles + '<div class="invoice-content">' + printContent + '</div>';
   window.print();
   document.body.innerHTML = originalContent;
   
   // Reload the page to restore functionality
   setTimeout(() => {
       location.reload();
   }, 100);
}

// NEW: Download demurrage as PDF
function downloadDemurragePDF(demurrageData) {
   // Show loading
   Swal.fire({
       title: 'Generating PDF...',
       html: '<div class="spinner-border text-primary" role="status"></div>',
       showConfirmButton: false,
       allowOutsideClick: false
   });
   
   // Create a hidden form to submit the data for PDF generation
   const form = document.createElement('form');
   form.method = 'POST';
   form.action = `/masters/api/demurrage/${demurrageData.demurrage_id}/download-pdf`;
   form.style.display = 'none';
   
   // Add CSRF token if available
   const csrfToken = document.querySelector('meta[name="csrf-token"]');
   if (csrfToken) {
       const csrfInput = document.createElement('input');
       csrfInput.type = 'hidden';
       csrfInput.name = 'csrf_token';
       csrfInput.value = csrfToken.getAttribute('content');
       form.appendChild(csrfInput);
   }
   
   document.body.appendChild(form);
   form.submit();
   document.body.removeChild(form);
   
   // Close loading after a delay
   setTimeout(() => {
       Swal.close();
   }, 2000);
}   















