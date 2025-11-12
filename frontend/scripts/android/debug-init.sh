#!/usr/bin/env fish

source (dirname (status --current-filename))/../env/android-debug.env
rm -rf src-tauri/gen tauri-plugin-hillview/android/build/  .svelte-kit/ build
bun run tauri android init --config src-tauri/tauri.android-dev.conf.json
./scripts/patch-android-gen-files.py

