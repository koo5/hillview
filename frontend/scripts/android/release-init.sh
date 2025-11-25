#!/usr/bin/env fish

source (dirname (status --current-filename))/../env/android-release.env
cd (dirname (readlink -m (status --current-filename)))/../..

./scripts/android/cleanup.sh
bun run tauri android init
./scripts/patch-android-gen-files.py
