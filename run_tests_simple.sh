#!/bin/bash
# Simple test runner - just run this file

echo "=========================================="
echo "Running Tests"
echo "=========================================="
echo ""

# Delete test database if it exists (non-interactive)
echo "Cleaning up test database..."
dropdb test_broker_portal 2>/dev/null || echo "Test database doesn't exist, will create new one"

echo ""
echo "Running all tests..."
# Use --noinput to automatically answer yes to prompts
python3 manage.py test core --verbosity=1 --noinput

echo ""
echo "Done!"
