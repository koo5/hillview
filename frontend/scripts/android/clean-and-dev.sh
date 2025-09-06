#!/usr/bin/env fish

rm -rf build tauri-plugin-hillview/node_modules .svelte-kit node_modules src-tauri/gen tauri-plugin-hillview/android/build
bun i
and ./scripts/android/debug-init.sh; 
and ./scripts/android/dev.sh

