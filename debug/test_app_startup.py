import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_app_context():
    """Test if we can create app context without errors"""
    print("=== TESTING APP CONTEXT ===")
    
    try:
        from app import app, db
        
        print("1. Creating app context...")
        with app.app_context():
            print("✅ App context created")
            
            print("2. Testing database connection...")
            result = db.engine.execute('SELECT 1')
            print("✅ Database query successful")
            
            print("3. Testing database metadata...")
            db.create_all()  # This will show any model errors
            print("✅ Database tables checked/created")
            
        return True
        
    except Exception as e:
        print(f"❌ App context test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_routes_registration():
    """Test if routes are registered without errors"""
    print("\n=== TESTING ROUTE REGISTRATION ===")
    
    try:
        from app import app
        
        print("Registered routes:")
        for rule in app.url_map.iter_rules():
            print(f"  {rule.endpoint}: {rule.rule} {list(rule.methods)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Route registration test failed: {e}")
        return False

if __name__ == "__main__":
    imports_ok = test_imports()
    
    if imports_ok:
        context_ok = test_app_context()
        test_routes_registration()
    else:
        print("❌ Fix import issues first")