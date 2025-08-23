#!/usr/bin/env fish

# Build release APK
source (dirname (status --current-filename))/../env/android-base.env
source (dirname (status --current-filename))/../env/android-release.env

echo "🔨 Building release APK..."
echo "📱 VITE_DEV_MODE: $VITE_DEV_MODE"
echo "🌐 VITE_BACKEND_ANDROID: $VITE_BACKEND_ANDROID"

bun run tauri android build --apk

if test $status -eq 0
    echo ""
    echo "✅ Release APK build successful!"
    echo "📦 APK locations:"
    find src-tauri/gen/android/app/build/outputs/apk -name "*.apk" -type f | while read apk
        echo "  📱 "(basename $apk)": "(du -h $apk | cut -f1)
    end
else
    echo ""
    echo "❌ Release APK build failed. Check the error messages above."
    exit 1
end