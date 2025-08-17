#!/bin/fish
set -q VITE_BACKEND_ANDROID; or set VITE_BACKEND_ANDROID http://10.0.2.2:8055/api
VITE_DEV_PORT=8218 VITE_BACKEND_ANDROID=$VITE_BACKEND_ANDROID TAURI_DEV_HOST=(hostname -I | awk '{print $1}') JAVA_HOME=/snap/android-studio/current/jbr/  CMAKE_MAKE_PROGRAM=/bin/make ANDROID_NDK_HOME=/home/koom/Android/Sdk/ndk/29.0.13113456/   NDK_HOME=/home/koom/Android/Sdk/ndk/29.0.13113456/  ANDROID_HOME=/home/koom/Android/Sdk/ bun run tauri android dev --verbose --config src-tauri/tauri.android-dev.conf.json
