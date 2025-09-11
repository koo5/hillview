#!/usr/bin/env fish

# Run Android tests with proper environment
source (dirname (status --current-filename))/../env/android-debug.env

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
            set wdio_args $wdio_args --spec "./test/specs/"(string sub --start 8 $arg)
        case '*'
            # If it's a .ts file without --spec prefix, assume it's a spec file
            if string match -q '*.ts' $arg
                set restart_per_suite true
                set wdio_args $wdio_args --spec "./test/specs/$arg"
            else
                set wdio_args $wdio_args $arg
            end
    end
end

# Set environment variables
set -gx WDIO_CLEAN_STATE $clean_state
set -gx WDIO_RESTART_PER_SUITE $restart_per_suite

# Run wdio with processed arguments
wdio run wdio.conf.ts $wdio_args