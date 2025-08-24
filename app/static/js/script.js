document.addEventListener('DOMContentLoaded', function () {
    const sidebar = document.getElementById('sidebar');
    const content = document.getElementById('content');
    const sidebarToggle = document.getElementById('sidebarToggle');

    // Function to update collapsed state
    function updateCollapsedState(isCollapsed) {
        if (isCollapsed) {
            sidebar.classList.add('collapsed');
            content.classList.add('collapsed');
            // Close all submenus when collapsing
            document.querySelectorAll('#sidebar .collapse').forEach(submenu => {
                const bsCollapse = bootstrap.Collapse.getInstance(submenu);
                if (bsCollapse) bsCollapse.hide();
            });
        } else {
            sidebar.classList.remove('collapsed');
            content.classList.remove('collapsed');
        }
        localStorage.setItem('sidebarCollapsed', isCollapsed);
    }

    // Toggle sidebar
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function () {
            const isCollapsed = !sidebar.classList.contains('collapsed');
            updateCollapsedState(isCollapsed);
        });
    }

    // Restore sidebar state on page load
    const savedState = localStorage.getItem('sidebarCollapsed') === 'true';
    updateCollapsedState(savedState);

    // Handle submenu clicks when sidebar is collapsed
    document.querySelectorAll('#sidebar .dropdown-toggle').forEach(toggle => {
        toggle.addEventListener('click', function (e) {
            if (sidebar.classList.contains('collapsed')) {
                e.preventDefault();
                e.stopPropagation();
                updateCollapsedState(false);
                const submenuId = this.getAttribute('href');
                setTimeout(() => {
                    const submenu = document.querySelector(submenuId);
                    if (submenu) {
                        bootstrap.Collapse.getOrCreateInstance(submenu).show();
                    }
                }, 300);
            }
        });
    });

    // Initialize all tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize Bootstrap popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Password visibility toggle
    const togglePassword = document.querySelectorAll('.toggle-password');
    togglePassword.forEach(function (button) {
        button.addEventListener('click', function () {
            const input = document.querySelector(this.getAttribute('data-target'));
            if (input) {
                if (input.type === 'password') {
                    input.type = 'text';
                    this.innerHTML = '<i class="fas fa-eye-slash"></i>';
                } else {
                    input.type = 'password';
                    this.innerHTML = '<i class="fas fa-eye"></i>';
                }
            }
        });
    });

    // Confirmation modal
    const confirmationModal = document.getElementById('confirmationModal');
    if (confirmationModal) {
        confirmationModal.addEventListener('show.bs.modal', function (event) {
            const button = event.relatedTarget;
            const action = button.getAttribute('data-action');
            const target = button.getAttribute('data-target');

            const modalTitle = confirmationModal.querySelector('.modal-title');
            const modalBody = confirmationModal.querySelector('.modal-body');
            const confirmButton = confirmationModal.querySelector('.btn-confirm');

            modalTitle.textContent = 'Confirm ' + action;
            modalBody.textContent = 'Are you sure you want to ' + action.toLowerCase() + ' this ' + target + '?';

            confirmButton.setAttribute('href', button.getAttribute('href'));
        });
    }
}); 