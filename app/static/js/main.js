// Sidebar toggle
$(document).ready(function () {
    $('#sidebarCollapse').on('click', function () {
        $('#sidebar').toggleClass('active');
    });

    // Form validation
    $('form').on('submit', function () {
        $(this).addClass('was-validated');
    });

    // Initialize DataTables
    if ($.fn.DataTable) {
        $('.datatable').DataTable({
            language: {
                search: "Search:",
                lengthMenu: "Show _MENU_ entries",
                info: "Showing _START_ to _END_ of _TOTAL_ entries",
                paginate: {
                    first: "First",
                    last: "Last",
                    next: "Next",
                    previous: "Previous"
                },
                emptyTable: "No data available in table"
            }
        });
    }

    // File input change
    $('.custom-file-input').on('change', function () {
        let fileName = $(this).val().split('\\').pop();
        $(this).next('.custom-file-label').html(fileName);
    });

    // Delete confirmation
    $('.delete-confirm').on('click', function (e) {
        if (!confirm('Are you sure you want to delete this item?')) {
            e.preventDefault();
        }
    });

    // Dynamic form fields
    $('.add-form-field').on('click', function () {
        let template = $(this).data('template');
        let container = $(this).data('container');
        $(container).append(template);
    });

    $(document).on('click', '.remove-form-field', function () {
        $(this).closest('.form-field').remove();
    });

    // Password visibility toggle
    $('.toggle-password').on('click', function () {
        let input = $(this).prev('input');
        let type = input.attr('type') === 'password' ? 'text' : 'password';
        input.attr('type', type);
        $(this).toggleClass('fa-eye fa-eye-slash');
    });

    // Dynamic select options
    $('.dynamic-select').on('change', function () {
        let url = $(this).data('url');
        let target = $(this).data('target');
        let value = $(this).val();

        $.get(url, { value: value }, function (data) {
            $(target).html(data);
        });
    });

    // AJAX form submission
    $('.ajax-form').on('submit', function (e) {
        e.preventDefault();
        let form = $(this);
        let url = form.attr('action');
        let method = form.attr('method');
        let data = form.serialize();

        $.ajax({
            url: url,
            method: method,
            data: data,
            success: function (response) {
                showAlert('success', response.message);
                if (response.redirect) {
                    window.location.href = response.redirect;
                }
            },
            error: function (xhr) {
                showAlert('danger', xhr.responseJSON.message || 'An error occurred');
            }
        });
    });

    // Alert function
    function showAlert(type, message) {
        let alert = `
            <div class="alert alert-${type} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        $('.alert-container').html(alert);
    }

    // Initialize tooltips and popovers
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // File upload preview
    $('.file-upload').on('change', function () {
        let file = this.files[0];
        let reader = new FileReader();
        let preview = $(this).data('preview');

        reader.onload = function (e) {
            $(preview).attr('src', e.target.result);
        }

        if (file) {
            reader.readAsDataURL(file);
        }
    });
}); 