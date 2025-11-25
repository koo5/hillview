#!/bin/env bash
rm -rf src-tauri/gen tauri-plugin-hillview/android/build/  .svelte-kit/ build node_modules
bun i --frozen-lockfile
