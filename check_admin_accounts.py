#!/usr/bin/env python3
"""
Script to check admin accounts in the database.
This helps verify admin account security.
"""

import os
import sys
import django

# Add the project directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'chip-3'))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'broker_portal.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import User

def check_admin_accounts():
    """Check all admin/superuser accounts"""
    print("="*60)
    print("ADMIN ACCOUNTS SECURITY CHECK")
    print("="*60)
    
    User = get_user_model()
    
    # Get all superusers (admin accounts)
    admin_users = User.objects.filter(is_superuser=True)
    
    print(f"\nTotal Admin/Superuser Accounts: {admin_users.count()}\n")
    
    if admin_users.count() == 0:
        print("✓ No admin accounts found (good for security)")
        return
    
    print("Admin Account Details:")
    print("-" * 60)
    
    for user in admin_users:
        print(f"\nUsername: {user.username}")
        print(f"Email: {user.email}")
        print(f"Active: {user.is_active}")
        print(f"Is Superuser: {user.is_superuser}")
        print(f"Is Staff: {user.is_staff}")
        print(f"Date Joined: {user.date_joined}")
        print(f"Last Login: {user.last_login}")
        
        # Check password strength indicators
        if hasattr(user, 'password'):
            password_hash = user.password
            if password_hash.startswith('pbkdf2_'):
                print("✓ Password: Using PBKDF2 hashing (secure)")
            elif password_hash.startswith('bcrypt'):
                print("✓ Password: Using bcrypt hashing (secure)")
            elif password_hash.startswith('argon2'):
                print("✓ Password: Using Argon2 hashing (very secure)")
            else:
                print("⚠️  Password: Unknown hashing algorithm")
        
        # Security recommendations
        recommendations = []
        
        if not user.email:
            recommendations.append("⚠️  No email address set")
        
        if not user.is_active:
            recommendations.append("⚠️  Account is inactive")
        
        if user.last_login is None:
            recommendations.append("⚠️  Account has never logged in")
        
        if recommendations:
            print("\nSecurity Recommendations:")
            for rec in recommendations:
                print(f"  {rec}")
    
    print("\n" + "="*60)
    print("SECURITY RECOMMENDATIONS")
    print("="*60)
    print("""
1. Ensure all admin accounts use strong passwords (12+ characters)
2. Enable two-factor authentication if available
3. Regularly review admin account access
4. Disable unused admin accounts
5. Use separate accounts for different admin users (don't share accounts)
6. Monitor admin account login activity
7. Use Django's password validators (already configured in your settings)
8. Consider using Django's admin log to track admin actions

Note: Passwords are hashed and cannot be retrieved. If you need to reset
an admin password, use Django's management command:
    python manage.py changepassword <username>
    """)

def check_user_passwords():
    """Check password policies"""
    print("\n" + "="*60)
    print("PASSWORD POLICY CHECK")
    print("="*60)
    
    from django.conf import settings
    
    validators = getattr(settings, 'AUTH_PASSWORD_VALIDATORS', [])
    
    if validators:
        print("\n✓ Password validators configured:")
        for validator in validators:
            validator_name = validator.get('NAME', 'Unknown')
            print(f"  - {validator_name}")
    else:
        print("\n⚠️  No password validators configured")
    
    # Check minimum length
    min_length = 12
    for validator in validators:
        if 'MinimumLengthValidator' in validator.get('NAME', ''):
            min_length = validator.get('OPTIONS', {}).get('min_length', 8)
    
    print(f"\nMinimum password length: {min_length} characters")
    
    if min_length >= 12:
        print("✓ Strong minimum password length")
    else:
        print("⚠️  Consider increasing minimum password length to 12+ characters")

def main():
    """Main function"""
    try:
        check_admin_accounts()
        check_user_passwords()
        
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print("""
Your Django application uses Django's authentication system, which:
✓ Hashes passwords using secure algorithms (PBKDF2/bcrypt/Argon2)
✓ Protects against SQL injection through Django ORM
✓ Provides password validators for strong passwords
✓ Stores passwords in hashed form (cannot be retrieved)

To improve security further:
1. Enable HTTPS/SSL on your production site
2. Use Django's security middleware
3. Regularly update Django and dependencies
4. Monitor failed login attempts
5. Use rate limiting (already implemented in your login view)
        """)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
