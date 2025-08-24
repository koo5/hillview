#!/usr/bin/env fish

# Initialize Tauri Android project for release builds
source (dirname (status --current-filename))/../env/android-release.env

bun run tauri android init