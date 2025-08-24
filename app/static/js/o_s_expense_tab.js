/**
 * Expense Modal Handler
 * Handles adding, editing, and deleting expenses
 */
document.addEventListener('DOMContentLoaded', function() {
    // Get elements
    const expenseModal = document.getElementById('expenseModal');
    const expenseForm = document.querySelector('#expenseModal form');
    const addExpenseBtn1 = document.getElementById('addExpenseBtn1');
    const expenseIdField = document.getElementById('expenseId');
    const modalTitle = document.getElementById('expenseModalLabel');
    const saveButton = document.getElementById('saveExpense');
    const entryIdField = document.getElementById('shipmentIdForExpense');
    
    // Set entry ID if available from the page context
    if (entryIdField && !entryIdField.value) {
        const initialEntryId = extractEntryIdFromPage();
        if (initialEntryId) {
            entryIdField.value = initialEntryId;
            console.log(`Set initial entry ID to: ${initialEntryId}`);
        } else {
            console.warn("Could not determine initial entry ID");
        }
    }
    
    // Form calculation fields
    const valueInput = document.getElementById('expenseValue');
    const vatInput = document.getElementById('expenseVAT');
    const netAmountDisplay = document.getElementById('expenseNetAmount');
    const marginInput = document.getElementById('expenseMargin');
    const marginAmountInput = document.getElementById('expenseMarginAmount');
    const chargeableDisplay = document.getElementById('expenseChargeableAmount');
    
    // "Add Expense" button click handler
    if (addExpenseBtn1) {
        addExpenseBtn1.addEventListener('click', function() {
            openExpenseModal();
        });
    }
    
    // "Add Expense" from invoice modal
    const addExpenseBtnInvoice = document.getElementById('addExpenseBtn1');
    if (addExpenseBtnInvoice) {
        addExpenseBtnInvoice.addEventListener('click', function() {
            openExpenseModal();
        });
    }
    
    // Handle edit expense button clicks
    document.querySelectorAll('.edit-expense').forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            
            const expenseId = this.getAttribute('data-id');
            let entryId = entryIdField.value;
            
            // If entry ID is not valid, try to extract it
            if (!entryId || entryId === '{{ shipment.id }}' || isNaN(parseInt(entryId))) {
                entryId = extractEntryIdFromPage();
            }
            
            if (!entryId) {
                Swal.fire({
                    title: 'Error',
                    text: 'Could not determine entry ID. Please reload the page and try again.',
                    icon: 'error',
                    confirmButtonClass: 'btn btn-primary w-xs mt-2',
                    buttonsStyling: false
                });
                return;
            }
            
            console.log(`Editing expense ID: ${expenseId} for entry ID: ${entryId}`);
            
            // Fetch expense data and open modal
            fetchExpenseData(entryId, expenseId);
        });
    });
    
    // Handle delete expense form submissions
    document.querySelectorAll('form.delete-expense-form').forEach(form => {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const expenseId = this.getAttribute('data-expense-id');
            const chargedAmount = parseFloat(this.getAttribute('data-charged-amount')) || 0;
            const entryId = this.getAttribute('data-entry-id');

            if (chargedAmount > 0) {
                // Show warning if charged amount is not zero
                Swal.fire({
                    title: 'Cannot Delete',
                    text: 'This expense has settlements. Remove all invoices that reference this expense first.',
                    icon: 'warning',
                    confirmButtonClass: 'btn btn-primary w-xs mt-2',
                    buttonsStyling: false
                });
                return;
            }
            
            // Confirm delete with SweetAlert
            Swal.fire({
                title: 'Are you sure?',
                text: "You won't be able to revert this!",
                icon: 'warning',
                showCancelButton: true,
                confirmButtonText: 'Yes, delete it!',
                cancelButtonText: 'Cancel',
                confirmButtonClass: 'btn btn-danger w-xs me-2 mt-2',
                cancelButtonClass: 'btn btn-light w-xs mt-2',
                buttonsStyling: false,
                showCloseButton: true
            }).then((result) => {
                if (result.isConfirmed) {
                    // Submit the form for deletion
                    form.submit();
                }
            });
        });
    });
    
    // Setup expense calculation events
    setupExpenseCalculations();
    
    // Function to open the expense modal for creating new expense
    function openExpenseModal() {
        // Reset form
        if (expenseForm) expenseForm.reset();
        
        // Clear hidden fields
        if (expenseIdField) expenseIdField.value = '';
        
        // Find the ship_doc_entry_id
        let entryId = extractEntryId();
        
        // Validate that we have an entry_id
        if (!entryId) {
            console.error("Missing entry_id - this should never happen with the global variable set");
            // Show error to user
            Swal.fire({
                title: 'System Error',
                text: 'Could not determine entry ID. Please reload the page.',
                icon: 'error'
            });
            return;
        }
        
        // Set form action
        if (expenseForm) {
            expenseForm.action = `/masters/entries/${entryId}/expenses/save`;
            expenseForm.method = "POST";
            
            // Add the current active tab to form submission
            const activeTab = document.querySelector('.nav-tabs .nav-link.active');
            if (activeTab) {
                const tabName = activeTab.getAttribute('href').replace('#tab-', '');
                
                // Remove any existing active_tab input
                const existingTabInput = expenseForm.querySelector('input[name="active_tab"]');
                if (existingTabInput) {
                    existingTabInput.value = tabName;
                } else {
                    // Create a new input for active_tab
                    const tabInput = document.createElement('input');
                    tabInput.type = 'hidden';
                    tabInput.name = 'active_tab';
                    tabInput.value = tabName;
                    expenseForm.appendChild(tabInput);
                }
            }
        }

        const entryIdField = document.getElementById('shipmentIdForExpense');
        if (entryIdField) {
            entryIdField.value = entryId;
        }
        
        // Set modal title and button text for new expense
        if (modalTitle) modalTitle.textContent = 'Add Expense';
        if (saveButton) saveButton.textContent = 'Create Expense';
        
        // Hide edit-only fields
        document.querySelectorAll('.edit-only-fields').forEach(field => {
            field.classList.add('d-none');
        });
        
        // Hide current attachment preview
        const currentAttachment = document.getElementById('currentAttachment');
        if (currentAttachment) currentAttachment.classList.add('d-none');
        
        // Set today's date as default
        const dateField = document.getElementById('expenseDateFrom');
        if (dateField) {
            const today = new Date();
            const formattedDate = today.toISOString().split('T')[0]; // YYYY-MM-DD
            dateField.value = formattedDate;
        }
        
        // Set default values for numeric fields
        if (valueInput) valueInput.value = '0.00';
        if (vatInput) vatInput.value = '0.00';
        if (netAmountDisplay) netAmountDisplay.value = '0.00';
        if (marginInput) marginInput.value = '0.00';
        if (marginAmountInput) marginAmountInput.value = '0.00';
        if (chargeableDisplay) chargeableDisplay.value = '0.00';
        
        // Reset settlement information
        const chargedAmount = document.getElementById('expenseChargedAmount');
        const balanceAmount = document.getElementById('expenseBalanceAmount');
        const settlementStatus = document.getElementById('expenseSettlementStatus');
        
        if (chargedAmount) chargedAmount.value = '0.00';
        if (balanceAmount) balanceAmount.value = '0.00';
        if (settlementStatus) {
            settlementStatus.innerHTML = '<span class="badge badge-soft-secondary">Not Available</span>';
        }
        
        // Set default customer visibility
        const visibleToCustomer = document.getElementById('expenseVisibleToCustomer');
        if (visibleToCustomer) visibleToCustomer.checked = true;
        
        // Show the modal immediately so the user sees something
        const bootstrapModal = new bootstrap.Modal(expenseModal);
        bootstrapModal.show();
        
        // Fetch document number from server
        fetchDocumentNumber(entryId);
    }

    // Separate function to fetch document number
    function fetchDocumentNumber(entryId) {
        const documentNumberField = document.getElementById('documentNumber');
        
        // Additional validation to avoid malformed requests
        if (!entryId || isNaN(parseInt(entryId))) {
            console.error("Invalid entry ID for document number generation");
            if (documentNumberField) {
                documentNumberField.value = 'Error: Invalid entry ID';
            }
            return;
        }
        
        // Show loading state
        if (documentNumberField) {
            documentNumberField.value = 'Generating...';
            documentNumberField.classList.add('bg-light');
            documentNumberField.setAttribute('readonly', true);
        }
        
        console.log(`Fetching document number for entry ID: ${entryId}`);
        
        // Fetch from server - using the new URL pattern for entries
        fetch(`/masters/entries/${entryId}/generate-expense-number`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Server error: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log("Server response:", data);
                if (data.success && documentNumberField) {
                    documentNumberField.value = data.document_number;
                } else {
                    throw new Error(data.error || 'Error generating document number');
                }
            })
            .catch(error => {
                console.error('Error fetching document number:', error);
                if (documentNumberField) {
                    documentNumberField.value = 'Error: ' + error.message;
                }
                
                // Notify user of the error
                Swal.fire({
                    title: 'Error',
                    text: 'Failed to generate document number. ' + error.message,
                    icon: 'error',
                    confirmButtonClass: 'btn btn-primary w-xs mt-2',
                    buttonsStyling: false
                });
            });
    }
    
    // Function to fetch expense data for editing
    function fetchExpenseData(entryId, expenseId) {
        // Validate the entry ID to prevent malformed requests
        if (!entryId || entryId === '{{ shipment.id }}' || isNaN(parseInt(entryId))) {
            console.error("Invalid entry ID:", entryId);
            
            // Try to find the entry ID from the URL or DOM
            entryId = extractEntryIdFromPage();
            
            if (!entryId) {
                Swal.fire({
                    title: 'Error',
                    text: 'Could not determine entry ID. Please reload the page and try again.',
                    icon: 'error',
                    confirmButtonClass: 'btn btn-primary w-xs mt-2',
                    buttonsStyling: false
                });
                return;
            }
        }
        
        // Show loading indicator
        Swal.fire({
            title: 'Loading...',
            text: 'Fetching expense data',
            allowOutsideClick: false,
            didOpen: () => {
                Swal.showLoading();
            }
        });
        
        console.log(`Fetching expense data for entry ID: ${entryId}, expense ID: ${expenseId}`);
        
        // Updated URL to use entries route pattern
        fetch(`/masters/entries/${entryId}/expenses/${expenseId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                // Close loading indicator
                Swal.close();
                
                if (data.success) {
                    populateExpenseModal(data.expense, entryId);
                } else {
                    throw new Error(data.error || 'Failed to load expense data');
                }
            })
            .catch(error => {
                console.error('Error fetching expense data:', error);
                
                // Close loading indicator and show error
                Swal.fire({
                    title: 'Error',
                    text: 'Failed to load expense data: ' + error.message,
                    icon: 'error',
                    confirmButtonClass: 'btn btn-primary w-xs mt-2',
                    buttonsStyling: false
                });
            });
    }

    // Helper function to extract entry ID from page
    function extractEntryIdFromPage() {
        let entryId;
        
        // Option 1: Try to get from a hidden field if it exists
        const entryIdField = document.getElementById('shipmentIdForExpense');
        if (entryIdField && entryIdField.value && entryIdField.value !== '{{ shipment.id }}') {
            entryId = entryIdField.value;
        } 
        // Option 2: Try to get from URL if it contains /entries/{id}/
        else {
            const urlMatch = window.location.pathname.match(/\/entries\/(\d+)/);
            if (urlMatch && urlMatch[1]) {
                entryId = urlMatch[1];
            }
        }
        
        // Option 3: Last resort, try to find any field with entry ID
        if (!entryId) {
            const idField = document.querySelector('input[name="id"]');
            if (idField && idField.value) {
                entryId = idField.value;
            }
        }
        
        // Make sure it's a valid number
        return entryId && !isNaN(parseInt(entryId)) ? entryId : null;
    }

    // Helper function to extract entry_id
    function extractEntryId() {
        // First check the global variable set in the template
        if (window.currentEntryId) {
            return window.currentEntryId;
        }
        
        // Fallback to hidden fields if global variable is not set
        const entryIdField = document.getElementById('shipmentIdForExpense');
        if (entryIdField && entryIdField.value) {
            return entryIdField.value;
        }
        
        // Last resort, try URL
        const urlMatch = window.location.pathname.match(/\/shipments\/(\d+)/);
        if (urlMatch && urlMatch[1]) {
            return urlMatch[1];
        }
        
        console.error('Could not determine entry ID');
        return null;
    }

    // Make the extractEntryIdFromPage function simply call extractEntryId
    function extractEntryIdFromPage() {
        return extractEntryId();
    }
        
    // Function to populate the expense modal with data
    function populateExpenseModal(expense, entryId) {
        if (!entryId || isNaN(parseInt(entryId))) {
            entryId = extractEntryIdFromPage();
            
            if (!entryId) {
                Swal.fire({
                    title: 'Error',
                    text: 'Could not determine entry ID for form submission.',
                    icon: 'error',
                    confirmButtonClass: 'btn btn-primary w-xs mt-2',
                    buttonsStyling: false
                });
                return;
            }
        }
    
        // Set hidden fields
        if (expenseIdField) expenseIdField.value = expense.id;
        
        // Set form action
        if (expenseForm) {
            expenseForm.action = `/masters/entries/${entryId}/expenses/save`;
        }
        
        // Set modal title and button text for editing
        if (modalTitle) modalTitle.textContent = 'Edit Expense';
        if (saveButton) saveButton.textContent = 'Update Expense';
        
        // Populate form fields
        const fields = {
            'expenseDateFrom': expense.doc_date,
            'documentNumber': expense.document_number,
            'supplierName': expense.supplier_name,
            'expenseReference': expense.reference,
            'expenseNarration': expense.narration,
            'expenseType': expense.expense_type_id,
            'expenseCurrency': expense.currency_id,
            'expenseValue': parseFloat(expense.value_amount).toFixed(2),
            'expenseVAT': parseFloat(expense.vat_amount).toFixed(2),
            'expenseNetAmount': parseFloat(expense.amount).toFixed(2),
            'expenseMargin': parseFloat(expense.margin).toFixed(2),
            'expenseMarginAmount': parseFloat(expense.margin_amount).toFixed(2),
            'expenseChargeableAmount': parseFloat(expense.chargeable_amount).toFixed(2),
            'expenseChargedAmount': parseFloat(expense.charged_amount).toFixed(2),
            'expenseBalanceAmount': parseFloat(expense.balance_amount).toFixed(2)
        };
        
        // Set each field value
        for (const [id, value] of Object.entries(fields)) {
            const field = document.getElementById(id);
            if (field) field.value = value;
        }
        
        // Make document number read-only
        const documentNumberField = document.getElementById('documentNumber');
        if (documentNumberField) {
            documentNumberField.setAttribute('readonly', true);
            documentNumberField.classList.add('bg-light');
        }
        
        // Set checkboxes
        const visibleToCustomer = document.getElementById('expenseVisibleToCustomer');
        if (visibleToCustomer) visibleToCustomer.checked = expense.visible_to_customer;
        
        const attachmentVisibleToCustomer = document.getElementById('attachmentVisibleToCustomer');
        if (attachmentVisibleToCustomer) attachmentVisibleToCustomer.checked = expense.attachment_visible_to_customer;
        
        // Handle attachment if exists
        if (expense.attachment_path) {
            const currentAttachment = document.getElementById('currentAttachment');
            const currentAttachmentName = document.getElementById('currentAttachmentName');
            const viewAttachmentLink = document.getElementById('viewAttachmentLink');
            
            if (currentAttachment) currentAttachment.classList.remove('d-none');
            if (currentAttachmentName) {
                // Extract filename from path
                const fileName = expense.attachment_path.split('/').pop();
                currentAttachmentName.textContent = fileName;
            }
            
            if (viewAttachmentLink) {
                viewAttachmentLink.href = `/masters/expenses/${expense.id}/attachment`;
            }
            
            // Set up remove attachment behavior
            const removeCurrentAttachment = document.getElementById('removeCurrentAttachment');
            if (removeCurrentAttachment) {
                removeCurrentAttachment.onclick = function() {
                    // Mark attachment for removal
                    const removeAttachmentField = document.createElement('input');
                    removeAttachmentField.type = 'hidden';
                    removeAttachmentField.name = 'remove_attachment';
                    removeAttachmentField.value = '1';
                    expenseForm.appendChild(removeAttachmentField);
                    
                    // Hide current attachment display
                    currentAttachment.classList.add('d-none');
                };
            }
        } else {
            // No attachment
            const currentAttachment = document.getElementById('currentAttachment');
            if (currentAttachment) currentAttachment.classList.add('d-none');
        }
        
        // Update settlement status display
        updateSettlementStatusDisplay(expense);
        
        // Setup settlement history view button
        const viewSettlementHistory = document.getElementById('viewSettlementHistory');
        if (viewSettlementHistory) {
            viewSettlementHistory.onclick = function() {
                window.location.href = `/masters/entries/${entryId}/expenses/${expense.id}/settlements`;
            };
        }
        
        // Add creator info if available (for edit-only fields)
        if (expense.created_by_name || expense.created_at) {
            const editOnlyFields = document.querySelector('.edit-only-fields');
            const createdByField = document.getElementById('expenseCreatedBy');
            const createdDateField = document.getElementById('expenseCreatedDate');
            
            if (editOnlyFields) editOnlyFields.classList.remove('d-none');
            if (createdByField) createdByField.value = expense.created_by_name || 'Unknown';
            if (createdDateField) createdDateField.value = expense.created_at || 'Unknown';
        }
        
        // Show modal
        const bootstrapModal = new bootstrap.Modal(expenseModal);
        bootstrapModal.show();
    }
    
    // Update the settlement status display
    function updateSettlementStatusDisplay(expense) {
        const settlementStatus = document.getElementById('expenseSettlementStatus');
        if (!settlementStatus) return;
        
        if (!expense.chargeable_amount) {
            settlementStatus.innerHTML = '<span class="badge badge-soft-secondary">N/A</span>';
            return;
        }
        
        const chargedAmount = parseFloat(expense.charged_amount) || 0;
        const chargeableAmount = parseFloat(expense.chargeable_amount) || 0;
        
        if (chargedAmount <= 0) {
            settlementStatus.innerHTML = '<span class="badge badge-soft-danger">Unsettled</span>';
        } else if (chargedAmount >= chargeableAmount) {
            settlementStatus.innerHTML = '<span class="badge badge-soft-success">Fully Settled</span>';
        } else {
            const percentage = Math.round((chargedAmount / chargeableAmount) * 100);
            settlementStatus.innerHTML = `<span class="badge badge-soft-warning">Partially Settled (${percentage}%)</span>`;
        }
    }
    
    // Setup expense calculations for dynamic UI updates
    function setupExpenseCalculations() {
        if (!valueInput || !vatInput || !netAmountDisplay || !marginInput || 
            !marginAmountInput || !chargeableDisplay) return;
        
        function updateCalculations() {
            // Calculate net amount
            const value = parseFloat(valueInput.value) || 0;
            const vat = parseFloat(vatInput.value) || 0;
            const netAmount = value + vat;
            
            // Update net amount display
            netAmountDisplay.value = netAmount.toFixed(2);
            
            // Update margin amount or percentage based on which one was modified
            const margin = parseFloat(marginInput.value) || 0;
            const marginAmount = (netAmount * margin / 100);
            marginAmountInput.value = marginAmount.toFixed(2);
            
            // Update chargeable amount
            const chargeableAmount = netAmount + marginAmount;
            chargeableDisplay.value = chargeableAmount.toFixed(2);
        }
        
        // Add event listeners for value fields
        valueInput.addEventListener('input', updateCalculations);
        vatInput.addEventListener('input', updateCalculations);
        marginInput.addEventListener('input', updateCalculations);
        
        // If margin amount is changed directly, update percentage
        marginAmountInput.addEventListener('input', function() {
            const netAmount = parseFloat(netAmountDisplay.value) || 0;
            if (netAmount > 0) {
                const marginAmount = parseFloat(this.value) || 0;
                const percentage = (marginAmount / netAmount) * 100;
                marginInput.value = percentage.toFixed(2);
            }
            
            // Update chargeable amount
            const netAmount2 = parseFloat(netAmountDisplay.value) || 0;
            const marginAmount2 = parseFloat(this.value) || 0;
            chargeableDisplay.value = (netAmount2 + marginAmount2).toFixed(2);
        });
    }
    
    // Handle attachment file selection for preview
    const expenseAttachment = document.getElementById('expenseAttachment');
    const attachmentPreview = document.getElementById('attachmentPreview');
    const attachmentName = document.getElementById('attachmentName');
    const attachmentSize = document.getElementById('attachmentSize');
    const attachmentIcon = document.getElementById('attachmentIcon');
    
    if (expenseAttachment && attachmentPreview) {
        expenseAttachment.addEventListener('change', function() {
            if (this.files && this.files[0]) {
                const file = this.files[0];
                const fileExt = file.name.split('.').pop().toLowerCase();
                
                // Show preview
                attachmentPreview.classList.remove('d-none');
                
                // Set name and size
                if (attachmentName) attachmentName.textContent = file.name;
                if (attachmentSize) {
                    const fileSizeKB = (file.size / 1024).toFixed(2);
                    attachmentSize.textContent = `${fileSizeKB} KB`;
                }
                
                // Set appropriate icon based on file type
                if (attachmentIcon) {
                    if (['jpg', 'jpeg', 'png', 'gif'].includes(fileExt)) {
                        attachmentIcon.className = 'ri-image-line fs-24 me-2';
                    } else if (fileExt === 'pdf') {
                        attachmentIcon.className = 'ri-file-pdf-line fs-24 me-2';
                    } else if (['doc', 'docx'].includes(fileExt)) {
                        attachmentIcon.className = 'ri-file-word-line fs-24 me-2';
                    } else if (['xls', 'xlsx'].includes(fileExt)) {
                        attachmentIcon.className = 'ri-file-excel-line fs-24 me-2';
                    } else {
                        attachmentIcon.className = 'ri-file-text-line fs-24 me-2';
                    }
                }
                
                // Setup remove button
                const removeAttachment = document.getElementById('removeAttachment');
                if (removeAttachment) {
                    removeAttachment.onclick = function() {
                        expenseAttachment.value = '';
                        attachmentPreview.classList.add('d-none');
                    };
                }
            }
        });
    }
    
    // Initialize: If the URL has a tab parameter for expenses, activate that tab
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('tab') === 'expenses') {
        const expensesTabLink = document.querySelector('a[href="#tab-expenses"]');
        if (expensesTabLink) {
            const tab = new bootstrap.Tab(expensesTabLink);
            tab.show();
        }
    }
});