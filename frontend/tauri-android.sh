#!/bin/bash

# Load environment variables
export $(grep -v '^#' .env | grep -E '^(JAVA_HOME|CMAKE_MAKE_PROGRAM|ANDROID_NDK_HOME|NDK_HOME|ANDROID_HOME)=' | xargs)

# Run tauri command with all arguments passed to this script
bunx tauri "$@"