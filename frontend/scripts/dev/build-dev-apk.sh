#!/bin/bash

# Build debug APK (faster than release) with dev mode enabled for tests
VITE_DEV_MODE=true ./scripts/tauri-android.sh android build --apk --debug --config src-tauri/tauri.android-dev.conf.json

if [ $? -eq 0 ]; then
    echo ""
    echo "Build successful!"
    echo "APK location: src-tauri/gen/android/app/build/outputs/apk/universal/debug/app-universal-debug.apk"
else
    echo ""
    echo "Build failed. Please check the error messages above."
    exit 1
fi
