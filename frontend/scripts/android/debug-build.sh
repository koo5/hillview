#!/usr/bin/env fish

source (dirname (status --filename))/../env/android-debug.env

cd (dirname (readlink -m (status --current-filename)))/../..

echo "🔨 Building debug APK..."
echo "📱 VITE_DEV_MODE: $VITE_DEV_MODE"
echo "🌐 VITE_BACKEND_ANDROID: $VITE_BACKEND_ANDROID"

# Extra args pass through to `tauri android build`, e.g. `--target x86_64`
# for a fast emulator-only APK (lands in .../apk/x86_64/debug/ instead).
bun run tauri android build --apk --debug --config src-tauri/tauri.android-dev.conf.json $argv

if test $status -eq 0
    echo ""
    echo "✅ Debug APK build successful!"
    echo "📦 APK location: src-tauri/gen/android/app/build/outputs/apk/universal/debug/app-universal-debug.apk"
else
    echo ""
    echo "❌ Debug APK build failed. Check the error messages above."
    exit 1
end