#!/usr/bin/env fish

# View Android logs with filtering for Hillview app
source (dirname (status --current-filename))/../env/android-debug.env

set ADB_PATH "$ANDROID_HOME/platform-tools/adb"

if not test -f $ADB_PATH
    echo "❌ ADB not found at: $ADB_PATH"
    echo "💡 Check ANDROID_HOME in scripts/env/android-base.env"
    exit 1
end

# Check for --no-follow, --once, or -1 flag
set FOLLOW_MODE true
for arg in $argv
    if test "$arg" = "--no-follow" -o "$arg" = "--once" -o "$arg" = "-1"
        set FOLLOW_MODE false
        break
    end
end

if test "$FOLLOW_MODE" = "true"
    echo "📱 Starting Android logs (filtered for Hillview)..."
    echo "🔍 Press Ctrl+C to stop"
    echo ""

    # Filter for Hillview-specific logs (continuous)
    $ADB_PATH logcat | grep -E "(🢄|📍|hillview|hillviedev|RustStdoutStderr|chromium)"
else
    echo "📱 Showing recent Android logs (filtered for Hillview)..."
    echo ""

    # Get recent logs and exit (last 500 lines, filtered)
    $ADB_PATH logcat -d | tail -500 | grep -E "(🢄|📍|hillview|hillviedev|RustStdoutStderr|chromium)"
end
