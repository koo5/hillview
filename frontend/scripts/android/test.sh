#!/usr/bin/env fish

# Run Android tests with proper environment

source (dirname (status --current-filename))/../env/android-debug.env
source (dirname (status --current-filename))/../env/android-base.env

set -gx APPIUM_HOST 127.0.0.1
set -gx APPIUM_PORT 4723

# Parse arguments and set environment variables
set -l clean_state true  # Default to clean state for proper test isolation
set -l restart_per_suite false
set -l wdio_args

for arg in $argv
    switch $arg
        case '--clean'
            set clean_state true  # Explicit clean (already default)
        case '--fast'
            set clean_state false  # Opt into fast mode
        case '--spec'
            set restart_per_suite true
        case '--spec=*'
            set restart_per_suite true
            set wdio_args $wdio_args --spec "./specs/"(string sub --start 8 $arg)
        case '*'
            # If it's a .ts file without --spec prefix, assume it's a spec file
            if string match -q -- '*.ts' $arg
                set restart_per_suite true
                set wdio_args $wdio_args --spec "./specs/$arg"
            else
                set wdio_args $wdio_args $arg
            end
    end
end

# Set environment variables
set -gx WDIO_CLEAN_STATE $clean_state
set -gx WDIO_RESTART_PER_SUITE $restart_per_suite

# Ensure correct Node.js version
source (dirname (status --current-filename))/ensure-node-version.sh

# Add Android platform-tools to PATH if not already there
if not string match -q -- '*platform-tools*' $PATH
    set -gx PATH $PATH $ANDROID_HOME/platform-tools
end

# Acquire shared test lock, then run wdio from tests-appium directory.
# Lock is held before Appium starts, preventing port conflicts
# and backend state races with Playwright/pytest.
set -l tests_dir (dirname (status --current-filename))/../../tests-appium
cd $tests_dir
node_modules/.bin/tsx helpers/lockAndRun.ts node_modules/.bin/wdio run wdio.conf.ts $wdio_args
