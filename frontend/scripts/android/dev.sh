#!/usr/bin/env fish

# Start Android development mode (Vite server + dev APK with hot reload)
source (dirname (status --current-filename))/../env/android-debug.env
cd (dirname (readlink -m (status --current-filename)))/../..

# Set TAURI_DEV_HOST for development
set -gx TAURI_DEV_HOST (hostname -I | awk '{print $1}')

echo "🚀 Starting Android development mode..."
echo "📱 VITE_DEV_MODE: $VITE_DEV_MODE"
echo "🌐 VITE_BACKEND_ANDROID: $VITE_BACKEND_ANDROID"
echo "🏠 TAURI_DEV_HOST: $TAURI_DEV_HOST"
echo "🔄 This will start Vite server AND launch dev APK with hot reload"

# Run quick checks (svelte-check + TS unit tests + plugin JVM unit tests) before
# launching the Android dev server. Skip by setting SKIP_QUICK_CHECKS=1.
if test "$SKIP_QUICK_CHECKS" != "1"
    echo "🔎 Running quick checks (set SKIP_QUICK_CHECKS=1 to bypass)..."
    bun run check:quick
    or exit 1
end

bun run tauri android dev --config src-tauri/tauri.android-dev.conf.json # --verbose