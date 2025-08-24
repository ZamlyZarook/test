/**
 * Optimized Invoice Tab Functionality - Functional Approach
 * Handles creating, editing, viewing invoices with VAT support
 * Supports expenses, rate cards, and income items
 */

// Global variables
let invoiceItems = {
    expenses: [],
    rateCards: [],
    incomes: []
};
let isEditMode = false;
let currentInvoiceId = null;

// DOM Ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('Invoice tab script loaded');
    initializeInvoiceTab();
});

// Initialize all invoice functionality
function initializeInvoiceTab() {
    setupEventListeners();
    setupVATCalculations();
    setupModalResets(); // ADD this line
    console.log('Invoice tab initialized');
}

// Setup all event listeners
function setupEventListeners() {
    // Create Invoice Button
    const createBtn = document.getElementById('createInvoiceBtn');
    if (createBtn) {
        createBtn.addEventListener('click', function(e) {
            e.preventDefault();
            console.log('Create invoice clicked');
            openCreateModal();
        });
    }

    // Invoice Form Submission
    // Invoice Form Submission - IMPROVED VERSION
    const form = document.getElementById('invoiceForm');
    if (form) {
        // Remove any existing listeners first
        const existingHandler = form._invoiceSubmitHandler;
        if (existingHandler) {
            form.removeEventListener('submit', existingHandler);
        }
        
        // Create new handler
        const submitHandler = function(e) {
            e.preventDefault();
            e.stopImmediatePropagation(); // Prevent other handlers
            
            // Prevent double submission
            if (form.hasAttribute('data-submitting')) {
                console.log('Form already submitting, ignoring duplicate');
                return false;
            }
            
            form.setAttribute('data-submitting', 'true');
            console.log('Form submitted, isEditMode:', isEditMode); // Add this debug line
            
            handleInvoiceSubmit().finally(() => {
                form.removeAttribute('data-submitting');
            });
            
            return false;
        };
        
        // Store reference and add listener
        form._invoiceSubmitHandler = submitHandler;
        form.addEventListener('submit', submitHandler);
    }

    // Add Item Buttons
    const addExpenseBtn = document.getElementById('addExpenseBtn');
    if (addExpenseBtn) {
        addExpenseBtn.addEventListener('click', function(e) {
            e.preventDefault();
            console.log('Add expense clicked');
            openExpenseSelectionModal();
        });
    }

    const addRateCardBtn = document.getElementById('addRateCardBtn');
    if (addRateCardBtn) {
        addRateCardBtn.addEventListener('click', function(e) {
            e.preventDefault();
            console.log('Add rate card clicked');
            openRateCardSelectionModal();
        });
    }

    const addIncomeBtn = document.getElementById('addIncomeBtn');
    if (addIncomeBtn) {
        addIncomeBtn.addEventListener('click', function(e) {
            e.preventDefault();
            console.log('Add income clicked');
            openIncomeModal();
        });
    }

    // Modal specific buttons
    const addSelectedExpenseBtn = document.getElementById('addSelectedExpense');
    if (addSelectedExpenseBtn) {
        addSelectedExpenseBtn.addEventListener('click', function(e) {
            e.preventDefault();
            addSelectedExpense();
        });
    }

    const addSelectedRateCardBtn = document.getElementById('addSelectedRateCard');
    if (addSelectedRateCardBtn) {
        addSelectedRateCardBtn.addEventListener('click', function(e) {
            e.preventDefault();
            addSelectedRateCard();
        });
    }

    // Expense selector change
    const expenseSelector = document.getElementById('expenseSelector');
    if (expenseSelector) {
        expenseSelector.addEventListener('change', function() {
            handleExpenseSelection();
        });
    }

    // Rate card selector change  
    const rateCardSelector = document.getElementById('rateCardSelector');
    if (rateCardSelector) {
        rateCardSelector.addEventListener('change', function() {
            handleRateCardSelection();
        });
    }

    // Table action buttons (using delegation)
    document.addEventListener('click', function(e) {
        handleTableActions(e);
    });

    // Status update button
    const updateStatusBtn = document.getElementById('updateInvoiceStatus');
    if (updateStatusBtn) {
        updateStatusBtn.addEventListener('click', function(e) {
            e.preventDefault();
            updateInvoiceStatus();
        });
    }

    const submitBtn = document.getElementById('submitInvoiceBtn');
    if (submitBtn) {
        submitBtn.addEventListener('click', function(e) {
            e.preventDefault();
            const invoiceId = this.getAttribute('data-invoice-id');
            if (invoiceId) submitInvoice(invoiceId);
        });
    }

    const submitEditBtn = document.getElementById('submitInvoiceEditBtn');
    if (submitEditBtn) {
        submitEditBtn.addEventListener('click', function(e) {
            e.preventDefault();
            const invoiceId = this.getAttribute('data-invoice-id');
            if (invoiceId) submitInvoice(invoiceId);
        });
    }


}

// Setup modal reset on close
function setupModalResets() {
    // Reset invoice modal when closed
    const invoiceModal = document.getElementById('invoiceModal');
    if (invoiceModal) {
        invoiceModal.addEventListener('hidden.bs.modal', function() {
            console.log('Modal closed, isEditMode:', isEditMode); // Debug
            
            // Only reset if we're not in edit mode
            if (!isEditMode) {
                resetForm();
            } else {
                // For edit mode, only clear form data but preserve button states
                const form = document.getElementById('invoiceForm');
                if (form) {
                    form.reset();
                    form.removeAttribute('data-submitting');
                }
                
                // Clear items but don't reset buttons
                invoiceItems = { expenses: [], rateCards: [], incomes: [] };
                document.getElementById('invoiceId').value = '';
                clearItemsTable();
                updateInvoiceTotal();
                
                // Reset edit mode flag
                isEditMode = false;
                currentInvoiceId = null;
            }
        });
    }
    
    // Reset expense selection modal when closed
    const expenseModal = document.getElementById('expenseSelectionModal');
    if (expenseModal) {
        expenseModal.addEventListener('hidden.bs.modal', function() {
            // Reset expense selector
            const selector = document.getElementById('expenseSelector');
            if (selector) selector.value = '';
            
            // Hide expense details
            const details = document.getElementById('expenseDetails');
            if (details) details.classList.add('d-none');
            
            // Reset VAT inputs
            const vatInputs = expenseModal.querySelectorAll('.charged-amount-input, .vat-percentage-input, .vat-amount-input, .final-amount-with-vat');
            vatInputs.forEach(input => {
                input.value = '0';
                input.classList.remove('is-invalid');
            });
        });
    }

    // Reset rate card selection modal when closed
    const rateCardModal = document.getElementById('rateCardSelectionModal');
    if (rateCardModal) {
        rateCardModal.addEventListener('hidden.bs.modal', function() {
            // Reset rate card selector
            const selector = document.getElementById('rateCardSelector');
            if (selector) selector.value = '';
            
            // Hide rate card details
            const details = document.getElementById('rateCardDetails');
            if (details) details.classList.add('d-none');
            
            // Reset description field
            const descriptionField = document.getElementById('rateCardDescription');
            if (descriptionField) descriptionField.value = '';
        });
    }

    // Reset income modal when closed
    const incomeModal = document.getElementById('incomeModal');
    if (incomeModal) {
        incomeModal.addEventListener('hidden.bs.modal', function() {
            // Reset income form fields
            const descriptionField = document.getElementById('incomeDescription');
            const amountField = document.getElementById('incomeAmount');
            
            if (descriptionField) {
                descriptionField.value = '';
                descriptionField.classList.remove('is-invalid');
            }
            if (amountField) {
                amountField.value = '';
                amountField.classList.remove('is-invalid');
            }
        });
    }
}


// Setup VAT calculations
function setupVATCalculations() {
    const expenseModal = document.getElementById('expenseSelectionModal');
    if (!expenseModal) return;

    expenseModal.addEventListener('input', function(e) {
        if (e.target.matches('.charged-amount-input')) {
            validateChargedAmount(e.target);
            calculateVAT('base');
        } else if (e.target.matches('.vat-percentage-input')) {
            calculateVAT('percentage');
        } else if (e.target.matches('.vat-amount-input')) {
            calculateVAT('amount');
        }
    });
}

// Open create modal
function openCreateModal() {
    console.log('Opening create modal');
    resetForm();
    isEditMode = false;
    currentInvoiceId = null;
    
    document.getElementById('invoiceModalLabel').textContent = 'Create Invoice';
    document.getElementById('saveInvoice').textContent = 'Create Invoice';
    
    const editFields = document.querySelector('.edit-only-fields');
    if (editFields) editFields.classList.add('d-none');
    
    setTodaysDate();
    fetchNextInvoiceNumber();
    
    const modal = new bootstrap.Modal(document.getElementById('invoiceModal'));
    modal.show();
}

// Reset form
// FIXED: Don't reset button states when in edit mode
function resetForm() {
    const form = document.getElementById('invoiceForm');
    if (form) form.reset();
    
    invoiceItems = { expenses: [], rateCards: [], incomes: [] };
    document.getElementById('invoiceId').value = '';
    clearItemsTable();
    updateInvoiceTotal();
    
    // ✅ FIXED: Only reset button states when NOT in edit mode
    if (!isEditMode) {
        // Reset submit buttons only for new invoices
        const submitEditBtn = document.getElementById('submitInvoiceEditBtn');
        if (submitEditBtn) {
            submitEditBtn.style.display = 'none';
            submitEditBtn.disabled = false;
            submitEditBtn.className = 'btn btn-primary';
            submitEditBtn.innerHTML = '<i class="ri-check-line me-1"></i> Submit Invoice';
        }
        
        const submitBtn = document.getElementById('submitInvoiceBtn');
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.className = 'btn btn-success';
            submitBtn.innerHTML = '<i class="ri-check-line me-1"></i> Submit Invoice';
        }
    }
}

// Clear items table
function clearItemsTable() {
    const tbody = document.querySelector('#invoiceItemsTable tbody');
    if (tbody) {
        tbody.innerHTML = `
            <tr id="noItemsRow">
                <td colspan="8" class="text-center">No items added yet</td>
            </tr>
        `;
    }
}

// Set today's date
function setTodaysDate() {
    const dateField = document.getElementById('invoiceDate');
    if (dateField) {
        const today = new Date().toISOString().split('T')[0];
        dateField.value = today;
    }
}

// Fetch next invoice number
async function fetchNextInvoiceNumber() {
    const entryId = getEntryId();
    if (!entryId) return;

    const invoiceNumberField = document.getElementById('invoiceNumber');
    if (!invoiceNumberField) return;

    try {
        invoiceNumberField.value = 'Generating...';
        
        const response = await fetch(`/masters/entries/${entryId}/invoices/next-number`);
        const data = await response.json();
        
        if (data.success) {
            invoiceNumberField.value = data.next_invoice_number;
        } else {
            throw new Error(data.message || 'Error generating invoice number');
        }
    } catch (error) {
        invoiceNumberField.value = 'Error: ' + error.message;
        showError('Failed to generate invoice number: ' + error.message);
    }
}

// Handle invoice form submission
async function handleInvoiceSubmit() {
    console.log('Handling invoice submission');
    
    const formData = collectFormData();
    if (!validateFormData(formData)) return Promise.resolve();

    try {
        setLoadingState(true);
        
        const entryId = getEntryId();
        const url = isEditMode 
            ? `/masters/entries/${entryId}/invoices/${currentInvoiceId}`
            : `/masters/entries/${entryId}/invoices`;
        const method = isEditMode ? 'PUT' : 'POST';

        console.log('Submitting to:', url, 'Method:', method, 'Data:', formData);

        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
        });

        const result = await response.json();
        console.log('Response:', result);
        
        if (result.success) {
            showSuccess(result.message || (isEditMode ? 'Invoice updated successfully' : 'Invoice created successfully'));
            closeModal();
            redirectToInvoicesTab();
        } else {
            throw new Error(result.message || 'Failed to save invoice');
        }
    } catch (error) {
        console.error('Submission error:', error);
        showError(error.message || 'An error occurred while saving the invoice');
    } finally {
        setLoadingState(false);
    }
}

// Collect form data
function collectFormData() {
    const data = {
        invoice_date: document.getElementById('invoiceDate')?.value,
        narration: document.getElementById('invoiceNarration')?.value || '',
        expense_items: collectExpenseItems(),
        rate_card_items: collectRateCardItems(),
        income_items: collectIncomeItems()
    };
    
    console.log('Collected form data:', data);
    return data;
}

// Collect expense items with VAT
function collectExpenseItems() {
    const expenseRows = document.querySelectorAll('#invoiceItemsTable tbody tr[data-expense-id]:not(#noItemsRow)');
    const items = [];
    
    expenseRows.forEach(row => {
        const expenseId = row.getAttribute('data-expense-id');
        if (!expenseId) return;

        // Try different input selectors for VAT data
        let chargedAmount = 0;
        let vatPercentage = 0;
        let vatAmount = 0;
        let finalAmount = 0;

        // For edit mode (with edit controls)
        const chargedEdit = row.querySelector('.charged-amount-edit');
        const vatPercentEdit = row.querySelector('.vat-percentage-edit');
        const vatAmountEdit = row.querySelector('.vat-amount-edit');
        const finalEdit = row.querySelector('.final-amount-edit');

        // For display mode (hidden inputs)
        const hiddenCharged = row.querySelector('input[name$="[charged_amount_before_vat]"]');
        const hiddenVatPercent = row.querySelector('input[name$="[vat_percentage]"]');
        const hiddenVatAmount = row.querySelector('input[name$="[vat_amount]"]');
        const hiddenFinal = row.querySelector('input[name$="[final_amount]"]');

        // For simple mode (just final amount)
        const finalAmountInput = row.querySelector('.final-amount');

        if (chargedEdit && vatPercentEdit && vatAmountEdit && finalEdit) {
            // Edit mode
            chargedAmount = parseFloat(chargedEdit.value) || 0;
            vatPercentage = parseFloat(vatPercentEdit.value) || 0;
            vatAmount = parseFloat(vatAmountEdit.value) || 0;
            finalAmount = parseFloat(finalEdit.value) || 0;
        } else if (hiddenCharged && hiddenVatPercent && hiddenVatAmount && hiddenFinal) {
            // Hidden inputs mode
            chargedAmount = parseFloat(hiddenCharged.value) || 0;
            vatPercentage = parseFloat(hiddenVatPercent.value) || 0;
            vatAmount = parseFloat(hiddenVatAmount.value) || 0;
            finalAmount = parseFloat(hiddenFinal.value) || 0;
        } else if (finalAmountInput) {
            // Simple mode - assume no VAT
            finalAmount = parseFloat(finalAmountInput.value) || 0;
            chargedAmount = finalAmount;
        }

        if (chargedAmount > 0 || finalAmount > 0) {
            items.push({
                expense_id: expenseId,
                charged_amount_before_vat: chargedAmount,
                vat_percentage: vatPercentage,
                vat_amount: vatAmount,
                final_amount: finalAmount
            });
        }
    });
    
    console.log('Collected expense items:', items);
    return items;
}

// Collect rate card items
function collectRateCardItems() {
    const rateCardRows = document.querySelectorAll('#invoiceItemsTable tbody tr[data-rate-card-id]:not(#noItemsRow)');
    const items = [];
    
    rateCardRows.forEach(row => {
        const rateCardId = row.getAttribute('data-rate-card-id');
        const finalAmountInput = row.querySelector('.final-amount, input[name$="[final_amount]"]');
        const descriptionInput = row.querySelector('input[name$="[description]"]');
        
        if (rateCardId && finalAmountInput) {
            const finalAmount = parseFloat(finalAmountInput.value) || 0;
            if (finalAmount > 0) {
                items.push({
                    rate_card_id: rateCardId,
                    description: descriptionInput?.value || '',
                    final_amount: finalAmount
                });
            }
        }
    });
    
    return items;
}

// Collect income items
function collectIncomeItems() {
    const incomeRows = document.querySelectorAll('#invoiceItemsTable tbody tr[data-item-type="income"]:not(#noItemsRow)');
    const items = [];
    
    incomeRows.forEach(row => {
        const description = row.getAttribute('data-description');
        const amountInput = row.querySelector('.final-amount, input[name$="[amount]"]');
        
        if (description && amountInput) {
            const amount = parseFloat(amountInput.value) || 0;
            if (amount > 0) {
                items.push({
                    description: description,
                    amount: amount
                });
            }
        }
    });
    
    return items;
}

// Validate form data
function validateFormData(formData) {
    if (!formData.invoice_date) {
        showError('Invoice date is required');
        return false;
    }

    const totalItems = formData.expense_items.length + formData.rate_card_items.length + formData.income_items.length;
    if (totalItems === 0) {
        showError('Please add at least one item to the invoice');
        return false;
    }

    return true;
}

// Open expense selection modal
async function openExpenseSelectionModal() {
    console.log('Opening expense selection modal');
    const entryId = getEntryId();
    if (!entryId) {
        showError('Could not determine entry ID');
        return;
    }

    try {
        const response = await fetch(`/masters/entries/${entryId}/available-expenses`);
        const data = await response.json();

        if (data.success) {
            populateExpenseSelector(data.expenses);
            const modal = new bootstrap.Modal(document.getElementById('expenseSelectionModal'));
            modal.show();
        } else {
            throw new Error(data.message || 'Failed to load expenses');
        }
    } catch (error) {
        showError('Failed to load available expenses: ' + error.message);
    }
}

// Populate expense selector
function populateExpenseSelector(expenses) {
    const selector = document.getElementById('expenseSelector');
    if (!selector) return;

    selector.innerHTML = '<option value="">Select an expense</option>';
    
    if (expenses.length === 0) {
        selector.innerHTML = '<option value="">No available expenses</option>';
        return;
    }

    expenses.forEach(expense => {
        const adjustedBalance = expense.balance_amount - getAlreadyChargedAmount(expense.id);
        if (adjustedBalance > 0) {
            const option = document.createElement('option');
            option.value = expense.id;
            option.textContent = `${expense.expense_type_description} - ${expense.formatted_chargeable_amount} (Available: ${formatCurrency(adjustedBalance)})`;
            option.dataset.expense = JSON.stringify({ ...expense, adjusted_balance: adjustedBalance });
            selector.appendChild(option);
        }
    });
}

// Handle expense selection
function handleExpenseSelection() {
    const selector = document.getElementById('expenseSelector');
    const detailsPanel = document.getElementById('expenseDetails');
    
    if (!selector || !detailsPanel) return;

    const selectedOption = selector.options[selector.selectedIndex];

    if (selectedOption?.value && selectedOption.dataset.expense) {
        try {
            const expense = JSON.parse(selectedOption.dataset.expense);
            populateExpenseDetails(expense);
            updateExpenseBalance(expense);
            detailsPanel.classList.remove('d-none');
        } catch (error) {
            console.error('Error handling expense selection:', error);
            detailsPanel.classList.add('d-none');
        }
    } else {
        detailsPanel.classList.add('d-none');
    }
}

// Populate expense details
function populateExpenseDetails(expense) {
    const elements = {
        type: document.getElementById('expenseTypeDisplay'),
        amount: document.getElementById('expenseAmountDisplay'),
        margin: document.getElementById('expenseMarginDisplay'),
        chargeable: document.getElementById('expenseChargeableDisplay'),
        narration: document.getElementById('expenseNarrationDisplay')
    };

    if (elements.type) elements.type.textContent = expense.expense_type_description || '';
    if (elements.amount) elements.amount.textContent = formatCurrency(expense.amount);
    if (elements.margin) elements.margin.textContent = `${expense.margin || 0}%`;
    if (elements.chargeable) elements.chargeable.textContent = formatCurrency(expense.chargeable_amount);
    if (elements.narration) elements.narration.textContent = expense.narration || '';
}

// Update expense balance display
function updateExpenseBalance(expense) {
    const alreadyCharged = getAlreadyChargedAmount(expense.id);
    const adjustedBalance = expense.balance_amount - alreadyCharged;

    const elements = {
        charged: document.getElementById('expenseChargedDisplay'),
        balance: document.getElementById('expenseBalanceDisplay'),
        maxAmount: document.getElementById('maxAvailableAmount'),
        chargedInput: document.querySelector('.charged-amount-input')
    };

    if (elements.charged) elements.charged.textContent = formatCurrency((expense.charged_amount || 0) + alreadyCharged);
    if (elements.balance) elements.balance.textContent = formatCurrency(adjustedBalance);
    if (elements.maxAmount) elements.maxAmount.textContent = formatCurrency(adjustedBalance);

    if (elements.chargedInput) {
        elements.chargedInput.max = adjustedBalance;
        elements.chargedInput.value = adjustedBalance > 0 ? adjustedBalance : 0;
        elements.chargedInput.setAttribute('data-adjusted-balance', adjustedBalance);
        elements.chargedInput.disabled = adjustedBalance <= 0;
    }

    calculateVAT('base');
}

// VAT calculation
function calculateVAT(triggerType) {
    const inputs = {
        charged: document.querySelector('.charged-amount-input'),
        vatPercent: document.querySelector('.vat-percentage-input'),
        vatAmount: document.querySelector('.vat-amount-input'),
        final: document.querySelector('.final-amount-with-vat')
    };

    if (!inputs.charged || !inputs.vatPercent || !inputs.vatAmount || !inputs.final) return;

    const baseAmount = parseFloat(inputs.charged.value) || 0;
    const vatPercentage = parseFloat(inputs.vatPercent.value) || 0;
    const vatAmount = parseFloat(inputs.vatAmount.value) || 0;

    let newVatAmount, newFinalAmount;

    switch (triggerType) {
        case 'percentage':
            newVatAmount = (baseAmount * vatPercentage) / 100;
            inputs.vatAmount.value = newVatAmount.toFixed(2);
            newFinalAmount = baseAmount + newVatAmount;
            break;
        case 'amount':
            newFinalAmount = baseAmount + vatAmount;
            if (baseAmount > 0) {
                const newPercentage = (vatAmount / baseAmount) * 100;
                inputs.vatPercent.value = newPercentage.toFixed(2);
            }
            break;
        case 'base':
        default:
            newVatAmount = (baseAmount * vatPercentage) / 100;
            inputs.vatAmount.value = newVatAmount.toFixed(2);
            newFinalAmount = baseAmount + newVatAmount;
            break;
    }

    inputs.final.value = newFinalAmount.toFixed(2);
}

// Validate charged amount
function validateChargedAmount(input) {
    const maxAmount = parseFloat(input.getAttribute('data-adjusted-balance')) || 0;
    const currentAmount = parseFloat(input.value) || 0;

    if (currentAmount > maxAmount) {
        input.classList.add('is-invalid');
        input.setCustomValidity('Amount exceeds available balance');
    } else {
        input.classList.remove('is-invalid');
        input.setCustomValidity('');
    }
}

// Add selected expense
function addSelectedExpense() {
    console.log('Adding selected expense');
    
    const selector = document.getElementById('expenseSelector');
    const selectedOption = selector?.options[selector.selectedIndex];
    
    if (!selectedOption?.value || !selectedOption.dataset.expense) {
        showError('Please select an expense first');
        return;
    }

    try {
        const expense = JSON.parse(selectedOption.dataset.expense);
        const vatData = getVATInputData();
        
        if (!validateExpenseVATData(vatData, expense)) return;

        addExpenseToTable(expense, vatData);
        closeModal(document.getElementById('expenseSelectionModal'));
        updateInvoiceTotal();
        showSuccess(`${formatCurrency(vatData.chargedAmount)} charged from expense (Invoice amount: ${formatCurrency(vatData.finalAmount)} with VAT)`);
    } catch (error) {
        console.error('Error adding expense:', error);
        showError('An error occurred while adding the expense');
    }
}

// Get VAT input data
function getVATInputData() {
    return {
        chargedAmount: parseFloat(document.querySelector('.charged-amount-input')?.value) || 0,
        vatPercentage: parseFloat(document.querySelector('.vat-percentage-input')?.value) || 0,
        vatAmount: parseFloat(document.querySelector('.vat-amount-input')?.value) || 0,
        finalAmount: parseFloat(document.querySelector('.final-amount-with-vat')?.value) || 0
    };
}

// Validate expense VAT data
function validateExpenseVATData(vatData, expense) {
    if (vatData.chargedAmount <= 0) {
        showError('Please enter a valid amount to charge');
        return false;
    }

    const adjustedBalance = parseFloat(document.querySelector('.charged-amount-input')?.getAttribute('data-adjusted-balance')) || 0;
    if (vatData.chargedAmount > adjustedBalance) {
        showError(`Amount exceeds available balance of ${formatCurrency(adjustedBalance)}`);
        return false;
    }

    return true;
}

// Add expense to table
function addExpenseToTable(expense, vatData) {
    removeNoItemsRow();
    
    const rowId = 'expense_' + Date.now();
    const row = document.createElement('tr');
    row.id = rowId;
    row.setAttribute('data-expense-id', expense.id);
    row.setAttribute('data-item-type', 'expense');

    row.innerHTML = generateExpenseRowHTML(expense, vatData, rowId);
    
    const tbody = document.querySelector('#invoiceItemsTable tbody');
    if (tbody) {
        tbody.appendChild(row);
    }
}

// Generate expense row HTML
function generateExpenseRowHTML(expense, vatData, rowId) {
    return `
        <td>
            ${expense.expense_type_description || ''}
            <input type="hidden" name="expense_items[][expense_id]" value="${expense.id}">
        </td>
        <td>${expense.narration || ''}</td>
        <td>${formatCurrency(expense.amount)}</td>
        <td>${expense.margin || 0}%</td>
        <td>${formatCurrency(expense.chargeable_amount)}</td>
        <td>${formatCurrency(expense.adjusted_balance)}</td>
        <td>
            <div class="vat-breakdown small">
                <div class="d-flex justify-content-between">
                    <span>Charged Amount:</span>
                    <span class="fw-medium">${formatCurrency(vatData.chargedAmount)}</span>
                </div>
                ${vatData.vatAmount > 0 ? `
                <div class="d-flex justify-content-between text-muted">
                    <span>+ VAT (${vatData.vatPercentage}%):</span>
                    <span>${formatCurrency(vatData.vatAmount)}</span>
                </div>
                <hr class="my-1">` : ''}
                <div class="d-flex justify-content-between fw-bold">
                    <span>Invoice Amount:</span>
                    <span class="text-success">${formatCurrency(vatData.finalAmount)}</span>
                </div>
            </div>
            ${generateVATHiddenInputs(vatData)}
        </td>
        <td>
            <button type="button" class="btn btn-sm btn-danger" onclick="removeInvoiceItem('${rowId}')">
                <i class="ri-delete-bin-line"></i>
            </button>
        </td>
    `;
}

// Generate VAT hidden inputs
function generateVATHiddenInputs(vatData) {
    return `
        <input type="hidden" name="expense_items[][charged_amount_before_vat]" value="${vatData.chargedAmount}">
        <input type="hidden" name="expense_items[][vat_percentage]" value="${vatData.vatPercentage}">
        <input type="hidden" name="expense_items[][vat_amount]" value="${vatData.vatAmount}">
        <input type="hidden" name="expense_items[][final_amount]" value="${vatData.finalAmount}">
        <input type="hidden" class="final-amount" value="${vatData.finalAmount}">
    `;
}

// Rate card functions
async function openRateCardSelectionModal() {
    console.log('Opening rate card selection modal');
    const entryId = getEntryId();
    if (!entryId) return;

    try {
        const response = await fetch(`/masters/entries/${entryId}/rate-cards`);
        const data = await response.json();

        if (data.success) {
            populateRateCardSelector(data.rate_cards);
            const modal = new bootstrap.Modal(document.getElementById('rateCardSelectionModal'));
            modal.show();
        } else {
            throw new Error(data.message || 'Failed to load rate cards');
        }
    } catch (error) {
        showError('Failed to load rate cards: ' + error.message);
    }
}

function populateRateCardSelector(rateCards) {
    const selector = document.getElementById('rateCardSelector');
    if (!selector) return;

    selector.innerHTML = '<option value="">Select a rate card item</option>';

    if (rateCards.length === 0) {
        selector.innerHTML = '<option value="">No rate cards available</option>';
        return;
    }

    rateCards.forEach(rate => {
        const option = document.createElement('option');
        option.value = rate.id;
        option.textContent = `${rate.income_description} - ${rate.formatted_amount}`;
        option.dataset.data = JSON.stringify(rate);
        selector.appendChild(option);
    });
}

function handleRateCardSelection() {
    const selector = document.getElementById('rateCardSelector');
    const details = document.getElementById('rateCardDetails');
    
    if (!selector || !details) return;

    const selectedOption = selector.options[selector.selectedIndex];

    if (selectedOption?.value && selectedOption.dataset.data) {
        try {
            const rateCard = JSON.parse(selectedOption.dataset.data);
            
            const typeDisplay = document.getElementById('rateCardTypeDisplay');
            const amountDisplay = document.getElementById('rateCardAmountDisplay');
            const descriptionField = document.getElementById('rateCardDescription');
            
            if (typeDisplay) typeDisplay.textContent = rateCard.income_description || '';
            if (amountDisplay) amountDisplay.textContent = rateCard.formatted_amount || '';
            if (descriptionField) descriptionField.value = '';
            
            details.classList.remove('d-none');
        } catch (error) {
            details.classList.add('d-none');
        }
    } else {
        details.classList.add('d-none');
    }
}

function addSelectedRateCard() {
    const selector = document.getElementById('rateCardSelector');
    if (!selector?.value) return;

    try {
        const selectedOption = selector.options[selector.selectedIndex];
        const rateCard = JSON.parse(selectedOption.dataset.data);
        const description = document.getElementById('rateCardDescription')?.value || '';

        addRateCardToTable(rateCard, description);
        closeModal(document.getElementById('rateCardSelectionModal'));
        updateInvoiceTotal();
    } catch (error) {
        showError('Error adding rate card');
    }
}

function addRateCardToTable(rateCard, description) {
    removeNoItemsRow();
    
    const rowId = 'rate_' + Date.now();
    const row = document.createElement('tr');
    row.id = rowId;
    row.setAttribute('data-rate-card-id', rateCard.id);
    row.setAttribute('data-item-type', 'rate_card');

    row.innerHTML = `
        <td>
            ${rateCard.income_description || ''}
            <span class="badge badge-soft-info ms-2">Rate Card</span>
            <input type="hidden" name="rate_card_items[][rate_card_id]" value="${rateCard.id}">
        </td>
        <td>
            ${description || rateCard.income_description || ''}
            <input type="hidden" name="rate_card_items[][description]" value="${description || rateCard.income_description || ''}">
        </td>
        <td colspan="4">
            ${formatCurrency(rateCard.amount)}
            <input type="hidden" name="rate_card_items[][original_amount]" value="${rateCard.amount || 0}">
        </td>
        <td>
            <div class="input-group input-group-sm">
                <span class="input-group-text">LKR</span>
                <input type="number" class="form-control form-control-sm final-amount" 
                       step="0.01" name="rate_card_items[][final_amount]" 
                       value="${rateCard.amount}" onchange="updateInvoiceTotal()">
            </div>
        </td>
        <td>
            <button type="button" class="btn btn-sm btn-danger" onclick="removeInvoiceItem('${rowId}')">
                <i class="ri-delete-bin-line"></i>
            </button>
        </td>
    `;

    const tbody = document.querySelector('#invoiceItemsTable tbody');
    if (tbody) {
        tbody.appendChild(row);
    }
}

// Income functions
function openIncomeModal() {
    console.log('Opening income modal');
    
    // Reset form fields
    const descriptionField = document.getElementById('incomeDescription');
    const amountField = document.getElementById('incomeAmount');
    
    if (descriptionField) descriptionField.value = '';
    if (amountField) amountField.value = '';
    
    const modal = new bootstrap.Modal(document.getElementById('incomeModal'));
    modal.show();
    
    // Setup income modal button if not already done
    setupIncomeModalButton();
}

function setupIncomeModalButton() {
    const incomeModal = document.getElementById('incomeModal');
    if (!incomeModal) return;
    
    // Find the add button in the modal
    const addButton = incomeModal.querySelector('.modal-footer .btn-primary');
    if (addButton && !addButton.hasAttribute('data-listener-added')) {
        addButton.setAttribute('data-listener-added', 'true');
        addButton.addEventListener('click', function(e) {
            e.preventDefault();
            addIncomeItem();
        });
    }
}

function addIncomeItem() {
    console.log('Adding income item');
    
    const descriptionInput = document.getElementById('incomeDescription');
    const amountInput = document.getElementById('incomeAmount');

    if (!descriptionInput || !amountInput) {
        showError('Income form elements not found');
        return;
    }

    const description = descriptionInput.value.trim();
    const amount = parseFloat(amountInput.value);

    // Validate inputs
    if (!description) {
        descriptionInput.classList.add('is-invalid');
        showError('Please enter a description');
        return;
    }
    descriptionInput.classList.remove('is-invalid');

    if (isNaN(amount) || amount <= 0) {
        amountInput.classList.add('is-invalid');
        showError('Please enter a valid amount');
        return;
    }
    amountInput.classList.remove('is-invalid');

    addIncomeToTable(description, amount);
    closeModal(document.getElementById('incomeModal'));
    updateInvoiceTotal();
}

function addIncomeToTable(description, amount) {
    removeNoItemsRow();
    
    const rowId = 'income_' + Date.now();
    const row = document.createElement('tr');
    row.id = rowId;
    row.setAttribute('data-item-type', 'income');
    row.setAttribute('data-description', description);

    row.innerHTML = `
        <td>
            <span class="fw-medium">Income</span>
            <span class="badge badge-soft-success ms-2">Income Item</span>
            <input type="hidden" name="income_items[][description]" value="${description}">
        </td>
        <td>${description}</td>
        <td colspan="4">${formatCurrency(amount)}</td>
        <td>
            <div class="input-group input-group-sm">
                <span class="input-group-text">LKR</span>
                <input type="number" class="form-control form-control-sm final-amount" 
                       step="0.01" name="income_items[][amount]" 
                       value="${amount}" onchange="updateInvoiceTotal()">
            </div>
        </td>
        <td>
            <button type="button" class="btn btn-sm btn-danger" onclick="removeInvoiceItem('${rowId}')">
                <i class="ri-delete-bin-line"></i>
            </button>
        </td>
    `;

    const tbody = document.querySelector('#invoiceItemsTable tbody');
    if (tbody) {
        tbody.appendChild(row);
    }
}

// Table management functions
function removeInvoiceItem(rowId) {
    console.log('Removing item:', rowId);
    
    const row = document.getElementById(rowId);
    if (row) {
        row.remove();
        updateInvoiceTotal();
        
        // Add "no items" row if table is empty
        const tbody = document.querySelector('#invoiceItemsTable tbody');
        const remainingRows = tbody?.querySelectorAll('tr');
        if (!remainingRows || remainingRows.length === 0) {
            clearItemsTable();
        }
    }
}

function removeNoItemsRow() {
    const noItemsRow = document.getElementById('noItemsRow');
    if (noItemsRow) {
        noItemsRow.remove();
    }
}

function updateInvoiceTotal() {
    const finalAmountInputs = document.querySelectorAll('#invoiceItemsTable .final-amount');
    let total = 0;

    finalAmountInputs.forEach(input => {
        const value = parseFloat(input.value) || 0;
        if (!isNaN(value)) total += value;
    });

    const totalElement = document.getElementById('invoiceTotal');
    if (totalElement) {
        totalElement.textContent = formatCurrency(total);
    }
}

// View/Edit/Delete functions
async function viewInvoice(entryId, invoiceId) {
    try {
        console.log('Viewing invoice:', invoiceId); // DEBUG
        
        const response = await fetch(`/masters/entries/${entryId}/invoices/${invoiceId}`);
        const data = await response.json();

        if (data.success) {
            console.log('Invoice data for view:', data.invoice); // DEBUG
            populateViewModal(data.invoice);
            
            const modal = new bootstrap.Modal(document.getElementById('viewInvoiceModal'));
            modal.show();
            
            // Double-check submit button state after modal is shown
            setTimeout(() => {
                debugSubmitButtonState();
            }, 100);
        } else {
            throw new Error(data.message || 'Failed to load invoice details');
        }
    } catch (error) {
        console.error('Error viewing invoice:', error);
        showError('Failed to load invoice details: ' + error.message);
    }
}

function populateViewModal(invoice) {
    console.log('Invoice data received:', invoice); // DEBUG LINE
    console.log('Submitted status:', invoice.submitted, typeof invoice.submitted); // DEBUG LINE
    
    // Set header info
    const elements = {
        number: document.getElementById('viewInvoiceNumber'),
        date: document.getElementById('viewInvoiceDate'),
        status: document.getElementById('viewInvoiceStatus'),
        customer: document.getElementById('viewInvoiceCustomer'),
        narration: document.getElementById('viewInvoiceNarration'),
        createdBy: document.getElementById('viewInvoiceCreatedBy'),
        total: document.getElementById('viewInvoiceTotal')
    };

    if (elements.number) elements.number.textContent = invoice.invoice_number;
    if (elements.date) elements.date.textContent = invoice.invoice_date ? new Date(invoice.invoice_date).toLocaleDateString() : '';
    if (elements.status) elements.status.innerHTML = getStatusBadge(invoice.payment_status);
    if (elements.customer) elements.customer.textContent = invoice.customer_name;
    if (elements.narration) elements.narration.textContent = invoice.narration || '-';
    if (elements.createdBy) elements.createdBy.textContent = invoice.created_by;
    if (elements.total) elements.total.textContent = invoice.formatted_total || formatCurrency(invoice.total);

    // Populate items table
    const tbody = document.querySelector('#viewInvoiceItems tbody');
    if (tbody) {
        tbody.innerHTML = '';

        if (invoice.details && invoice.details.length > 0) {
            invoice.details.forEach(item => {
                const row = document.createElement('tr');
                row.innerHTML = generateViewItemHTML(item);
                tbody.appendChild(row);
            });
        } else {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center">No items found</td></tr>';
        }
    }

    // FIXED: Update submit button state based on submission status
    const submitBtn = document.getElementById('submitInvoiceBtn');
    if (submitBtn) {
        // Convert to boolean and handle various truthy/falsy values
        const isSubmitted = Boolean(invoice.submitted);
        console.log('View modal - Invoice submitted status:', isSubmitted); // DEBUG
        
        if (isSubmitted) {
            // Hide submit button if already submitted
            submitBtn.style.display = 'none';
            console.log('View modal - Submit button hidden'); // DEBUG
        } else {
            // Show submit button if not submitted
            submitBtn.style.display = 'inline-block';
            submitBtn.disabled = false;
            submitBtn.className = 'btn btn-success';
            submitBtn.innerHTML = '<i class="ri-check-line me-1"></i> Submit Invoice';
            submitBtn.setAttribute('data-invoice-id', invoice.id);
            console.log('View modal - Submit button shown'); // DEBUG
        }
    } else {
        console.error('Submit button not found in view modal'); // DEBUG
    }

    // Add debug call
    debugSubmitButtonState();
}



function generateViewItemHTML(item) {
    if (item.item_type === 'rate_card') {
        return `
            <td>${item.expense_type}<span class="badge badge-soft-info ms-2">Rate Card</span></td>
            <td>${item.description || '-'}</td>
            <td>${formatCurrency(item.original_amount)}</td>
            <td>N/A</td>
            <td>N/A</td>
            <td class="text-end">${formatCurrency(item.final_amount)}</td>
        `;
    } else if (item.item_type === 'income') {
        return `
            <td>Income<span class="badge badge-soft-success ms-2">Income Item</span></td>
            <td>${item.description || '-'}</td>
            <td>${formatCurrency(item.original_amount)}</td>
            <td>N/A</td>
            <td>N/A</td>
            <td class="text-end">${formatCurrency(item.final_amount)}</td>
        `;
    } else if (item.item_type === 'expense') {
        const hasVAT = item.vat_amount && item.vat_amount > 0;
        const chargedBeforeVAT = item.charged_amount_before_vat || item.final_amount;
        const vatAmount = item.vat_amount || 0;
        const vatPercentage = item.vat_percentage || 0;

        let settlementInfo = '';
        if (item.original_chargeable_amount > 0) {
            const percentage = Math.round((chargedBeforeVAT / item.original_chargeable_amount) * 100);
            if (percentage < 100) {
                settlementInfo = `<small class="text-muted d-block">(${percentage}% of chargeable amount)</small>`;
            }
        }

        return `
            <td>${item.expense_type}</td>
            <td>${item.description || '-'}</td>
            <td>${formatCurrency(item.original_amount)}</td>
            <td>${item.margin || 0}%</td>
            <td>${formatCurrency(item.original_chargeable_amount)}</td>
            <td>
                <div class="vat-breakdown-view">
                    <div class="d-flex justify-content-between">
                        <span>Charged Amount:</span>
                        <span class="fw-medium">${formatCurrency(chargedBeforeVAT)}</span>
                    </div>
                    ${hasVAT ? `
                    <div class="d-flex justify-content-between text-muted small">
                        <span>+ VAT (${vatPercentage}%):</span>
                        <span>${formatCurrency(vatAmount)}</span>
                    </div>
                    <hr class="my-1">` : ''}
                    <div class="d-flex justify-content-between fw-bold">
                        <span>Invoice Total:</span>
                        <span class="text-success">${formatCurrency(item.final_amount)}</span>
                    </div>
                    ${settlementInfo}
                </div>
            </td>
        `;
    }
    return '';
}

async function editInvoice(entryId, invoiceId) {
    console.log('editInvoice called with:', entryId, invoiceId); // Debug
    
    try {
        // Set edit mode BEFORE clearing form data
        isEditMode = true;
        currentInvoiceId = invoiceId;
        
        console.log('Edit mode set, currentInvoiceId:', currentInvoiceId); // Debug
        console.log('isEditMode value:', isEditMode); // Debug
        
        // Clear form data
        const form = document.getElementById('invoiceForm');
        if (form) form.reset();
        
        // Clear items but don't reset button states
        invoiceItems = { expenses: [], rateCards: [], incomes: [] };
        document.getElementById('invoiceId').value = '';
        clearItemsTable();
        updateInvoiceTotal();
        
        document.getElementById('invoiceModalLabel').textContent = 'Loading Invoice...';
        document.getElementById('saveInvoice').disabled = true;
        
        const modal = new bootstrap.Modal(document.getElementById('invoiceModal'));
        modal.show();

        const response = await fetch(`/masters/entries/${entryId}/invoices/${invoiceId}`);
        const data = await response.json();

        console.log('Invoice data received:', data); // Debug

        if (data.success) {
            // Add a small delay to ensure modal is fully rendered
            await new Promise(resolve => setTimeout(resolve, 100));
            
            console.log('About to call populateInvoiceEditForm with:', data.invoice); // Debug
            console.log('isEditMode before populateInvoiceEditForm:', isEditMode); // Debug
            
            // Test if populateInvoiceEditForm function exists
            console.log('populateInvoiceEditForm function exists:', typeof populateInvoiceEditForm); // Debug
            
            try {
                // Simple test to see if the function is callable
                console.log('Calling populateInvoiceEditForm...'); // Debug
                await populateInvoiceEditForm(data.invoice);
                console.log('populateInvoiceEditForm completed successfully'); // Debug
            } catch (populateError) {
                console.error('Error in populateInvoiceEditForm:', populateError); // Debug
                console.error('Error stack:', populateError.stack); // Debug
                throw populateError;
            }
            
            document.getElementById('invoiceModalLabel').textContent = 'Edit Invoice';
            document.getElementById('saveInvoice').textContent = 'Update Invoice';
            document.getElementById('saveInvoice').disabled = false;
            
            const editFields = document.querySelector('.edit-only-fields');
            if (editFields) editFields.classList.remove('d-none');
            
            console.log('Edit form populated successfully'); // Debug
        } else {
            throw new Error(data.message || 'Failed to load invoice details');
        }
    } catch (error) {
        console.error('Error in editInvoice:', error); // Debug
        showError('Failed to load invoice details: ' + error.message);
        closeModal();
    }
}

async function populateInvoiceEditForm(invoice) {
    console.log('=== populateInvoiceEditForm START ==='); // Debug
    console.log('populateInvoiceEditForm called with invoice:', invoice); // Debug
    
    // Immediate test to see if we can access DOM elements
    console.log('Testing DOM access...'); // Debug
    const testElement = document.getElementById('invoiceNumber');
    console.log('invoiceNumber element found:', !!testElement); // Debug
    
    try {
        console.log('Entering try block...'); // Debug
        
        // Set form fields with error checking
        const invoiceNumberField = document.getElementById('invoiceNumber');
        const invoiceDateField = document.getElementById('invoiceDate');
        const invoiceNarrationField = document.getElementById('invoiceNarration');
        
        console.log('Form fields found:', {
            invoiceNumber: !!invoiceNumberField,
            invoiceDate: !!invoiceDateField,
            invoiceNarration: !!invoiceNarrationField
        }); // Debug
        
        if (invoiceNumberField) {
            invoiceNumberField.value = invoice.invoice_number;
            console.log('Set invoice number:', invoice.invoice_number); // Debug
        } else {
            console.error('invoiceNumber field not found'); // Debug
        }
        
        if (invoiceDateField && invoice.invoice_date) {
            const dateValue = new Date(invoice.invoice_date).toISOString().split('T')[0];
            invoiceDateField.value = dateValue;
            console.log('Set invoice date:', dateValue); // Debug
        } else {
            console.error('invoiceDate field not found or no date'); // Debug
        }
        
        if (invoiceNarrationField) {
            invoiceNarrationField.value = invoice.narration || '';
            console.log('Set narration:', invoice.narration || ''); // Debug
        } else {
            console.error('invoiceNarration field not found'); // Debug
        }

        // Set creator info
        const createdByField = document.getElementById('invoiceCreatedBy');
        const createdDateField = document.getElementById('invoiceCreatedDate');
        
        console.log('Creator fields found:', {
            createdBy: !!createdByField,
            createdDate: !!createdDateField
        }); // Debug
        
        if (createdByField) createdByField.value = invoice.created_by || 'Unknown';
        if (createdDateField) createdDateField.value = invoice.created_at ? new Date(invoice.created_at).toLocaleString() : 'Unknown';

        // Populate items
        console.log('Invoice details:', invoice.details); // Debug
        if (invoice.details && invoice.details.length > 0) {
            for (const detail of invoice.details) {
                console.log('Processing detail:', detail); // Debug
                if (detail.item_type === 'expense') {
                    await addEditExpenseItem(detail);
                } else if (detail.item_type === 'rate_card') {
                    addEditRateCardItem(detail);
                } else if (detail.item_type === 'income') {
                    addEditIncomeItem(detail);
                }
            }
        }

        // Update submit button state for edit modal
        const submitEditBtn = document.getElementById('submitInvoiceEditBtn');
        if (submitEditBtn) {
            const isSubmitted = Boolean(invoice.submitted);
            
            if (isSubmitted) {
                // Hide submit button if already submitted
                submitEditBtn.style.display = 'none';
            } else {
                // Show submit button if not submitted
                submitEditBtn.style.display = 'block';
                submitEditBtn.disabled = false;
                submitEditBtn.className = 'btn btn-primary';
                submitEditBtn.innerHTML = '<i class="ri-check-line me-1"></i> Submit Invoice';
                submitEditBtn.setAttribute('data-invoice-id', invoice.id);
            }
        }
        
        // FIXED: Convert submitted to boolean and update the submit button state
        const isSubmitted = Boolean(invoice.submitted);
        console.log('Edit form - Invoice submitted status:', isSubmitted); // DEBUG
        
        updateSubmitButtonState('submitInvoiceEditBtn', isSubmitted, invoice.id);
        
        updateInvoiceTotal();
        console.log('populateInvoiceEditForm completed successfully'); // Debug
    } catch (error) {
        console.error('Error in populateInvoiceEditForm:', error); // Debug
        console.error('Error stack:', error.stack); // Debug
        throw error;
    }
    
    console.log('=== populateInvoiceEditForm END ==='); // Debug
}

async function addEditExpenseItem(detail) {
    try {
        const entryId = getEntryId();
        const response = await fetch(`/masters/entries/${entryId}/expenses/${detail.expense_id}`);
        const data = await response.json();

        if (data.success) {
            const expense = data.expense;
            const vatData = {
                chargedAmount: detail.charged_amount_before_vat || detail.final_amount,
                vatPercentage: detail.vat_percentage || 0,
                vatAmount: detail.vat_amount || 0,
                finalAmount: detail.final_amount
            };

            // Adjust balance for edit mode
            expense.adjusted_balance = expense.balance_amount + vatData.chargedAmount;
            addExpenseToEditTable(expense, vatData);
        }
    } catch (error) {
        console.error('Error loading expense for edit:', error);
    }
}


// Submit invoice function
async function submitInvoice(invoiceId) {
    const entryId = getEntryId();
    if (!entryId) {
        showError('Could not determine entry ID');
        return;
    }

    // Find the button that was clicked
    const submitBtn = document.getElementById('submitInvoiceBtn') || document.getElementById('submitInvoiceEditBtn');
    if (!submitBtn) return;

    const originalHTML = submitBtn.innerHTML;
    const originalDisabled = submitBtn.disabled;
    
    try {
        // Show loading state
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Submitting...';
        submitBtn.disabled = true;

        const response = await fetch(`/masters/entries/${entryId}/invoices/${invoiceId}/submit`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' }
        });

        const data = await response.json();
        
        if (data.success) {
            showSuccess(data.message || 'Invoice submitted successfully');
            
            // Close any open modals
            const viewModal = bootstrap.Modal.getInstance(document.getElementById('viewInvoiceModal'));
            if (viewModal) viewModal.hide();
            
            const editModal = bootstrap.Modal.getInstance(document.getElementById('invoiceModal'));
            if (editModal) editModal.hide();
            
            // Refresh the page to update the invoice table
            setTimeout(() => {
                window.location.reload();
            }, 1500);
        } else {
            throw new Error(data.message || 'Failed to submit invoice');
        }
    } catch (error) {
        // Restore original state on error
        submitBtn.innerHTML = originalHTML;
        submitBtn.disabled = originalDisabled;
        showError('Failed to submit invoice: ' + error.message);
    }
}



function updateSubmitButtonState(buttonId, isSubmitted, invoiceId) {
    const button = document.getElementById(buttonId);
    if (!button) {
        console.warn(`Button with ID ${buttonId} not found`);
        return;
    }
    
    // Ensure isSubmitted is a boolean
    const submitted = Boolean(isSubmitted);
    
    console.log(`Updating button ${buttonId} - Invoice ID: ${invoiceId}, Submitted: ${submitted}`); // DEBUG
    
    // Set the invoice ID
    button.setAttribute('data-invoice-id', invoiceId);
    
    if (submitted) {
        // Submitted state
        button.disabled = true;
        button.className = 'btn btn-secondary';
        button.innerHTML = '<i class="ri-check-double-line me-1"></i> Submitted';
        console.log(`Button ${buttonId} set to submitted state`); // DEBUG
    } else {
        // Not submitted state
        button.disabled = false;
        button.className = buttonId === 'submitInvoiceBtn' ? 'btn btn-success' : 'btn btn-primary';
        button.innerHTML = '<i class="ri-check-line me-1"></i> Submit Invoice';
        console.log(`Button ${buttonId} set to active state`); // DEBUG
    }
}

function updateInvoiceTableRow(invoiceId) {
    // Find the invoice row in the main table and update any status indicators
    const tableRow = document.querySelector(`#invoicesTable tbody tr[data-id="${invoiceId}"]`);
    if (tableRow) {
        // Hide edit and delete buttons for submitted invoices
        const editBtn = tableRow.querySelector('.edit-invoice');
        const deleteBtn = tableRow.querySelector('.delete-invoice');
        const statusBtn = tableRow.querySelector('.update-status');
        
        if (editBtn) editBtn.style.display = 'none';
        if (deleteBtn) deleteBtn.style.display = 'none';
        if (statusBtn) statusBtn.style.display = 'none';
        
        // Add a "Submitted" badge to indicate status
        const statusCell = tableRow.querySelector('td:nth-child(4)'); // Adjust column index as needed
        if (statusCell) {
            const submittedBadge = document.createElement('span');
            submittedBadge.className = 'badge badge-soft-success ms-2';
            submittedBadge.textContent = 'Submitted';
            statusCell.appendChild(submittedBadge);
        }
    }
}

function addExpenseToEditTable(expense, vatData) {
    removeNoItemsRow();
    
    const rowId = 'expense_' + Date.now();
    const row = document.createElement('tr');
    row.id = rowId;
    row.setAttribute('data-expense-id', expense.id);
    row.setAttribute('data-item-type', 'expense');

    row.innerHTML = `
        <td>
            ${expense.expense_type_description || ''}
            <input type="hidden" name="expense_items[][expense_id]" value="${expense.id}">
        </td>
        <td>${expense.narration || ''}</td>
        <td>${formatCurrency(expense.amount)}</td>
        <td>${expense.margin || 0}%</td>
        <td>${formatCurrency(expense.chargeable_amount)}</td>
        <td>${formatCurrency(expense.adjusted_balance)}</td>
        <td>
            <div class="edit-vat-breakdown">
                <div class="row g-2">
                    <div class="col-8">
                        <label class="form-label small">Charged Amount</label>
                        <div class="input-group input-group-sm">
                            <span class="input-group-text">LKR</span>
                            <input type="number" class="form-control charged-amount-edit" step="0.01" 
                                   max="${expense.adjusted_balance}" value="${vatData.chargedAmount}" 
                                   data-row-id="${rowId}">
                        </div>
                    </div>
                    <div class="col-4">
                        <label class="form-label small">VAT %</label>
                        <input type="number" class="form-control form-control-sm vat-percentage-edit" 
                               step="0.01" min="0" max="100" value="${vatData.vatPercentage}" 
                               data-row-id="${rowId}">
                    </div>
                    <div class="col-6">
                        <label class="form-label small">VAT Amount</label>
                        <div class="input-group input-group-sm">
                            <span class="input-group-text">LKR</span>
                            <input type="number" class="form-control vat-amount-edit" step="0.01" 
                                   min="0" value="${vatData.vatAmount}" 
                                   data-row-id="${rowId}">
                        </div>
                    </div>
                    <div class="col-6">
                        <label class="form-label small fw-bold">Invoice Total</label>
                        <div class="input-group input-group-sm">
                            <span class="input-group-text">LKR</span>
                            <input type="number" class="form-control final-amount-edit final-amount" 
                                   step="0.01" readonly value="${vatData.finalAmount}" 
                                   style="background-color: #e9ecef; font-weight: bold;">
                        </div>
                    </div>
                </div>
                ${generateEditVATHiddenInputs(vatData)}
            </div>
        </td>
        <td>
            <button type="button" class="btn btn-sm btn-danger" onclick="removeInvoiceItem('${rowId}')">
                <i class="ri-delete-bin-line"></i>
            </button>
        </td>
    `;

    const tbody = document.querySelector('#invoiceItemsTable tbody');
    if (tbody) {
        tbody.appendChild(row);
    }

    // Add event listeners for dynamic updates
    setupEditRowEventListeners(rowId);
}


function setupEditRowEventListeners(rowId) {
    const row = document.getElementById(rowId);
    if (!row) {
        console.warn('Row not found for event listeners:', rowId);
        return;
    }

    // Add event listeners for all edit inputs
    const chargedInput = row.querySelector('.charged-amount-edit');
    const vatPercentInput = row.querySelector('.vat-percentage-edit');
    const vatAmountInput = row.querySelector('.vat-amount-edit');

    if (chargedInput) {
        chargedInput.addEventListener('input', function() {
            console.log('Charged amount changed:', this.value); // Debug
            validateEditAmount(this, rowId);
        });
        chargedInput.addEventListener('change', function() {
            console.log('Charged amount change event triggered'); // Debug
            updateEditVAT(rowId);
        });
    }

    if (vatPercentInput) {
        vatPercentInput.addEventListener('change', function() {
            console.log('VAT percentage changed:', this.value); // Debug
            updateEditVAT(rowId);
        });
    }

    if (vatAmountInput) {
        vatAmountInput.addEventListener('change', function() {
            console.log('VAT amount changed:', this.value); // Debug
            updateEditVAT(rowId);
        });
    }
    
    console.log('Event listeners set up for row:', rowId); // Debug
}


function generateEditVATHiddenInputs(vatData) {
    return `
        <input type="hidden" name="expense_items[][charged_amount_before_vat]" value="${vatData.chargedAmount}" class="hidden-charged-amount">
        <input type="hidden" name="expense_items[][vat_percentage]" value="${vatData.vatPercentage}" class="hidden-vat-percentage">
        <input type="hidden" name="expense_items[][vat_amount]" value="${vatData.vatAmount}" class="hidden-vat-amount">
        <input type="hidden" name="expense_items[][final_amount]" value="${vatData.finalAmount}" class="hidden-final-amount">
    `;
}

function updateEditVAT(rowId) {
    const row = document.getElementById(rowId);
    if (!row) return;

    const chargedAmountInput = row.querySelector('.charged-amount-edit');
    const vatPercentageInput = row.querySelector('.vat-percentage-edit');
    const vatAmountInput = row.querySelector('.vat-amount-edit');
    const finalAmountInput = row.querySelector('.final-amount-edit');

    if (!chargedAmountInput || !vatPercentageInput || !vatAmountInput || !finalAmountInput) return;

    const chargedAmount = parseFloat(chargedAmountInput.value) || 0;
    const vatPercentage = parseFloat(vatPercentageInput.value) || 0;

    // Calculate VAT amount and final amount
    const vatAmount = (chargedAmount * vatPercentage) / 100;
    const finalAmount = chargedAmount + vatAmount;

    // Update display fields
    vatAmountInput.value = vatAmount.toFixed(2);
    finalAmountInput.value = finalAmount.toFixed(2);

    // Update hidden fields
    const hiddenCharged = row.querySelector('.hidden-charged-amount');
    const hiddenVatPercent = row.querySelector('.hidden-vat-percentage');
    const hiddenVatAmount = row.querySelector('.hidden-vat-amount');
    const hiddenFinal = row.querySelector('.hidden-final-amount');

    if (hiddenCharged) hiddenCharged.value = chargedAmount;
    if (hiddenVatPercent) hiddenVatPercent.value = vatPercentage;
    if (hiddenVatAmount) hiddenVatAmount.value = vatAmount.toFixed(2);
    if (hiddenFinal) hiddenFinal.value = finalAmount.toFixed(2);

    updateInvoiceTotal();
}

function validateEditAmount(input, rowId) {
    const maxAmount = parseFloat(input.getAttribute('max')) || 0;
    const currentAmount = parseFloat(input.value) || 0;

    if (currentAmount > maxAmount) {
        input.classList.add('is-invalid');
        input.setCustomValidity('Amount exceeds available balance');
    } else {
        input.classList.remove('is-invalid');
        input.setCustomValidity('');
    }
}

function addEditRateCardItem(detail) {
    removeNoItemsRow();
    
    const rowId = 'rate_' + Date.now();
    const row = document.createElement('tr');
    row.id = rowId;
    row.setAttribute('data-rate-card-id', detail.rate_card_id);
    row.setAttribute('data-item-type', 'rate_card');

    row.innerHTML = `
        <td>
            ${detail.expense_type}
            <span class="badge badge-soft-info ms-2">Rate Card</span>
            <input type="hidden" name="rate_card_items[][rate_card_id]" value="${detail.rate_card_id}">
        </td>
        <td>
            ${detail.description || '-'}
            <input type="hidden" name="rate_card_items[][description]" value="${detail.description || ''}">
        </td>
        <td colspan="4">
            ${formatCurrency(detail.original_amount)}
            <input type="hidden" name="rate_card_items[][original_amount]" value="${detail.original_amount || 0}">
        </td>
        <td>
            <div class="input-group input-group-sm">
                <span class="input-group-text">LKR</span>
                <input type="number" class="form-control form-control-sm final-amount" 
                       step="0.01" name="rate_card_items[][final_amount]" 
                       value="${detail.final_amount}" onchange="updateInvoiceTotal()">
            </div>
        </td>
        <td>
            <button type="button" class="btn btn-sm btn-danger" onclick="removeInvoiceItem('${rowId}')">
                <i class="ri-delete-bin-line"></i>
            </button>
        </td>
    `;

    const tbody = document.querySelector('#invoiceItemsTable tbody');
    if (tbody) {
        tbody.appendChild(row);
    }
}

function addEditIncomeItem(detail) {
    removeNoItemsRow();
    
    const rowId = 'income_' + Date.now();
    const row = document.createElement('tr');
    row.id = rowId;
    row.setAttribute('data-item-type', 'income');
    row.setAttribute('data-description', detail.description);

    row.innerHTML = `
        <td>
            <span class="fw-medium">Income</span>
            <span class="badge badge-soft-success ms-2">Income Item</span>
            <input type="hidden" name="income_items[][description]" value="${detail.description}">
        </td>
        <td>${detail.description}</td>
        <td colspan="4">${formatCurrency(detail.original_amount)}</td>
        <td>
            <div class="input-group input-group-sm">
                <span class="input-group-text">LKR</span>
                <input type="number" class="form-control form-control-sm final-amount" 
                       step="0.01" name="income_items[][amount]" 
                       value="${detail.final_amount}" onchange="updateInvoiceTotal()">
            </div>
        </td>
        <td>
            <button type="button" class="btn btn-sm btn-danger" onclick="removeInvoiceItem('${rowId}')">
                <i class="ri-delete-bin-line"></i>
            </button>
        </td>
    `;

    const tbody = document.querySelector('#invoiceItemsTable tbody');
    if (tbody) {
        tbody.appendChild(row);
    }
}

// Delete functions
function confirmDeleteInvoice(invoiceId) {
    const entryId = getEntryId();
    if (!entryId) return;

    Swal.fire({
        title: 'Are you sure?',
        text: "You are about to delete this invoice. This will also reverse all expense settlements. This action cannot be undone!",
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Yes, delete it!',
        cancelButtonText: 'Cancel',
        confirmButtonColor: '#d33',
        cancelButtonColor: '#3085d6'
    }).then((result) => {
        if (result.isConfirmed) {
            deleteInvoice(entryId, invoiceId);
        }
    });
}

async function deleteInvoice(entryId, invoiceId) {
    try {
        const response = await fetch(`/masters/entries/${entryId}/invoices/${invoiceId}`, {
            method: 'DELETE'
        });

        const data = await response.json();
        if (data.success) {
            showSuccess(data.message || 'Invoice deleted successfully');
            redirectToInvoicesTab();
        } else {
            throw new Error(data.message || 'Failed to delete invoice');
        }
    } catch (error) {
        showError('Failed to delete invoice: ' + error.message);
    }
}

// Status update functions
function openStatusModal(invoiceId, currentStatus) {
    const statusSelect = document.getElementById('invoicePaymentStatus');
    const invoiceIdField = document.getElementById('statusInvoiceId');

    if (statusSelect && invoiceIdField) {
        statusSelect.value = currentStatus;
        invoiceIdField.value = invoiceId;

        const modal = new bootstrap.Modal(document.getElementById('invoiceStatusModal'));
        modal.show();
    }
}

async function updateInvoiceStatus() {
    const invoiceId = document.getElementById('statusInvoiceId').value;
    const newStatus = document.getElementById('invoicePaymentStatus').value;
    const entryId = getEntryId();

    if (!entryId) return;

    const updateBtn = document.getElementById('updateInvoiceStatus');
    const originalText = updateBtn.textContent;
    
    try {
        updateBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Updating...';
        updateBtn.disabled = true;

        const response = await fetch(`/masters/entries/${entryId}/invoices/${invoiceId}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ payment_status: newStatus })
        });

        const data = await response.json();
        if (data.success) {
            const modal = bootstrap.Modal.getInstance(document.getElementById('invoiceStatusModal'));
            modal?.hide();
            
            showSuccess(data.message || 'Invoice status updated successfully');
            redirectToInvoicesTab();
        } else {
            throw new Error(data.message || 'Failed to update invoice status');
        }
    } catch (error) {
        showError('Failed to update invoice status: ' + error.message);
    } finally {
        updateBtn.innerHTML = originalText;
        updateBtn.disabled = false;
    }
}

// Handle table actions
function handleTableActions(event) {
    const target = event.target;
    
    // Check for various invoice action buttons
    if (target.matches('.view-invoice') || target.closest('.view-invoice')) {
        event.preventDefault();
        const button = target.matches('.view-invoice') ? target : target.closest('.view-invoice');
        const invoiceId = button.getAttribute('data-id');
        const entryId = getEntryId();
        if (invoiceId && entryId) {
            viewInvoice(entryId, invoiceId);
        }
        return;
    }
    
    if (target.matches('.edit-invoice') || target.closest('.edit-invoice')) {
        event.preventDefault();
        const button = target.matches('.edit-invoice') ? target : target.closest('.edit-invoice');
        const invoiceId = button.getAttribute('data-id');
        const entryId = getEntryId();
        if (invoiceId && entryId) {
            editInvoice(entryId, invoiceId);
        }
        return;
    }
    
    if (target.matches('.delete-invoice') || target.closest('.delete-invoice')) {
        event.preventDefault();
        const button = target.matches('.delete-invoice') ? target : target.closest('.delete-invoice');
        const invoiceId = button.getAttribute('data-id');
        if (invoiceId) {
            confirmDeleteInvoice(invoiceId);
        }
        return;
    }
    
    if (target.matches('.update-status') || target.closest('.update-status')) {
        event.preventDefault();
        const button = target.matches('.update-status') ? target : target.closest('.update-status');
        const invoiceId = button.getAttribute('data-id');
        const currentStatus = button.getAttribute('data-status');
        if (invoiceId) {
            openStatusModal(invoiceId, currentStatus);
        }
        return;
    }
}

// Utility functions
function getEntryId() {
    return window.currentEntryId || 
           document.getElementById('shipDocEntryId')?.value || 
           document.getElementById('shipmentIdForInvoice')?.value;
}

function getAlreadyChargedAmount(expenseId) {
    let total = 0;
    const expenseRows = document.querySelectorAll(`#invoiceItemsTable tbody tr[data-expense-id="${expenseId}"]`);
    
    expenseRows.forEach(row => {
        const chargedInput = row.querySelector('input[name$="[charged_amount_before_vat]"], .charged-amount-edit');
        if (chargedInput) {
            total += parseFloat(chargedInput.value) || 0;
        }
    });
    
    return total;
}

function formatCurrency(amount, currencyCode = '') {
    if (amount === undefined || amount === null) return `${currencyCode} 0.00`;
    const numValue = parseFloat(amount);
    if (isNaN(numValue)) return `${currencyCode} 0.00`;
    return `${currencyCode}${numValue.toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,')}`;
}





function getStatusBadge(status) {
    const statusMap = {
        0: { class: 'badge-soft-warning', text: 'Pending' },
        1: { class: 'badge-soft-info', text: 'Partially Paid' },
        2: { class: 'badge-soft-success', text: 'Paid' },
        3: { class: 'badge-soft-danger', text: 'Cancelled' }
    };
    
    const statusInfo = statusMap[status] || { class: 'badge-soft-secondary', text: 'Unknown' };
    return `<span class="badge ${statusInfo.class}">${statusInfo.text}</span>`;
}

function setLoadingState(isLoading) {
    const saveButton = document.getElementById('saveInvoice');
    if (!saveButton) return;

    if (isLoading) {
        saveButton.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Saving...';
        saveButton.disabled = true;
    } else {
        saveButton.innerHTML = isEditMode ? 'Update Invoice' : 'Create Invoice';
        saveButton.disabled = false;
    }
}

function closeModal(modalElement) {
    const modal = bootstrap.Modal.getInstance(modalElement || document.getElementById('invoiceModal'));
    modal?.hide();
}

function redirectToInvoicesTab() {
    const entryId = getEntryId();
    if (entryId) {
        window.location.href = `/masters/orders/shipment/${entryId}?tab=invoices`;
    }
}

function showSuccess(message) {
    Swal.fire({
        title: 'Success',
        text: message,
        icon: 'success',
        timer: 1500,
        showConfirmButton: false
    });
}

function showError(message) {
    Swal.fire({
        title: 'Error',
        text: message,
        icon: 'error'
    });
}

// Global functions for backward compatibility and inline event handlers
window.updateInvoiceTotal = updateInvoiceTotal;
window.removeInvoiceItem = removeInvoiceItem;
window.formatCurrency = formatCurrency;
window.validateAmount = validateChargedAmount;
window.updateEditVAT = updateEditVAT;
window.validateEditAmount = validateEditAmount;

// Print invoice function
function handlePrintInvoice() {
    const printWindow = window.open('', '_blank');
    
    const elements = {
        number: document.getElementById('viewInvoiceNumber')?.textContent || '',
        date: document.getElementById('viewInvoiceDate')?.textContent || '',
        status: document.getElementById('viewInvoiceStatus')?.textContent || '',
        customer: document.getElementById('viewInvoiceCustomer')?.textContent || '',
        narration: document.getElementById('viewInvoiceNarration')?.textContent || '',
        items: document.getElementById('viewInvoiceItems')?.outerHTML || '',
        total: document.getElementById('viewInvoiceTotal')?.textContent || ''
    };
    
    printWindow.document.write(`
        <html>
        <head>
            <title>Invoice Details</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; }
                table { width: 100%; border-collapse: collapse; margin-top: 20px; }
                th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                th { background-color: #f2f2f2; }
                .header { display: flex; justify-content: space-between; margin-bottom: 20px; }
                .footer { margin-top: 30px; text-align: right; }
                .badge { 
                    padding: 3px 8px; 
                    border-radius: 4px; 
                    font-size: 11px;
                    font-weight: bold;
                }
                .badge-soft-warning { background-color: #fff3cd; color: #856404; }
                .badge-soft-success { background-color: #d4edda; color: #155724; }
                .badge-soft-info { background-color: #d1ecf1; color: #0c5460; }
                .badge-soft-danger { background-color: #f8d7da; color: #721c24; }
                .vat-breakdown-view { font-size: 12px; }
                .vat-breakdown-view hr { margin: 2px 0; }
            </style>
        </head>
        <body>
            <div class="header">
                <div>
                    <h2>Invoice #${elements.number}</h2>
                    <p>Date: ${elements.date}</p>
                </div>
                <div>
                    <p>Status: ${elements.status}</p>
                </div>
            </div>
            <div>
                <p><strong>Customer:</strong> ${elements.customer}</p>
                <p><strong>Narration:</strong> ${elements.narration}</p>
            </div>
            ${elements.items}
            <div class="footer">
                <p><strong>Total:</strong> ${elements.total}</p>
            </div>
        </body>
        </html>
    `);
    printWindow.document.close();
    printWindow.print();
}

// Setup print button event listener
document.addEventListener('DOMContentLoaded', function() {
    const printBtn = document.getElementById('printInvoiceBtn');
    if (printBtn) {
        printBtn.addEventListener('click', function(e) {
            e.preventDefault();
            handlePrintInvoice();
        });
    }
});

console.log('Invoice tab script loaded successfully');

// Add this function to help debug submit button issues
function debugSubmitButtonState() {
    const submitBtn = document.getElementById('submitInvoiceBtn');
    if (submitBtn) {
        console.log('Submit button state:', {
            display: submitBtn.style.display,
            disabled: submitBtn.disabled,
            className: submitBtn.className,
            innerHTML: submitBtn.innerHTML,
            dataInvoiceId: submitBtn.getAttribute('data-invoice-id')
        });
    } else {
        console.log('Submit button not found');
    }
}

