#!/usr/bin/env python3
"""
Password Reset Script

This script resets all user passwords in the database to 'welcome1'.
Usage: python changepassword.py
"""

import sys
import os

# Ensure the app's directory is in the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import Flask app and models
try:
    from app import create_app, db
    from app.models import User
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print("Make sure you're running this from the project root directory.")
    sys.exit(1)

def reset_all_passwords():
    """Reset all user passwords to 'welcome1'"""
    try:
        # Create app context
        app = create_app()
        
        with app.app_context():
            # Get all users
            users = User.query.all()
            
            if not users:
                print("No users found in the database.")
                return
            
            count = 0
            
            print("\n=== Password Reset Process Started ===\n")
            
            # Reset each user's password
            for user in users:
                # Store the original hash for comparison
                original_hash = user.password_hash
                
                # Set the new password
                user.set_password("welcome1")
                count += 1
                
                # Print information about the change
                print(f"User #{count}: {user.username} ({user.email})")
                if original_hash:
                    print(f"  Old hash: {original_hash[:15]}...")
                else:
                    print("  Old hash: None")
                print(f"  New hash: {user.password_hash[:15]}...")
                print("  Status: ✓ Password reset")
                print("-" * 50)
            
            # Commit changes to database
            db.session.commit()
            print(f"\n✅ SUCCESS: Reset {count} user passwords to 'welcome1'")
            
            # Print instructions
            print("\nUsers should now be able to log in with the password: welcome1")
            print("Please instruct users to change their passwords after first login.")
    
    except Exception as e:
        print(f"\n❌ ERROR: Failed to reset passwords: {str(e)}")
        # If we're in a session, roll it back
        try:
            db.session.rollback()
        except:
            pass
        return False
    
    return True

if __name__ == "__main__":
    print("Password Reset Utility")
    print("======================")
    
    # Ask for confirmation
    confirm = input("This will reset ALL user passwords to 'welcome1'. Continue? (y/n): ")
    
    if confirm.lower() != 'y':
        print("Operation cancelled.")
        sys.exit(0)
    
    # Run the password reset function
    success = reset_all_passwords()
    
    # Exit with appropriate status code
    sys.exit(0 if success else 1)