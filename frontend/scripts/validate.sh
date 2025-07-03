#!/bin/bash

# Script to validate build and tests before commits/deployments
# Usage: ./scripts/validate.sh [--skip-android]

set -e  # Exit on any error

# Source common functions
source "$(dirname "$0")/lib/common.sh"

echo -e "${YELLOW}Starting validation process...${NC}"

# Track overall status
all_passed=true

# 1. Check dependencies
ensure_dependencies || exit 1

# 2. Run TypeScript type checking
if ! run_in_project_root run_check "TypeScript type checking" "bun run check"; then
    all_passed=false
fi

# 3. Run linting (if configured)
if [ -f "$PROJECT_ROOT/.eslintrc.json" ] || [ -f "$PROJECT_ROOT/.eslintrc.js" ]; then
    if ! run_in_project_root run_check "ESLint" "bun run lint"; then
        all_passed=false
    fi
fi

# 4. Run build
if ! run_in_project_root run_check "Build" "bun run build"; then
    all_passed=false
    echo -e "${RED}Build failed - skipping tests${NC}"
    exit 1
fi

# 5. Run unit tests (if they exist)
if grep -q '"test:unit"' "$PROJECT_ROOT/package.json"; then
    if ! run_in_project_root run_check "Unit tests" "bun run test:unit"; then
        all_passed=false
    fi
else
    echo -e "${YELLOW}No unit tests configured - skipping${NC}"
fi

# 6. Run Android tests (optional - can be skipped with --skip-android)
if [[ "$*" != *"--skip-android"* ]]; then
    echo -e "\n${YELLOW}Checking Android test requirements...${NC}"
    
    if check_android_device; then
        # Build Android APK
        if ! run_in_project_root run_check "Android build" "bun run test:android:build"; then
            all_passed=false
            echo -e "${RED}Android build failed - skipping tests${NC}"
        else
            # Install and test
            if install_apk; then
                if ! run_in_project_root run_check "Android tests" "bun run test:android"; then
                    all_passed=false
                fi
            else
                all_passed=false
            fi
        fi
    else
        echo -e "${YELLOW}⚠ No Android device connected - skipping Android build and tests${NC}"
        echo -e "${YELLOW}  To run Android tests, connect a device or start an emulator${NC}"
        echo -e "${YELLOW}  Or use --skip-android to suppress this warning${NC}"
    fi
else
    echo -e "${YELLOW}Skipping Android build and tests (--skip-android flag used)${NC}"
fi

# 7. Run code quality checks
run_code_quality_checks

# Final status
print_final_status "$all_passed" \
    "All validation checks passed!\n  Your code is ready for commit/deployment" \
    "Some validation checks failed\n  Please fix the issues before proceeding"