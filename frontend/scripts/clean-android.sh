#!/bin/bash

# Script to clean up Android emulator/device storage
# Usage: ./scripts/clean-android.sh [--deep]

set -e  # Exit on any error

# Source common functions
source "$(dirname "$0")/lib/common.sh"

echo -e "${YELLOW}Android Cleanup Utility${NC}"
echo -e "${YELLOW}=======================${NC}\n"

# Check if Android device is available
if ! command -v adb &> /dev/null; then
    echo -e "${RED}Error: ADB not found in PATH.${NC}"
    echo -e "${YELLOW}Please ensure Android SDK is installed and one of the following:${NC}"
    echo -e "  1. Add Android SDK platform-tools to your PATH"
    echo -e "  2. Add the path to your .env file (e.g., export PATH=\$PATH:/path/to/android-sdk/platform-tools)"
    echo -e "  3. Run with explicit path: PATH=\$PATH:/path/to/android-sdk/platform-tools $0"
    exit 1
fi

# Show connected devices
echo -e "${YELLOW}Connected devices:${NC}"
adb devices

if ! adb devices | grep -q "device$"; then
    echo -e "${RED}No Android device or emulator connected.${NC}"
    exit 1
fi

# Function to show storage info
show_storage_info() {
    echo -e "\n${YELLOW}Storage information:${NC}"
    adb shell df -h /data | grep -E "(Filesystem|/data)" || echo "Unable to get storage info"
}

# Function to clean app data
clean_app_data() {
    echo -e "\n${YELLOW}Cleaning Hillview app data...${NC}"
    
    # Clear app data (keeps the app installed but removes all data)
    if adb shell pm clear "$PACKAGE_ID" 2>/dev/null; then
        echo -e "${GREEN}✓ App data cleared${NC}"
    else
        echo -e "${YELLOW}App not installed or already clean${NC}"
    fi
}

# Function to uninstall app
uninstall_app() {
    echo -e "\n${YELLOW}Uninstalling Hillview app...${NC}"
    
    if adb uninstall "$PACKAGE_ID" 2>/dev/null; then
        echo -e "${GREEN}✓ App uninstalled${NC}"
    else
        echo -e "${YELLOW}App not installed${NC}"
    fi
}

# Function to clean build cache on device
clean_build_cache() {
    echo -e "\n${YELLOW}Cleaning build cache...${NC}"
    
    # Clear package manager cache
    adb shell pm trim-caches 999999999999 2>/dev/null || echo "Unable to trim caches (requires root)"
    
    # Clear dalvik cache (requires root)
    if adb shell su -c "rm -rf /data/dalvik-cache/*" 2>/dev/null; then
        echo -e "${GREEN}✓ Dalvik cache cleared${NC}"
    else
        echo -e "${YELLOW}Cannot clear dalvik cache (requires root)${NC}"
    fi
}

# Function to clean test artifacts
clean_test_artifacts() {
    echo -e "\n${YELLOW}Cleaning test artifacts...${NC}"
    
    # Remove screenshots from tests
    adb shell rm -rf /sdcard/Pictures/screenshots 2>/dev/null || true
    adb shell rm -rf /sdcard/Download/test-* 2>/dev/null || true
    
    # Remove any test databases
    adb shell rm -rf "/data/data/$PACKAGE_ID/databases/*" 2>/dev/null || true
    
    echo -e "${GREEN}✓ Test artifacts cleaned${NC}"
}

# Function to show app storage usage
show_app_storage() {
    echo -e "\n${YELLOW}App storage usage:${NC}"
    
    # Get app size
    local app_info=$(adb shell dumpsys package "$PACKAGE_ID" | grep -E "(codePath|dataDir|cacheDir)" 2>/dev/null)
    if [ -n "$app_info" ]; then
        echo "$app_info"
        
        # Try to get actual sizes
        local data_size=$(adb shell du -sh "/data/data/$PACKAGE_ID" 2>/dev/null | cut -f1)
        if [ -n "$data_size" ]; then
            echo -e "Data size: $data_size"
        fi
    else
        echo "App not installed"
    fi
}

# Main cleanup logic
echo -e "\n${BLUE}What would you like to clean?${NC}"
echo "1) Clear app data only (keeps app installed)"
echo "2) Uninstall app completely"
echo "3) Clean test artifacts"
echo "4) Full cleanup (uninstall + test artifacts)"
echo "5) Deep clean (full cleanup + caches) [--deep flag]"
echo "6) Show storage info only"

# Check for --deep flag
if [[ "$*" == *"--deep"* ]]; then
    CHOICE=5
else
    read -p "Enter your choice (1-6): " CHOICE
fi

# Show initial storage info
show_storage_info
show_app_storage

case $CHOICE in
    1)
        clean_app_data
        ;;
    2)
        uninstall_app
        ;;
    3)
        clean_test_artifacts
        ;;
    4)
        uninstall_app
        clean_test_artifacts
        ;;
    5)
        uninstall_app
        clean_test_artifacts
        clean_build_cache
        ;;
    6)
        # Already shown above
        ;;
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac

# Show final storage info
if [ "$CHOICE" != "6" ]; then
    echo -e "\n${YELLOW}Final storage state:${NC}"
    show_storage_info
    show_app_storage
fi

echo -e "\n${GREEN}✓ Cleanup complete!${NC}"