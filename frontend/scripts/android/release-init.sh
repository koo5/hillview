#!/usr/bin/env fish

# Initialize Tauri Android project for release builds
source (dirname (status --current-filename))/../env/android-release.env

rm -rf src-tauri/gen tauri-plugin-hillview/android/build/

bun run tauri android init