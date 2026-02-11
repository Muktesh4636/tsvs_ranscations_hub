#!/bin/bash
# Test runner script for comprehensive test suite

echo "=========================================="
echo "Running Comprehensive Test Suite"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo -e "${RED}Error: manage.py not found. Please run from project root.${NC}"
    exit 1
fi

# Detect Python command
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}Error: Python not found. Please install Python 3.${NC}"
    exit 1
fi

# Run all tests (use --keepdb to reuse test database, or remove it first)
echo -e "${YELLOW}Running all tests using $PYTHON_CMD...${NC}"
echo -e "${YELLOW}Note: If test database exists, use --keepdb flag or delete it first${NC}"
$PYTHON_CMD manage.py test core --verbosity=2 --keepdb

# Check exit status
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}=========================================="
    echo "All tests passed successfully!"
    echo "==========================================${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}=========================================="
    echo "Some tests failed. Please check the output above."
    echo "==========================================${NC}"
    exit 1
fi
