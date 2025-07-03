#!/bin/bash

# Script to validate Android build and run tests
# Usage: ./scripts/validate-android.sh

set -e  # Exit on any error

# Source common functions
source "$(dirname "$0")/lib/common.sh"

echo -e "${YELLOW}Starting Android validation...${NC}"

# Check if Android device is available
check_android_device || exit 1

# Check device storage
check_device_storage

# Track overall status
all_passed=true

# 1. Ensure dependencies
ensure_dependencies || exit 1

# 2. Run web build first (required for Tauri)
if ! run_in_project_root run_check "Web build" "bun run build"; then
    all_passed=false
    echo -e "${RED}Web build failed - cannot proceed with Android build${NC}"
    exit 1
fi

# 3. Build Android APK
if ! run_in_project_root run_check "Android build" "bun run test:android:build"; then
    all_passed=false
    echo -e "${RED}Android build failed${NC}"
    exit 1
fi

# 4. Check if APK was created
if [ -f "$APK_PATH" ]; then
    echo -e "${GREEN}✓ APK found at: $APK_PATH${NC}"
    ls -lh "$APK_PATH"
else
    echo -e "${RED}✗ APK not found at expected location${NC}"
    all_passed=false
    exit 1
fi

# 5. Install APK
install_apk || { all_passed=false; exit 1; }

# 6. Run Android tests
if ! run_in_project_root run_check "Android tests" "bun run test:android"; then
    all_passed=false
fi

# Final status
print_final_status "$all_passed" \
    "Android validation passed!\n  APK is ready and tests are passing" \
    "Android validation failed\n  Please check the errors above"