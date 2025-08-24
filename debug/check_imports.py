import sys
import os

# Add parent directory to path to import your app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_imports():
    """Test if we can import your main app components"""
    print("=== TESTING IMPORTS ===")
    
    try:
        print("1. Testing app import...")
        from app import app
        print("✅ App imported successfully")
        
        print("2. Testing database import...")
        from app import db
        print("✅ Database imported successfully")
        
        print("3. Testing models...")
        # Try to import your models - adjust these imports based on your structure
        try:
            from models import User  # or wherever your User model is
            print("✅ User model imported")
        except ImportError as e:
            print(f"⚠️ User model import failed: {e}")
            # Try alternative import paths
            try:
                from app import User
                print("✅ User model imported from app")
            except ImportError as e2:
                print(f"❌ Could not import User model: {e2}")
        
        print("4. Testing Flask-Login...")
        try:
            from flask_login import current_user
            print("✅ Flask-Login imported")
        except ImportError as e:
            print(f"⚠️ Flask-Login import issue: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Import test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_imports()