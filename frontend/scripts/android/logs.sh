#!/usr/bin/env fish

# View Android logs with filtering for Hillview app
source (dirname (status --current-filename))/../env/android-debug.env

set ADB_PATH "$ANDROID_HOME/platform-tools/adb"

if not test -f $ADB_PATH
    echo "❌ ADB not found at: $ADB_PATH"
    echo "💡 Check ANDROID_HOME in scripts/env/android-base.env"
    exit 1
end

echo "📱 Starting Android logs (filtered for Hillview)..."
echo "🔍 Press Ctrl+C to stop"
echo ""

# Filter for Hillview-specific logs
$ADB_PATH logcat | grep -E "(🢄|📍|hillview|RustStdoutStderr)"
