#!/usr/bin/env fish

# Run Android tests with proper environment
source (dirname (status --current-filename))/../env/android-debug.env

# Pass all arguments through to wdio
wdio run wdio.conf.ts $argv