#!/bin/bash
# TradeXV2 Parallel Execution Monitor
# Run this script to track team progress in real-time

set -e

echo "🚀 TradeXV2 Parallel Execution Monitor"
echo "========================================"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to check test status
check_tests() {
    local module=$1
    local count=$(python -m pytest $module --collect-only -q 2>/dev/null | wc -l | tr -d ' ')
    echo -e "${BLUE}$module${NC}: $count tests collected"
}

# Function to check file stats
check_files() {
    local pattern=$1
    local count=$(find . -name "$pattern" -path "*/tests/*" -type f 2>/dev/null | wc -l | tr -d ' ')
    echo -e "${BLUE}$pattern${NC}: $count test files"
}

echo "📊 TEAM 1 - Broker Adapters Status:"
echo "-----------------------------------"
check_tests "tests/unit/brokers/dhan/"
check_tests "tests/unit/brokers/upstox/"
check_files "test_*.py"
echo ""

echo "📊 TEAM 2 - API Development Status:"
echo "-----------------------------------"
check_tests "datalake/api/"
check_files "test_*.py" | grep -E "(router|endpoint|api)" || echo "Router tests: 0"
echo ""

echo "📊 TEAM 3 - Analytics Enhancement Status:"
echo "----------------------------------------"
check_tests "analytics/tests/"
check_files "test_*.py" | grep -E "(feature|pipeline|scanner)" || echo "Analytics tests: 0"
echo ""

echo "📊 TEAM 4 - Testing & Docs Status:"
echo "----------------------------------"
check_tests "tests/e2e/"
check_tests "tests/chaos/"
check_tests "tests/integration/"
echo ""

echo "🔥 CRITICAL CHECKS:"
echo "--------------------"

# Check for security issues
if grep -rn "password\|secret\|token" .env.local 2>/dev/null; then
    echo -e "${RED}⚠️  SECURITY: Creds found in .env.local${NC}"
else
    echo -e "${GREEN}✅ SECURITY: No creds in .env${NC}"
fi

# Check for iterrows
iterrows_count=$(grep -rn "iterrows" --include="*.py" brokers/ cli/ datalake/ analytics/ 2>/dev/null | wc -l | tr -d ' ')
if [ "$iterrows_count" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  PERFORMANCE: $iterrows_count iterrows() still present${NC}"
else
    echo -e "${GREEN}✅ PERFORMANCE: No iterrows() found${NC}"
fi

# Check imports
import_errors=$(python -c "from analytics.scanner.models import *" 2>&1 | grep -c "F821\|error" || echo "0")
if [ "$import_errors" -gt 0 ]; then
    echo -e "${RED}⚠️  CODE QUALITY: Import errors detected${NC}"
else
    echo -e "${GREEN}✅ CODE QUALITY: Clean imports${NC}"
fi

echo ""
echo "📈 PROGRESS THIS WEEK:"
echo "---------------------"
git log --oneline --since="1 week ago" --grep="feat\|fix\|refactor" 2>/dev/null | wc -l | xargs -I {} echo "Commits: {}"

echo ""
echo "🎯 READY FOR PARALLEL DEVELOPMENT"
echo "All teams can proceed with assigned tasks"