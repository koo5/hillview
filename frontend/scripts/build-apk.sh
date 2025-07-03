#!/bin/bash

# Build Android APK with support for different architectures
# Usage: ./scripts/build-apk.sh [universal|x86_64|arm64|x86|all]

set -e

# Source common functions
source "$(dirname "$0")/lib/common.sh"

# Default to universal build
BUILD_TYPE="${1:-universal}"

# Function to build APK for specific architecture
build_apk() {
    local arch=$1
    local gradle_flags=""
    
    case "$arch" in
        universal)
            echo -e "${YELLOW}Building universal APK...${NC}"
            gradle_flags=""
            ;;
        x86_64|x86|arm64)
            echo -e "${YELLOW}Building APK for $arch...${NC}"
            gradle_flags="-PtargetArch=$arch"
            ;;
        *)
            echo -e "${RED}Unknown architecture: $arch${NC}"
            return 1
            ;;
    esac
    
    # Run the build
    if [ -z "$gradle_flags" ]; then
        run_in_project_root ./tauri-android.sh android build --apk
    else
        (
            cd "$PROJECT_ROOT/src-tauri/gen/android" &&
            ./gradlew assembleDebug $gradle_flags
        )
    fi
}

# Ensure dependencies
ensure_dependencies || exit 1

# Build based on type
case "$BUILD_TYPE" in
    universal)
        build_apk universal
        ;;
    x86_64|x86|arm64)
        build_apk "$BUILD_TYPE"
        ;;
    all)
        echo -e "${YELLOW}Building APKs for all architectures...${NC}"
        for arch in x86_64 x86 arm64; do
            build_apk "$arch" || {
                echo -e "${RED}Failed to build $arch APK${NC}"
                exit 1
            }
        done
        echo -e "${GREEN}✓ All architecture APKs built successfully${NC}"
        ;;
    *)
        echo -e "${RED}Invalid build type: $BUILD_TYPE${NC}"
        echo "Usage: $0 [universal|x86_64|arm64|x86|all]"
        exit 1
        ;;
esac

# Show APK locations
echo -e "\n${YELLOW}APK locations:${NC}"
find "$PROJECT_ROOT/src-tauri/gen/android/app/build/outputs/apk" -name "*.apk" -type f | while read -r apk; do
    echo -e "  ${GREEN}✓${NC} $(basename "$apk"): $(du -h "$apk" | cut -f1)"
done