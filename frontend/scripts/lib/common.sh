#!/bin/bash

# Common functions and variables for all validation scripts
# Source this file in other scripts: source "$(dirname "$0")/lib/common.sh"

# Common paths (need this first)
export PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Source .env file if it exists (after PROJECT_ROOT is defined)
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a  # automatically export all variables
    source "$PROJECT_ROOT/.env"
    set +a  # turn off automatic export
fi

# Try to find adb in common Android SDK locations if not in PATH
if ! command -v adb &> /dev/null; then
    # Common Android SDK locations
    ANDROID_SDK_PATHS=(
        "$ANDROID_HOME/platform-tools"
        "$ANDROID_SDK_ROOT/platform-tools"
        "$HOME/Android/Sdk/platform-tools"
        "$HOME/Library/Android/sdk/platform-tools"
        "/usr/local/android-sdk/platform-tools"
        "$HOME/.android/sdk/platform-tools"
    )

    for sdk_path in "${ANDROID_SDK_PATHS[@]}"; do
        if [ -f "$sdk_path/adb" ]; then
            export PATH="$PATH:$sdk_path"
            break
        fi
    done
fi

# Colors for output
export RED='\033[0;31m'
export GREEN='\033[0;32m'
export YELLOW='\033[1;33m'
export BLUE='\033[0;34m'
export NC='\033[0m' # No Color
export SCRIPTS_DIR="$PROJECT_ROOT/scripts"
export APK_PATH="$PROJECT_ROOT/src-tauri/gen/android/app/build/outputs/apk/universal/debug/app-universal-debug.apk"
export APK_PATH_X86_64="$PROJECT_ROOT/src-tauri/gen/android/app/build/outputs/apk/x86_64/debug/app-x86_64-debug.apk"
export PACKAGE_ID="cz.hillview"

# Function to run a command and check its status
run_check() {
    local description=$1
    local command=$2

    echo -e "\n${YELLOW}Running: ${description}${NC}"
    echo -e "Command: ${command}"

    if eval "$command"; then
        echo -e "${GREEN}✓ ${description} passed${NC}"
        return 0
    else
        echo -e "${RED}✗ ${description} failed${NC}"
        return 1
    fi
}

# Function to check and install dependencies
ensure_dependencies() {
    if [ ! -d "$PROJECT_ROOT/node_modules" ]; then
        echo -e "${YELLOW}Installing dependencies...${NC}"
        (cd "$PROJECT_ROOT" && bun install) || {
            echo -e "${RED}Failed to install dependencies${NC}"
            return 1
        }
    fi
    return 0
}

# Function to check if Android device is connected
check_android_device() {
    if ! command -v adb &> /dev/null; then
        echo -e "${RED}Error: ADB not found. Please install Android SDK.${NC}"
        return 1
    fi

    echo -e "\n${YELLOW}Checking for Android devices...${NC}"
    adb devices

    if ! adb devices | grep -q "device$"; then
        echo -e "${RED}Error: No Android device or emulator connected.${NC}"
        echo -e "${YELLOW}Please connect a device or start an emulator.${NC}"
        return 1
    fi

    return 0
}

# Function to uninstall and install APK
install_apk() {
    local apk_path="${1:-$APK_PATH}"

    if [ ! -f "$apk_path" ]; then
        echo -e "${RED}✗ APK not found at: $apk_path${NC}"
        return 1
    fi

    echo -e "${YELLOW}Uninstalling old version...${NC}"
    adb uninstall "$PACKAGE_ID" 2>/dev/null || echo -e "${YELLOW}No previous installation found${NC}"

    echo -e "${YELLOW}Installing APK...${NC}"
    if adb install -r "$apk_path"; then
        echo -e "${GREEN}✓ APK installed successfully${NC}"
        return 0
    else
        echo -e "${RED}✗ Failed to install APK${NC}"
        return 1
    fi
}

# Function to run code quality checks
run_code_quality_checks() {
    echo -e "\n${YELLOW}Running code quality checks...${NC}"

    # Check for console.log statements
    if grep -r "console\.log" "$PROJECT_ROOT/src/" --exclude-dir=node_modules --exclude="*.test.*" > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠ Warning: console.log statements found in source code${NC}"
        grep -r "console\.log" "$PROJECT_ROOT/src/" --exclude-dir=node_modules --exclude="*.test.*" | head -5
        echo -e "${YELLOW}  Consider removing or replacing with proper logging${NC}"
    fi

    # Check for TODO comments
    if grep -r "TODO\|FIXME\|XXX" "$PROJECT_ROOT/src/" --exclude-dir=node_modules > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠ Found TODO/FIXME comments:${NC}"
        grep -r "TODO\|FIXME\|XXX" "$PROJECT_ROOT/src/" --exclude-dir=node_modules | head -5
    fi
}

# Function to print final status
print_final_status() {
    local status=$1
    local success_message=$2
    local failure_message=$3

    echo -e "\n${YELLOW}========================================${NC}"
    if [ "$status" = "true" ]; then
        echo -e "${GREEN}✓ $success_message${NC}"
        return 0
    else
        echo -e "${RED}✗ $failure_message${NC}"
        return 1
    fi
}

# Function to run command in project root
run_in_project_root() {
    (cd "$PROJECT_ROOT" && "$@")
}

# Function to clean app from device/emulator
clean_app_from_device() {
    echo -e "${YELLOW}Cleaning previous installation...${NC}"
    adb uninstall "$PACKAGE_ID" 2>/dev/null || echo -e "${YELLOW}No previous installation found${NC}"
}

# Function to check available storage on device
check_device_storage() {
    local available=$(adb shell df /data | tail -1 | awk '{print $4}')
    if [ -n "$available" ]; then
        # Convert to MB if it's in KB
        if [[ "$available" =~ ^[0-9]+$ ]]; then
            local available_mb=$((available / 1024))
            if [ "$available_mb" -lt 100 ]; then
                echo -e "${YELLOW}⚠ Warning: Low storage on device (${available_mb}MB available)${NC}"
                echo -e "${YELLOW}  Consider running './scripts/clean-android.sh' to free up space${NC}"
                return 1
            fi
        fi
    fi
    return 0
}
