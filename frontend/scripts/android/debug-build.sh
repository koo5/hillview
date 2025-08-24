#!/usr/bin/env fish

# Build debug APK with dev configuration
source (dirname (status --current-filename))/../env/android-debug.env

echo "🔨 Building debug APK..."
echo "📱 VITE_DEV_MODE: $VITE_DEV_MODE"
echo "🌐 VITE_BACKEND_ANDROID: $VITE_BACKEND_ANDROID"

bun run tauri android build --apk --debug --config src-tauri/tauri.android-dev.conf.json

if test $status -eq 0
    echo ""
    echo "✅ Debug APK build successful!"
    echo "📦 APK location: src-tauri/gen/android/app/build/outputs/apk/universal/debug/app-universal-debug.apk"
else
    echo ""
    echo "❌ Debug APK build failed. Check the error messages above."
    exit 1
end