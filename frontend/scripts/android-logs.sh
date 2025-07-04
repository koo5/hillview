#!/bin/bash


set -e

# Source common functions
source "$(dirname "$0")/lib/common.sh"

adb stdbuf -i0 -o0 -e0 $ADB logcat -v threadtime | stdbuf -i0 -o0 -e0 grep -i --color=auto "hillview\|rust\|Error\|Exception"
