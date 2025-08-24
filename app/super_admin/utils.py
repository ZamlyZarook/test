import secrets
import string
from app.models.user import User, Role, Menu, RoleMenuPermission

def generate_company_key(length=16):
    """Generate a random company key."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for i in range(length))

def get_menu_tree():
    """Fetch all menus and build hierarchical structure"""
    all_menus = Menu.query.order_by(Menu.order_index).all()
    menu_dict = {menu.id: {'menu': menu, 'children': []} for menu in all_menus}
    
    root_menus = []
    for menu in all_menus:
        if menu.parent_id is None:
            root_menus.append(menu_dict[menu.id])
        else:
            menu_dict[menu.parent_id]['children'].append(menu_dict[menu.id])
    
    return root_menus