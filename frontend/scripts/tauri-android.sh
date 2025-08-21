#!/bin/bash

# Load Android build environment variables from .env
export $(grep -v '^#' .env | grep -E '^(JAVA_HOME|CMAKE_MAKE_PROGRAM|ANDROID_NDK_HOME|NDK_HOME|ANDROID_HOME)=' | xargs)

# For build commands, also load .env.build for frontend variables
if [[ "$*" == *"build"* ]] && [[ -f .env.build ]]; then
    echo "Loading .env.build for production build..."
    export $(grep -v '^#' .env.build | grep -E '^VITE_' | xargs)
fi

# Run tauri command with all arguments passed to this script
bunx tauri "$@"