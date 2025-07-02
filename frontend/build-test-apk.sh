#!/bin/bash

echo "Building Hillview Android APK for testing..."
echo "This may take 10-20 minutes on first build as it compiles all Rust dependencies."
echo ""

# Build debug APK (faster than release)
./tauri-android.sh android build --apk --debug

if [ $? -eq 0 ]; then
    echo ""
    echo "Build successful!"
    echo "APK location: src-tauri/gen/android/app/build/outputs/apk/universal/debug/app-universal-debug.apk"
    
    # Check if device is connected
    if adb devices | grep -q "device$"; then
        echo ""
        echo "Android device detected. You can now run: bun run test:android"
    else
        echo ""
        echo "No Android device detected. Please connect a device or start an emulator before running tests."
    fi
else
    echo ""
    echo "Build failed. Please check the error messages above."
    exit 1
fi