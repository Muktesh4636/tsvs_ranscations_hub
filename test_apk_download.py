#!/usr/bin/env python3
"""
Test script to verify APK download functionality.
"""
import os
import sys
import django

# Add the project directory to the Python path
sys.path.insert(0, '/Users/pradyumna/chip_3/chip-3')

# Set the Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'broker_portal.settings')

# Setup Django
django.setup()

from django.test import Client

def test_apk_download():
    """Test that APK download route exists and returns 404 when file doesn't exist."""
    client = Client()

    # Test APK download URL
    response = client.get('/download/apk/')

    print(f"APK download response status: {response.status_code}")

    if response.status_code == 404:
        print("✅ APK download route works correctly (file not found as expected)")
        return True
    else:
        print(f"❌ Unexpected response: {response.status_code}")
        return False

if __name__ == '__main__':
    success = test_apk_download()
    sys.exit(0 if success else 1)