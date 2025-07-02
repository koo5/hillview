#!/bin/bash

echo "Building Hillview Android APK for x86_64 emulator..."
echo "This will create a smaller APK specifically for x86_64 emulators."
echo ""

# Build debug APK for x86_64 only (for emulator)
./tauri-android.sh android build --apk --debug --split-per-abi

if [ $? -eq 0 ]; then
    echo ""
    echo "Build successful!"
    echo "APK locations:"
    echo "  x86_64: src-tauri/gen/android/app/build/outputs/apk/x86_64/debug/app-x86_64-debug.apk"
    echo "  x86: src-tauri/gen/android/app/build/outputs/apk/x86/debug/app-x86-debug.apk"
    echo "  arm64: src-tauri/gen/android/app/build/outputs/apk/arm64-v8a/debug/app-arm64-v8a-debug.apk"
    
    # Check APK sizes
    echo ""
    echo "APK sizes:"
    ls -lh src-tauri/gen/android/app/build/outputs/apk/*/debug/*.apk 2>/dev/null | grep -E "(x86_64|x86|arm64)" || echo "APKs not found yet"
    
    # Check if device is connected
    if /home/koom/Android/Sdk/platform-tools/adb devices | grep -q "device$"; then
        echo ""
        echo "Android device detected. Update wdio.conf.ts to use the appropriate APK for your device architecture."
    else
        echo ""
        echo "No Android device detected. Please connect a device or start an emulator before running tests."
    fi
else
    echo ""
    echo "Build failed. Please check the error messages above."
    exit 1
fi