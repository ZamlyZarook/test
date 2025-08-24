from flask import render_template, redirect, url_for, jsonify, request, flash, make_response
from flask_login import login_required, current_user
from ..utils_roles import check_route_permission
from app.models.company import CompanyInfo
from app.models.user import User, Role, Menu, RoleMenuPermission, Route, RoutePermission, UserActionPermission
from .utils import generate_company_key
from werkzeug.security import generate_password_hash
from .forms import CreateCompanyForm, EditCompanyForm
import logging
import traceback
from functools import wraps
from flask import request, has_request_context
from flask_login import current_user
from datetime import datetime
from app.super_admin import super_admin_bp
from app import db

# Route Management routes -------------------------------------
# @super_admin_bp.route("/Routes")
# @login_required
# @check_route_permission()
# def manage_routes_page():
#     routes = Route.query.all()
#     roles = Role.query.all()
#     return render_template("super_admin/manage_routes.html", routes=routes, roles=roles)


# @super_admin_bp.route("/update_route_status", methods=['POST'])
# @login_required
# @check_route_permission()
# def update_route_status():
#     try:
#         route_id = request.json.get('route_id')
#         is_active = request.json.get('is_active')
        
#         route = Route.query.get_or_404(route_id)
#         route.is_active = is_active
#         db.session.commit()
        
#         return jsonify({
#             'success': True,
#             'message': f'Route {"activated" if is_active else "deactivated"} successfully'
#         })
        
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({'success': False, 'message': str(e)})

# @super_admin_bp.route("/update_route_permission", methods=['POST'])
# @login_required
# @check_route_permission()
# def update_route_permission():
#     try:
#         route_id = request.json.get('route_id')
#         role_id = request.json.get('role_id')
#         has_access = request.json.get('has_access')
        
#         # Check if permission exists
#         permission = RoutePermission.query.filter_by(
#             route_id=route_id,
#             role_id=role_id
#         ).first()
        
#         if permission:
#             if has_access:
#                 permission.can_access = True
#             else:
#                 db.session.delete(permission)
#         elif has_access:
#             # Create new permission
#             permission = RoutePermission(
#                 route_id=route_id,
#                 role_id=role_id,
#                 can_access=True
#             )
#             db.session.add(permission)
            
#         db.session.commit()
        
#         return jsonify({
#             'success': True,
#             'message': 'Permission updated successfully'
#         })
        
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({'success': False, 'message': str(e)})

# @super_admin_bp.route("/update_route_permissions_bulk", methods=['POST'])
# @login_required
# @check_route_permission()
# def update_route_permissions_bulk():
#     try:
#         route_id = request.json.get('route_id')
#         permissions = request.json.get('permissions')  # List of {role_id, has_access}

#         for perm in permissions:
#             role_id = perm.get('roleId')
#             has_access = perm.get('hasAccess')

#             # Check if permission exists
#             permission = RoutePermission.query.filter_by(
#                 route_id=route_id,
#                 role_id=role_id
#             ).first()

#             if permission:
#                 if has_access:
#                     permission.can_access = True
#                 else:
#                     db.session.delete(permission)
#             elif has_access:
#                 # Create new permission
#                 permission = RoutePermission(
#                     route_id=route_id,
#                     role_id=role_id,
#                     can_access=True
#                 )
#                 db.session.add(permission)

#         db.session.commit()

#         return jsonify({
#             'success': True,
#             'message': 'Permissions updated successfully'
#         })

#     except Exception as e:
#         db.session.rollback()
#         return jsonify({'success': False, 'message': str(e)})

# @super_admin_bp.route("/delete_route/<int:route_id>", methods=['POST'])
# @login_required
# @check_route_permission()
# def delete_route(route_id):
#     try:
#         route = Route.query.get_or_404(route_id)
        
#         # Delete associated permissions first
#         RoutePermission.query.filter_by(route_id=route_id).delete()
        
#         # Delete route
#         db.session.delete(route)
#         db.session.commit()
        
#         return jsonify({
#             'success': True,
#             'message': 'Route deleted successfully'
#         })
        
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({'success': False, 'message': str(e)})

# @super_admin_bp.route("/get_route_permissions", methods=['GET'])
# @login_required
# @check_route_permission()
# def get_route_permissions():
#     try:
#         route_id = request.args.get('route_id')
#         permissions = RoutePermission.query.filter_by(route_id=route_id).all()
        
#         return jsonify({
#             'success': True,
#             'permissions': [{
#                 'role_id': perm.role_id,
#                 'can_access': perm.can_access
#             } for perm in permissions]
#         })
        
#     except Exception as e:
#         return jsonify({'success': False, 'message': str(e)})

# @super_admin_bp.route("/add_route", methods=['POST'])
# @login_required
# @check_route_permission()
# def add_route():
#     try:
#         route_name = request.json.get('route_name')
#         description = request.json.get('description')
        
#         new_route = Route(
#             route_name=route_name,
#             description=description,
#             is_active=True,
#             menu_id=1
#         )
#         db.session.add(new_route)
#         db.session.commit()
        
#         return jsonify({
#             'success': True,
#             'message': 'Route added successfully'
#         })
        
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({'success': False, 'message': str(e)})


# -------------------------------------------------------------
# Roles

# @super_admin_bp.route('/roles')
# @login_required
# @check_route_permission()
# def manage_roles():
#     roles = Role.query.all()
#     return render_template('super_admin/manage_roles.html', 
#                          roles=roles,
#                          title="Role Management")

# @super_admin_bp.route('/role/<int:role_id>', methods=['GET'])
# @login_required
# @check_route_permission()
# def get_role(role_id):
#     role = Role.query.get_or_404(role_id)
#     return jsonify({
#         'role_name': role.role_name,
#         'description': getattr(role, 'description', '')
#     })

# @super_admin_bp.route('/role', methods=['POST'])
# @login_required
# @check_route_permission()
# def create_role():
#     try:
#         data = request.get_json()
#         role = Role(role_name=data['role_name'])
#         db.session.add(role)
#         db.session.commit()
#         return jsonify({'message': 'Success'})
#     except Exception as e:
#         db.session.rollback()
#         print(f"Error creating role: {str(e)}")
#         return jsonify({'message': 'Error creating role'}), 500

# @super_admin_bp.route('/role/<int:role_id>/menus')
# @login_required
# @check_route_permission()
# def get_role_menus(role_id):
#     try:
#         role = Role.query.get_or_404(role_id)
#         menus = Menu.query.all()
        
#         menu_permissions = {p.menu_id: p.can_access for p in role.menu_permissions}
        
#         def format_menu(menu):
#             children = Menu.query.filter_by(parent_id=menu.id).all()
#             return {
#                 'id': menu.id,
#                 'name': menu.name,
#                 'has_access': menu_permissions.get(menu.id, False),
#                 'children': [format_menu(child) for child in children]
#             }
        
#         root_menus = Menu.query.filter_by(parent_id=None).all()
#         menu_tree = [format_menu(menu) for menu in root_menus]
        
#         return jsonify(menu_tree)
#     except Exception as e:
#         print(f"Error getting menus: {str(e)}")
#         return jsonify({'message': 'Error getting menus'}), 500

# @super_admin_bp.route('/role/<int:role_id>/menus', methods=['POST'])
# @login_required
# @check_route_permission()
# def update_role_menus(role_id):
#     try:
#         role = Role.query.get_or_404(role_id)
#         menu_ids = request.json.get('menu_ids', [])
        
#         # Clear existing menu permissions
#         RoleMenuPermission.query.filter_by(role_id=role_id).delete()
        
#         # Add new menu permissions and collect routes
#         route_names = set()
#         for menu_id in menu_ids:
#             # Add menu permission
#             permission = RoleMenuPermission(role_id=role_id, menu_id=menu_id, can_access=True)
#             db.session.add(permission)
            
#             # Get route from menu
#             menu = Menu.query.get(menu_id)
#             if menu and menu.route:
#                 route_names.add(menu.route)
        
#         # Update route permissions
#         for route_name in route_names:
#             route = Route.query.filter_by(route_name=route_name).first()
#             if route:
#                 # Check if permission exists
#                 route_permission = RoutePermission.query.filter_by(
#                     route_id=route.id,
#                     role_id=role_id
#                 ).first()
                
#                 if not route_permission:
#                     route_permission = RoutePermission(
#                         route_id=route.id,
#                         role_id=role_id,
#                         can_access=True
#                     )
#                     db.session.add(route_permission)
        
#         db.session.commit()
#         return jsonify({'message': 'Success'})
        
#     except Exception as e:
#         db.session.rollback()
#         print(f"Error updating permissions: {str(e)}")
#         return jsonify({'message': 'Error updating permissions'}), 500

#-------------------------------------------------------------------
@super_admin_bp.route("/User_Accounts")
@login_required
@check_route_permission()
def manage_user_accounts():
    return render_template("super_admin/manage_users.html")

@super_admin_bp.route("/Licenses")
@login_required
@check_route_permission()
def manage_licenses():
    return render_template("super_admin/license_management.html")

# Company Management Routes (moved from administration)

@super_admin_bp.route("/Company_configuration")
@login_required
@check_route_permission()
def company_configuration():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    pagination = Company.query.paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    total_companies = Company.query.count()
    total_pages = (total_companies + per_page - 1) // per_page
    
    response = make_response(render_template(
        "super_admin/company_configuration.html",
        companies=pagination.items,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        pagination=pagination
    ))
    
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@super_admin_bp.route("/add_company", methods=['POST'])
@login_required
@check_route_permission()
def add_company():
    form = CreateCompanyForm()
    
    if form.validate_on_submit():
        try:
            company_key = generate_company_key()
            while Company.query.filter_by(company_key=company_key).first():
                company_key = generate_company_key()

            new_company = Company(
                company_name=form.company_name.data,
                company_key=company_key,
                company_code=form.company_code.data,
                email=form.email.data,
                website=form.website.data,
                contact_number=form.contact_number.data,
                address=form.address.data
            )
            
            db.session.add(new_company)
            db.session.commit()
            
            flash('Company added successfully!', 'success')
            return redirect(url_for('super_admin.company_configuration'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding company: {str(e)}', 'error')
            print("Error:", str(e))
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{getattr(form, field).label.text}: {error}', 'error')
    
    return redirect(url_for('super_admin.company_configuration'))

@super_admin_bp.route("/add_company_page")
@login_required
@check_route_permission()
def add_company_page():
    form = CreateCompanyForm()
    response = make_response(render_template(
        "super_admin/add_company.html",
        form=form
    ))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@super_admin_bp.route("/edit_company/<int:company_id>")
@login_required
@check_route_permission()
def edit_company(company_id):
    company = Company.query.get_or_404(company_id)
    form = EditCompanyForm(obj=company)
    
    response = make_response(render_template(
        "super_admin/edit_company.html",
        company=company,
        form=form
    ))
    
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@super_admin_bp.route("/update_company/<int:company_id>", methods=['POST'])
@login_required
@check_route_permission()
def update_company(company_id):
    company = Company.query.get_or_404(company_id)
    form = EditCompanyForm()
    
    if form.validate_on_submit():
        try:
            company.company_name = form.company_name.data
            company.company_code = form.company_code.data
            company.email = form.email.data
            company.website = form.website.data
            company.contact_number = form.contact_number.data
            company.address = form.address.data
            
            db.session.commit()
            flash('Company updated successfully!', 'success')
            return redirect(url_for('super_admin.company_configuration'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating company: {str(e)}', 'error')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{getattr(form, field).label.text}: {error}', 'error')
    
    return redirect(url_for('super_admin.edit_company', company_id=company_id))

# App Logs Handling

@super_admin_bp.route("/System_Logs")
@login_required
@check_route_permission()
def system_logs():
    """View system logs with filtering and pagination."""
    page = request.args.get('page', 1, type=int)
    module = request.args.get('module', '')
    level = request.args.get('level', '')
    search = request.args.get('search', '')
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')
    per_page = 50
    
    # Start with base query
    query = ApplicationLog.query
    
    # Apply filters
    if module:
        query = query.filter(ApplicationLog.module == module)
    if level:
        query = query.filter(ApplicationLog.level == level)
    if search:
        query = query.filter(
            db.or_(
                ApplicationLog.message.ilike(f'%{search}%'),
                ApplicationLog.module.ilike(f'%{search}%')
            )
        )
    if from_date:
        query = query.filter(
            ApplicationLog.created_at >= datetime.strptime(from_date, '%Y-%m-%d')
        )
    if to_date:
        query = query.filter(
            ApplicationLog.created_at <= datetime.strptime(to_date + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
        )
    
    # Get distinct values for filters
    modules = db.session.query(ApplicationLog.module).distinct().all()
    levels = db.session.query(ApplicationLog.level).distinct().all()
    
    # Get paginated results
    logs = query.order_by(ApplicationLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template(
        'super_admin/system_logs.html',  # Update template path
        logs=logs,
        modules=modules,
        levels=levels,
        selected_module=module,
        selected_level=level,
        search=search,
        from_date=from_date,
        to_date=to_date
    )

@super_admin_bp.route("/api/clear_logs", methods=['POST'])
@login_required
@check_route_permission()
def clear_logs():
    """Clear logs based on filters."""
    try:
        data = request.json
        module = data.get('module')
        level = data.get('level')
        from_date = data.get('from_date')
        to_date = data.get('to_date')
        
        query = ApplicationLog.query
        
        if module:
            query = query.filter(ApplicationLog.module == module)
        if level:
            query = query.filter(ApplicationLog.level == level)
        if from_date:
            query = query.filter(
                ApplicationLog.created_at >= datetime.strptime(from_date, '%Y-%m-%d')
            )
        if to_date:
            query = query.filter(
                ApplicationLog.created_at <= datetime.strptime(to_date + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
            )
            
        # Delete filtered logs
        count = query.delete()
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'Successfully cleared {count} logs',
            'count': count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    


@super_admin_bp.route('/menus')
@login_required
def menus():
    # Fetch the parent menus (those with parent_id=None)
    menus = Menu.query.filter_by(parent_id=None).all()

    # Loop through each menu to fetch its submenus and sub-submenus
    for menu in menus:
        # Fetch submenus for each parent menu
        menu.submenus = Menu.query.filter_by(parent_id=menu.id).all()

        # For each submenu, fetch the sub-submenus
        for submenu in menu.submenus:
            submenu.subsubmenus = Menu.query.filter_by(parent_id=submenu.id).all()

    # Dynamically fetch the current route including the blueprint name
    current_route = request.path
    print(f"Current route: {current_route}")

    # Fetch the menu ID for the current route
    current_menu = Menu.query.filter_by(route=current_route).first()

    if current_menu:
        menu_id = current_menu.id
        print(f"Current menu ID for route '{current_route}': {menu_id}")
    else:
        menu_id = None
        print(f"No menu found for route '{current_route}'")

    # Fetch user permissions for the current user and the fetched menu_id
    if menu_id:
        user_permissions = UserActionPermission.query.filter(
            UserActionPermission.user_id == current_user.id,
            UserActionPermission.menu_id == menu_id
        ).all()
    else:
        user_permissions = []

    # Create a dictionary of permissions for easier access in the template
    permissions_dict = {}

    # Populate the permissions_dict with actions for each menu_id
    for permission in user_permissions:
        permissions_dict[permission.menu_id] = {
            'create': permission.create,
            'edit': permission.edit,
            'delete': permission.delete,
            'print': permission.print
        }

    # Debug: Print the permissions_dict to verify its contents
    print(f"Permissions for current user: {permissions_dict}")

    return render_template('super_admin/manage_menu.html', menus=menus, permissions_dict=permissions_dict, current_menu_id=menu_id)


# Route to create a new menu
@super_admin_bp.route('/menus/create', methods=['POST'])
def create_menu():
    name = request.form.get('name')
    icon = request.form.get('icon')
    parent_id = request.form.get('parent_id') or None
    route = request.form.get('route')
    order_index = request.form.get('order_index')
    is_active = bool(request.form.get('is_active'))

    new_menu = Menu(
        name=name,
        icon=icon,
        parent_id=parent_id,
        route=route,
        order_index=order_index,
        is_active=is_active
    )
    db.session.add(new_menu)
    db.session.commit()

    if route:
        existing_route = Route.query.filter_by(route_name=route).first()
        if not existing_route:
            new_route = Route(route_name=route, description=f"Route for {name}", menu_id=new_menu.id, is_active=True)
            db.session.add(new_route)
        else:
            existing_route.description = f"Updated route for {name}"
            existing_route.is_active = True
        db.session.commit()

    flash('Menu created successfully', 'success')
    return redirect(url_for('super_admin.menus'))

# Route to edit an existing menu
@super_admin_bp.route('/menus/edit/<int:menu_id>', methods=['POST'])
def edit_menu(menu_id):
    menu = Menu.query.get_or_404(menu_id)
    
    # Update menu fields
    menu.name = request.form.get('name')
    menu.icon = request.form.get('icon')
    menu.parent_id = request.form.get('parent_id') or None
    new_route_name = request.form.get('route')
    menu.order_index = request.form.get('order_index')
    menu.is_active = request.form.get('is_active') == '1'  # This will return True if '1' is selected, False if '0' is selected

    # Handle associated route
    if new_route_name:
        if menu.routes:  # Existing route
            menu.routes.route_name = new_route_name
            menu.routes.description = f"Updated route for {menu.name}"
            menu.routes.is_active = True
        else:  # No associated route
            new_route = Route(route_name=new_route_name, description=f"Route for {menu.name}", menu_id=menu.id, is_active=True)
            db.session.add(new_route)
        
        # Update the menu's route column
        menu.route = new_route_name
    elif menu.routes:  # Remove the route if no new route is provided
        db.session.delete(menu.routes)
        menu.route = None  # Clear the route column in the menu table

    db.session.commit()
    flash('Menu and associated route updated successfully', 'success')
    return redirect(url_for('super_admin.menus'))

# Route to delete a menu
@super_admin_bp.route('/menus/delete/<int:menu_id>', methods=['POST'])
def delete_menu(menu_id):
    print(f"Starting to delete menu with ID: {menu_id}")

    try:
        # Fetch the menu to be deleted
        menu = Menu.query.get_or_404(menu_id)
        print(f"Found menu: {menu.id} with route: {menu.route}")

        # Recursive deletion of submenus and related records
        def delete_submenus(menu_id):
            print(f"Looking for submenus under menu ID: {menu_id}")
            submenus = Menu.query.filter_by(parent_id=menu_id).all()

            for submenu in submenus:
                print(f"Deleting related records for submenu ID: {submenu.id}")

                # Delete related RoleMenuPermission and UserActionPermission
                RoleMenuPermission.query.filter_by(menu_id=submenu.id).delete()
                UserActionPermission.query.filter_by(menu_id=submenu.id).delete()
                print(f"Deleted permissions for submenu ID: {submenu.id}")

                # Delete related routes and route permissions
                if submenu.route:
                    submenu_route = Route.query.filter_by(route_name=submenu.route).first()
                    if submenu_route:
                        RoutePermission.query.filter_by(route_id=submenu_route.id).delete()
                        db.session.delete(submenu_route)
                        print(f"Deleted route {submenu.route} for submenu ID: {submenu.id}")

                # Recursively delete child submenus
                delete_submenus(submenu.id)

                # Delete the submenu
                db.session.delete(submenu)
                print(f"Deleted submenu ID: {submenu.id}")

        # Call the recursive function to delete all submenus and sub-submenus
        delete_submenus(menu_id)

        # Delete related records for the main menu
        RoleMenuPermission.query.filter_by(menu_id=menu.id).delete()
        UserActionPermission.query.filter_by(menu_id=menu.id).delete()
        print(f"Deleted permissions for menu ID: {menu.id}")

        # Delete the main menu's route and its permissions
        if menu.route:
            menu_route = Route.query.filter_by(route_name=menu.route).first()
            if menu_route:
                RoutePermission.query.filter_by(route_id=menu_route.id).delete()
                db.session.delete(menu_route)
                print(f"Deleted route {menu.route} for menu ID: {menu.id}")

        # Delete the main menu
        db.session.delete(menu)
        print(f"Deleted menu with ID: {menu.id}")

        db.session.commit()
        print("Transaction committed successfully.")
        flash('Menu, its submenus, and related permissions deleted successfully!', 'success')

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        db.session.rollback()
        print("Transaction rolled back.")
        flash(f'Error occurred while deleting menu: {e}', 'danger')

    return redirect(url_for('super_admin.menus'))


@super_admin_bp.route('/create_submenu/<int:parent_id>', methods=['POST'])
def create_submenu(parent_id):
    # Get parent menu
    parent_menu = Menu.query.get_or_404(parent_id)

    # Get form data
    name = request.form.get('name')
    icon = request.form.get('icon')
    route = request.form.get('route')
    order_index = request.form.get('order_index')
    is_active = bool(int(request.form.get('is_active', '0')))

    # Validate required fields
    if not name:
        flash('Name is required.', 'error')
        return redirect(url_for('super_admin.menus'))

    # Create submenu
    submenu = Menu(
        name=name,
        icon=icon,
        parent_id=parent_menu.id,
        route=route,
        order_index=int(order_index),
        is_active=is_active
    )
    db.session.add(submenu)
    db.session.commit()

    # Update the routes table
    if route:  # Check if the route is not empty
        existing_route = Route.query.filter_by(route_name=route).first()
        if not existing_route:
            new_route = Route(route_name=route, description=f"Route for submenu {name}", menu_id=submenu.id, is_active=True)
            db.session.add(new_route)
        else:
            existing_route.description = f"Updated route for submenu {name}"
            existing_route.is_active = True
        db.session.commit()
    else:
        print("Route value is empty; no record will be created in the Routes table.")


    flash('Submenu added successfully!', 'success')
    return redirect(url_for('super_admin.menus'))


@super_admin_bp.route('/edit_submenu/<int:submenu_id>', methods=['POST'])
def edit_submenu(submenu_id):
    submenu = Menu.query.get_or_404(submenu_id)

    # Update submenu properties
    submenu.name = request.form.get('name', submenu.name)
    submenu.icon = request.form.get('icon', submenu.icon)
    new_route_name = request.form.get('route', submenu.route)
    submenu.order_index = request.form.get('order_index', submenu.order_index)
    submenu.is_active = bool(int(request.form.get('is_active', submenu.is_active)))

    if new_route_name:
        if submenu.routes:  # Existing route
            submenu.routes.route_name = new_route_name
            submenu.routes.description = f"Updated route for {submenu.name}"
            submenu.routes.is_active = True
        else:  # No associated route
            new_route = Route(route_name=new_route_name, description=f"Route for {submenu.name}", menu_id=submenu.id, is_active=True)
            db.session.add(new_route)
        
        # Update the menu's route column
        submenu.route = new_route_name
    elif submenu.routes:  # Remove the route if no new route is provided
        db.session.delete(submenu.routes)
        submenu.route = None  # Clear the route column in the menu table

    db.session.commit()
    flash('Submenu updated successfully!', 'success')
    return redirect(url_for('super_admin.menus', parent_id=submenu.parent_id))


@super_admin_bp.route('/delete_submenu/<int:submenu_id>', methods=['POST'])
def delete_submenu(submenu_id):
    print(f"Starting to delete submenu with ID: {submenu_id}")

    try:
        submenu = Menu.query.get_or_404(submenu_id)
        print(f"Found submenu: {submenu.id} with route: {submenu.route}")

        # Recursive deletion of submenus and related records
        def delete_subsubmenus(menu_id):
            print(f"Looking for submenus under menu ID: {menu_id}")
            submenus = Menu.query.filter_by(parent_id=menu_id).all()

            for submenu in submenus:
                print(f"Deleting related records for submenu ID: {submenu.id}")

                # Delete related RoleMenuPermission and UserActionPermission
                RoleMenuPermission.query.filter_by(menu_id=submenu.id).delete()
                UserActionPermission.query.filter_by(menu_id=submenu.id).delete()
                print(f"Deleted permissions for submenu ID: {submenu.id}")

                # Delete related routes and route permissions
                if submenu.route:
                    submenu_route = Route.query.filter_by(route_name=submenu.route).first()
                    if submenu_route:
                        RoutePermission.query.filter_by(route_id=submenu_route.id).delete()
                        db.session.delete(submenu_route)
                        print(f"Deleted route {submenu.route} for submenu ID: {submenu.id}")

                # Recursively delete child submenus
                delete_subsubmenus(submenu.id)

                # Delete the submenu
                db.session.delete(submenu)
                print(f"Deleted submenu ID: {submenu.id}")

        # Delete child submenus first
        delete_subsubmenus(submenu_id)

        # Delete related records for the main submenu
        RoleMenuPermission.query.filter_by(menu_id=submenu.id).delete()
        UserActionPermission.query.filter_by(menu_id=submenu.id).delete()

        # Find and delete ALL routes associated with this menu
        routes = Route.query.filter_by(menu_id=submenu.id).all()
        for route in routes:
            # Delete the route permissions first
            RoutePermission.query.filter_by(route_id=route.id).delete()
            # Then delete the route itself
            db.session.delete(route)
            print(f"Deleted route with ID: {route.id} for menu ID: {submenu.id}")

        # Also check by route name if menu.route exists
        if submenu.route:
            route_by_name = Route.query.filter_by(route_name=submenu.route).first()
            if route_by_name:
                RoutePermission.query.filter_by(route_id=route_by_name.id).delete()
                db.session.delete(route_by_name)
                print(f"Deleted route {submenu.route} for submenu ID: {submenu.id}")

        # Delete the main submenu
        db.session.delete(submenu)
        print(f"Deleted submenu with ID: {submenu.id}")

        db.session.commit()
        print("Transaction committed successfully.")

        return redirect(url_for('super_admin.menus'))

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        db.session.rollback()
        print("Transaction rolled back.")
        return redirect(url_for('super_admin.menus'))

@super_admin_bp.route('/add_subsubmenu/<int:submenu_id>', methods=['POST'])
def add_subsubmenu(submenu_id):
    submenu = Menu.query.get_or_404(submenu_id)

    # Get form data
    name = request.form.get('name')
    icon = request.form.get('icon')
    route = request.form.get('route')
    order_index = request.form.get('order_index')
    is_active = bool(int(request.form.get('is_active')))

    # Create new sub-submenu
    new_subsubmenu = Menu(
        name=name,
        icon=icon,
        route=route,
        order_index=order_index,
        is_active=is_active,
        parent_id=submenu.id  # Linking subsubmenu to its parent submenu
    )

    # Add new sub-submenu to the database
    db.session.add(new_subsubmenu)
    db.session.commit()

    # Update the routes table
    existing_route = Route.query.filter_by(route_name=route).first()
    if not existing_route:
        new_route = Route(route_name=route, description=f"Route for sub-submenu {name}", menu_id=new_subsubmenu.id, is_active=True)
        db.session.add(new_route)
    else:
        existing_route.description = f"Updated route for sub-submenu {name}"
        existing_route.is_active = True
    db.session.commit()

    flash('Sub-Submenu created successfully!', 'success')
    return redirect(url_for('super_admin.menus', parent_id=submenu.id))


@super_admin_bp.route('/edit_subsubmenu/<int:subsubmenu_id>', methods=['POST'])
def edit_subsubmenu(subsubmenu_id):
    subsubmenu = Menu.query.get_or_404(subsubmenu_id)

    # Update subsubmenu properties
    subsubmenu.name = request.form.get('name', subsubmenu.name)
    subsubmenu.icon = request.form.get('icon', subsubmenu.icon)
    new_route_name = request.form.get('route', subsubmenu.route)
    subsubmenu.order_index = request.form.get('order_index', subsubmenu.order_index)
    subsubmenu.is_active = bool(int(request.form.get('is_active', subsubmenu.is_active)))

    if new_route_name:
        if subsubmenu.routes:  # Existing route
            subsubmenu.routes.route_name = new_route_name
            subsubmenu.routes.description = f"Updated route for {subsubmenu.name}"
            subsubmenu.routes.is_active = True
        else:  # No associated route
            new_route = Route(route_name=new_route_name, description=f"Route for {subsubmenu.name}", menu_id=subsubmenu.id, is_active=True)
            db.session.add(new_route)
        
        # Update the menu's route column
        subsubmenu.route = new_route_name
    elif subsubmenu.routes:  # Remove the route if no new route is provided
        db.session.delete(subsubmenu.routes)
        subsubmenu.route = None  # Clear the route column in the menu table    

    db.session.commit()
    flash('Sub-Submenu updated successfully!', 'success')
    return redirect(url_for('super_admin.menus', parent_id=subsubmenu.parent_id))

@super_admin_bp.route('/delete_subsubmenu/<int:subsubmenu_id>', methods=['POST'])
def delete_subsubmenu(subsubmenu_id):
    subsubmenu = Menu.query.get_or_404(subsubmenu_id)
    subsubmenu_route_to_check = subsubmenu.route  

    UserActionPermission.query.filter_by(menu_id=subsubmenu.id).delete()

    RoleMenuPermission.query.filter_by(menu_id=subsubmenu.id).delete()

    if subsubmenu_route_to_check:
        subsubmenu_route = Route.query.filter_by(route_name=subsubmenu_route_to_check).first()
        if subsubmenu_route:
            RoutePermission.query.filter_by(route_id=subsubmenu_route.id).delete()
            db.session.delete(subsubmenu_route)

    # Delete the subsubmenu
    db.session.delete(subsubmenu)
    db.session.commit()

    flash('Sub-Submenu and related permissions deleted successfully!', 'success')
    return redirect(url_for('super_admin.menus', parent_id=subsubmenu.parent_id))

@super_admin_bp.route('/permissions', methods=['GET'])
def permissions():
    def get_roles_for_user(user):
        # Fetch all roles first
        all_roles = Role.query.all()
        print(f"All roles: {[role.role_name for role in all_roles]}")  # Debug: Log all roles

        # Initialize filtered_roles as empty
        filtered_roles = []

        # Filter roles based on user's role
        if user.role == 'admin':
            # Admin cannot adjust Admin or Super Admin
            filtered_roles = [role for role in all_roles if role.role_name not in ['admin', 'super_admin']]
        else:
            # Super Admin or other roles can view all
            filtered_roles = all_roles

        print(f"Roles for user '{user.role}': {[role.role_name for role in filtered_roles]}")  # Debug: Log filtered roles
        return filtered_roles

    # Use the current user to filter roles
    roles = get_roles_for_user(current_user)

    # Load menus with submenus and sub-submenus
    menus = Menu.query.filter_by(parent_id=None).options(db.joinedload(Menu.children).joinedload(Menu.children)).all()

    return render_template('super_admin/permissions.html', roles=roles, menus=menus)

@super_admin_bp.route('/update_permission', methods=['POST'])
def update_permission():
    data = request.get_json()
    role_id = data['role_id']
    menu_id = data['menu_id']
    can_access = data['can_access']
    
    print(f"[DEBUG] Received request to update permission: role_id={role_id}, menu_id={menu_id}, can_access={can_access}")
    print(f"[DEBUG] Full request data: {data}")

    try:
        menu = Menu.query.get(menu_id)
        if not menu:
            print(f"[ERROR] Menu with ID {menu_id} not found in database")
            return jsonify({'message': 'Menu not found'}), 404
        
        print(f"[DEBUG] Found menu: id={menu.id}, name={menu.name}, route={menu.route}")

        def get_all_descendants(menu):
            """Recursively get all descendants of a menu"""
            descendants = []
            for child in menu.children:
                descendants.append(child)
                descendants.extend(get_all_descendants(child))
            return descendants

        def get_all_ancestors(menu):
            """Recursively get all ancestors of a menu"""
            ancestors = []
            current = menu.parent
            while current:
                ancestors.append(current)
                current = current.parent
            return ancestors

        def is_leaf_node(menu):
            """Check if the menu is a leaf node"""
            is_leaf = len(menu.children) == 0
            print(f"[DEBUG] Menu '{menu.name}' is leaf node: {is_leaf}")
            return is_leaf

        def update_user_permissions(menu_id, role_id, role_permission):
            """Update user permissions based on role permission changes"""
            # Get all users with this role
            users_with_role = User.query.filter_by(role_id=role_id).all()
            print(f"[DEBUG] Found {len(users_with_role)} users with role_id={role_id}")
            
            for user in users_with_role:
                print(f"[DEBUG] Processing user: id={user.id}, username={user.username}")
                # Find or create user permission record
                user_permission = UserActionPermission.query.filter_by(
                    user_id=user.id,
                    menu_id=menu_id,
                    role_id=role_id
                ).first()

                if not user_permission:
                    print(f"[DEBUG] Creating new user permission for user_id={user.id}, menu_id={menu_id}")
                    user_permission = UserActionPermission(
                        user_id=user.id,
                        menu_id=menu_id,
                        role_id=role_id,
                        access=role_permission.can_access,
                        create=role_permission.can_create,
                        edit=role_permission.can_edit,
                        delete=role_permission.can_delete,
                        print=role_permission.can_print
                    )
                    db.session.add(user_permission)
                    print(f"[DEBUG] Added new user permission to session: {user_permission}")
                else:
                    print(f"[DEBUG] Updating existing user permission for user_id={user.id}, menu_id={menu_id}")
                    # Update access permission
                    user_permission.access = role_permission.can_access

                    # If role denies access, ensure all action permissions are denied
                    if not role_permission.can_access:
                        user_permission.create = False
                        user_permission.edit = False
                        user_permission.delete = False
                        user_permission.print = False
                    else:
                        # If role grants access, set the action permissions to match role permissions
                        user_permission.create = role_permission.can_create
                        user_permission.edit = role_permission.can_edit
                        user_permission.delete = role_permission.can_delete
                        user_permission.print = role_permission.can_print
                    
                    print(f"[DEBUG] Updated user permission: access={user_permission.access}, create={user_permission.create}, edit={user_permission.edit}, delete={user_permission.delete}, print={user_permission.print}")

        def update_single_menu_permission(menu, can_access, include_actions=False):
            """Update permission for a single menu"""
            print(f"[DEBUG] Updating permission for menu: id={menu.id}, name={menu.name}, can_access={can_access}, include_actions={include_actions}")
            
            permission = RoleMenuPermission.query.filter_by(
                role_id=role_id, 
                menu_id=menu.id
            ).first()

            if not permission:
                print(f"[DEBUG] Creating new role menu permission for menu_id={menu.id}")
                permission = RoleMenuPermission(
                    role_id=role_id,
                    menu_id=menu.id,
                    can_access=can_access
                )
                db.session.add(permission)
                print(f"[DEBUG] Added new role menu permission to session")
            else:
                print(f"[DEBUG] Updating existing role menu permission for menu_id={menu.id} from can_access={permission.can_access} to can_access={can_access}")
                permission.can_access = can_access

            # Update action permissions for leaf nodes
            if include_actions and is_leaf_node(menu):
                print(f"[DEBUG] Updating action permissions for leaf node menu_id={menu.id}")
                permission.can_create = can_access
                permission.can_edit = can_access
                permission.can_delete = can_access
                permission.can_print = can_access
                print(f"[DEBUG] Set all action permissions to {can_access}")

            # Update user permissions after role permission change
            update_user_permissions(menu.id, role_id, permission)

            # Update route permissions if applicable
            if menu.route:
                print(f"[DEBUG] Menu has route: {menu.route}, checking route permissions")
                route = Route.query.filter_by(route_name=menu.route).first()
                if route:
                    print(f"[DEBUG] Found route: id={route.id}, name={route.route_name}")
                    route_permission = RoutePermission.query.filter_by(
                        route_id=route.id,
                        role_id=role_id
                    ).first()
                    
                    if not route_permission:
                        print(f"[DEBUG] Creating new route permission for route_id={route.id}")
                        route_permission = RoutePermission(
                            route_id=route.id,
                            role_id=role_id,
                            can_access=can_access
                        )
                        db.session.add(route_permission)
                        print(f"[DEBUG] Added new route permission to session")
                    else:
                        print(f"[DEBUG] Updating existing route permission from can_access={route_permission.can_access} to can_access={can_access}")
                        route_permission.can_access = can_access

        # Start transaction
        print("[DEBUG] Starting database transaction (nested)")

        # 1. Update the current menu
        if is_leaf_node(menu):
            print(f"[DEBUG] Processing leaf node menu_id={menu_id}")
            permission = RoleMenuPermission.query.filter_by(
                role_id=role_id,
                menu_id=menu_id
            ).first()

            if not permission:
                print(f"[DEBUG] Creating new role permission for leaf menu_id={menu_id}")
                permission = RoleMenuPermission(
                    role_id=role_id,
                    menu_id=menu_id,
                    can_access=can_access
                )
                db.session.add(permission)
                print(f"[DEBUG] Added new role permission to session")
            else:
                print(f"[DEBUG] Updating existing role permission for leaf menu_id={menu_id} from can_access={permission.can_access} to can_access={can_access}")
                permission.can_access = can_access

            # Update action permissions if provided
            if can_access:
                # If specific actions are provided in the request, use those
                permission.can_create = data.get('can_create', True)
                permission.can_edit = data.get('can_edit', True)
                permission.can_delete = data.get('can_delete', True)
                permission.can_print = data.get('can_print', True)
                print(f"[DEBUG] Updated action permissions: create={permission.can_create}, edit={permission.can_edit}, delete={permission.can_delete}, print={permission.can_print}")
            else:
                permission.can_create = False
                permission.can_edit = False
                permission.can_delete = False
                permission.can_print = False
                print("[DEBUG] Disabled all action permissions because can_access=False")

            # Update user permissions after role permission change
            update_user_permissions(menu_id, role_id, permission)
        else:
            print(f"[DEBUG] Processing non-leaf node menu_id={menu_id}")
            update_single_menu_permission(menu, can_access)

        # 2. If menu is being selected, ensure all ancestors are accessible
        if can_access:
            ancestors = get_all_ancestors(menu)
            print(f"[DEBUG] Found {len(ancestors)} ancestors for menu_id={menu_id}")
            for ancestor in ancestors:
                print(f"[DEBUG] Processing ancestor: id={ancestor.id}, name={ancestor.name}")
                update_single_menu_permission(ancestor, True)

        # 3. Update all descendants
        descendants = get_all_descendants(menu)
        print(f"[DEBUG] Found {len(descendants)} descendants for menu_id={menu_id}")
        for descendant in descendants:
            print(f"[DEBUG] Processing descendant: id={descendant.id}, name={descendant.name}")
            update_single_menu_permission(descendant, can_access, include_actions=True)

        # 4. Special handling for parent menu selection
        if can_access and menu.parent:
            print(f"[DEBUG] Processing special case for parent menu: id={menu.parent.id}, name={menu.parent.name}")
            siblings = Menu.query.filter_by(parent_id=menu.parent.id).all()
            print(f"[DEBUG] Found {len(siblings)} siblings for menu_id={menu_id}")
            
            sibling_permissions = []
            for sibling in siblings:
                perm = RoleMenuPermission.query.filter_by(
                    role_id=role_id,
                    menu_id=sibling.id
                ).first()
                sibling_permissions.append((sibling.id, perm.can_access if perm else False))
            
            print(f"[DEBUG] Sibling permissions: {sibling_permissions}")
            
            all_siblings_access = all(
                RoleMenuPermission.query.filter_by(
                    role_id=role_id,
                    menu_id=sibling.id,
                    can_access=True
                ).first() is not None
                for sibling in siblings
            )
            
            print(f"[DEBUG] All siblings have access: {all_siblings_access}")
            
            if all_siblings_access:
                parent_permission = RoleMenuPermission.query.filter_by(
                    role_id=role_id,
                    menu_id=menu.parent.id
                ).first()
                
                if parent_permission:
                    print(f"[DEBUG] Updating parent permission from can_access={parent_permission.can_access} to can_access=True")
                    parent_permission.can_access = True
                    # Update user permissions for parent menu
                    update_user_permissions(menu.parent.id, role_id, parent_permission)

        # Check session state before commit
        print(f"[DEBUG] Session state before commit: {db.session.new}, {db.session.dirty}")
        print("[DEBUG] Committing transaction")
        db.session.commit()
        print("[DEBUG] Transaction committed successfully")
        
        # Verify after commit
        verification = RoleMenuPermission.query.filter_by(role_id=role_id, menu_id=menu_id).first()
        print(f"[DEBUG] Verification after commit - Permission exists: {verification is not None}")
        if verification:
            print(f"[DEBUG] Permission values: can_access={verification.can_access}, can_create={verification.can_create}, can_edit={verification.can_edit}, can_delete={verification.can_delete}, can_print={verification.can_print}")
        
        return jsonify({'message': 'Permissions updated successfully'})

    except Exception as e:
        print(f"[ERROR] Exception occurred: {str(e)}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        db.session.rollback()
        print(f"[ERROR] Transaction rolled back due to error: {str(e)}")
        return jsonify({'message': f'Error updating permissions: {str(e)}'}), 500 


@super_admin_bp.route('/fetch_permissions/<int:role_id>', methods=['GET'])
def fetch_permissions(role_id):
    print(f"[DEBUG] Fetching permissions for role_id={role_id}")
    try:
        permissions = RoleMenuPermission.query.filter_by(role_id=role_id).all()
        print(f"[DEBUG] Found {len(permissions)} permission records")
        
        response = []
        for permission in permissions:
            print(f"[DEBUG] Permission - menu_id={permission.menu_id}, can_access={permission.can_access}, can_create={permission.can_create}, can_edit={permission.can_edit}, can_delete={permission.can_delete}, can_print={permission.can_print}")
            response.append({
                'menu_id': permission.menu_id,
                'can_access': permission.can_access,
                'can_create': permission.can_create,
                'can_edit': permission.can_edit,
                'can_delete': permission.can_delete,
                'can_print': permission.can_print
            })
        
        return jsonify({'permissions': response})
    except Exception as e:
        print(f"[ERROR] Error fetching permissions: {str(e)}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return jsonify({'message': f'Error fetching permissions: {str(e)}'}), 500
    

@super_admin_bp.route('/get-permitted-menus', methods=['GET'])
@login_required
def get_permitted_menus():
    role_id = current_user.role_id  # Assuming the role is attached to the user
    print(f"Fetching permitted menus for role_id: {role_id}")

    # Get all permitted menus with submenus and sub-submenus
    menus = Menu.query.filter_by(parent_id=None).options(db.joinedload(Menu.children).joinedload(Menu.children)).all()
    permitted_menus = []

    for menu in menus:
        if has_permission(menu.id, role_id):
            menu_data = {
                'id': menu.id,
                'name': menu.name,
                'icon': menu.icon,
                'route': menu.route,
                'children': []
            }

            # Include submenus and sub-submenus if permitted
            for child in menu.children:
                if has_permission(child.id, role_id):
                    child_data = {
                        'id': child.id,
                        'name': child.name,
                        'icon': child.icon,
                        'route': child.route,
                        'children': []
                    }
                    
                    for subChild in child.children:
                        if has_permission(subChild.id, role_id):
                            child_data['children'].append({
                                'id': subChild.id,
                                'name': subChild.name,
                                'route': subChild.route
                            })

                    menu_data['children'].append(child_data)

            permitted_menus.append(menu_data)

    return jsonify(permitted_menus)


def has_permission(menu_id, role_id):
    # Helper function to check if the user has permission for a specific menu
    permission = RoleMenuPermission.query.filter_by(menu_id=menu_id, role_id=role_id).first()
    return permission and permission.can_access


@super_admin_bp.route('/get-role-menus/<int:role_id>', methods=['GET'])
def get_role_menus(role_id):
    # Fetch menus accessible to the role
    role_menu_permissions = db.session.query(
        RoleMenuPermission.menu_id,
        Menu.name.label('menu_name'),
        Menu.parent_id.label('parent_id')
    ).join(Menu, Menu.id == RoleMenuPermission.menu_id).filter(
        RoleMenuPermission.role_id == role_id
    ).all()

    # Organize menus into a nested structure (menu -> submenu -> sub-submenu)
    menus = {}
    for perm in role_menu_permissions:
        if perm.parent_id is None:  # Top-level menu
            menus[perm.menu_id] = {
                'id': perm.menu_id,
                'name': perm.menu_name,
                'submenus': []
            }
        else:  # Submenu or sub-submenu
            parent_menu = menus.get(perm.parent_id)
            if parent_menu:
                parent_menu['submenus'].append({
                    'id': perm.menu_id,
                    'name': perm.menu_name
                })

    return jsonify({'menus': list(menus.values())})

@super_admin_bp.route('/save-permissions', methods=['POST'])
def save_permissions():
    data = request.json
    role_id = data.get('role_id')
    permissions = data.get('permissions', [])

    for perm in permissions:
        user_action_permission = UserActionPermission(
            role_id=role_id,
            menu_id=perm['menu_id'],
            access=perm.get('access', False),
            create=perm.get('create', False),
            edit=perm.get('edit', False),
            delete=perm.get('delete', False),
            print=perm.get('print', False)
        )
        db.session.add(user_action_permission)
    db.session.commit()

    return jsonify({'message': 'Permissions saved successfully!'})

