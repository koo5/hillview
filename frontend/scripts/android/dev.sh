#!/usr/bin/env fish

# Start Android development mode (Vite server + dev APK with hot reload)
source (dirname (status --current-filename))/../env/android-base.env
source (dirname (status --current-filename))/../env/android-debug.env

# Set TAURI_DEV_HOST for development
set -gx TAURI_DEV_HOST (hostname -I | awk '{print $1}')

echo "🚀 Starting Android development mode..."
echo "📱 VITE_DEV_MODE: $VITE_DEV_MODE"
echo "🌐 VITE_BACKEND_ANDROID: $VITE_BACKEND_ANDROID"
echo "🏠 TAURI_DEV_HOST: $TAURI_DEV_HOST"
echo "🔄 This will start Vite server AND launch dev APK with hot reload"

bun run tauri android dev --verbose --config src-tauri/tauri.android-dev.conf.json