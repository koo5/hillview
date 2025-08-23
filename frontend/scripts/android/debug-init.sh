#!/usr/bin/env fish

# Initialize Tauri Android project for debug development
source (dirname (status --current-filename))/../env/android-base.env
source (dirname (status --current-filename))/../env/android-debug.env

bun run tauri android init --config src-tauri/tauri.android-dev.conf.json