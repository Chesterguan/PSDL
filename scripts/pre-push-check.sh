#!/bin/bash
# Pre-push check script - runs all CI checks locally
# Usage: ./scripts/pre-push-check.sh

set -e  # Exit on first error

echo "========================================"
echo "PSDL Pre-Push Checks"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

check_passed() {
    echo -e "${GREEN}✓ $1 passed${NC}"
}

check_failed() {
    echo -e "${RED}✗ $1 failed${NC}"
    exit 1
}

# 1. Flake8
echo ""
echo "Running flake8..."
if python3 -m flake8 src/ tests/ --max-line-length 100; then
    check_passed "Flake8"
else
    check_failed "Flake8"
fi

# 2. isort
echo ""
echo "Running isort check..."
if python3 -m isort src/ tests/ --check-only --profile black; then
    check_passed "isort"
else
    echo "Fixing isort..."
    python3 -m isort src/ tests/ --profile black
    check_passed "isort (auto-fixed)"
fi

# 3. Black
echo ""
echo "Running black check..."
if python3 -m black src/ tests/ --check --line-length 100; then
    check_passed "Black"
else
    echo "Fixing black..."
    python3 -m black src/ tests/ --line-length 100
    check_passed "Black (auto-fixed)"
fi

# 4. Tests
echo ""
echo "Running tests..."
if python3 -m pytest tests/ -v --tb=short; then
    check_passed "Tests"
else
    check_failed "Tests"
fi

echo ""
echo "========================================"
echo -e "${GREEN}All checks passed! Safe to push.${NC}"
echo "========================================"
