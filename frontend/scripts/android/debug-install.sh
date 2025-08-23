#!/usr/bin/env fish

# Install debug APK to connected Android device/emulator
source (dirname (status --current-filename))/../env/android-base.env

set APK_PATH "src-tauri/gen/android/app/build/outputs/apk/universal/debug/app-universal-debug.apk"
set PACKAGE_ID "io.github.koo5.hillview.dev"
set ADB_PATH "$ANDROID_HOME/platform-tools/adb"

if not test -f $APK_PATH
    echo "❌ Debug APK not found at: $APK_PATH"
    echo "🔨 Run 'bun run android:debug:build' first"
    exit 1
end

if not test -f $ADB_PATH
    echo "❌ ADB not found at: $ADB_PATH"
    echo "💡 Check ANDROID_HOME in scripts/env/android-base.env"
    exit 1
end

echo "📱 Installing debug APK..."
echo "🗑️  Uninstalling previous version..."
$ADB_PATH uninstall $PACKAGE_ID 2>/dev/null; or echo "ℹ️  No previous installation found"

echo "📦 Installing APK..."
if $ADB_PATH install -r $APK_PATH
    echo "✅ Debug APK installed successfully!"
else
    echo "❌ Failed to install debug APK"
    exit 1
end