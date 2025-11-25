#!/usr/bin/env fish

source (dirname (status --current-filename))/../env/android-debug.env
cd (dirname (readlink -m (status --current-filename)))/../..

./scripts/android/cleanup.sh
bun run tauri android init --config src-tauri/tauri.android-dev.conf.json
./scripts/patch-android-gen-files.py

