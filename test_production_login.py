#!/usr/bin/env python3
"""
Test production login and explain database situation
"""

import requests

BASE_URL = "https://national77.com"

def test_login(username, password):
    """Test login on production site"""
    login_url = f"{BASE_URL}/login/"
    
    session = requests.Session()
    
    # Get login page and CSRF token
    response = session.get(login_url)
    
    # Extract CSRF token if available
    csrf_token = None
    if 'csrftoken' in session.cookies:
        csrf_token = session.cookies['csrftoken']
    elif 'csrfmiddlewaretoken' in response.text:
        import re
        match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', response.text)
        if match:
            csrf_token = match.group(1)
    
    # Try to login
    data = {
        'username': username,
        'password': password
    }
    
    if csrf_token:
        data['csrfmiddlewaretoken'] = csrf_token
    
    response = session.post(login_url, data=data, allow_redirects=False)
    
    return response

print("="*60)
print("PRODUCTION LOGIN TEST")
print("="*60)

print("\n⚠️  IMPORTANT:")
print("Your local database and production database are DIFFERENT!")
print("Changing password locally does NOT affect production site.")
print()

# Test different passwords
passwords_to_test = [
    'admin',
    'HackedPassword123!',
    'admin123',
]

print("Testing passwords on production site...")
for pwd in passwords_to_test:
    print(f"\nTesting password: {pwd}")
    response = test_login('admin', pwd)
    
    if response.status_code == 302:
        location = response.headers.get('Location', '')
        if 'dashboard' in location or 'admin' in location:
            print(f"  ✓ SUCCESS! Password '{pwd}' works on production!")
            break
        else:
            print(f"  ✗ Failed - redirected to: {location}")
    elif response.status_code == 200:
        if 'invalid' in response.text.lower() or 'error' in response.text.lower():
            print(f"  ✗ Failed - invalid credentials")
        else:
            print(f"  ? Unexpected response")
    else:
        print(f"  Status: {response.status_code}")

print("\n" + "="*60)
print("SOLUTION:")
print("="*60)
print("""
To change the production admin password, you need to:

1. SSH into your production server
2. Navigate to your Django project directory
3. Run: python manage.py changepassword admin
4. Or use Django shell:
   python manage.py shell
   >>> from django.contrib.auth import get_user_model
   >>> User = get_user_model()
   >>> admin = User.objects.get(username='admin')
   >>> admin.set_password('your_new_password')
   >>> admin.save()

The local database password change only affects your local development environment.
""")
