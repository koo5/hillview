#!/bin/bash


set -e

# Source common functions
source "$(dirname "$0")/lib/common.sh"

stdbuf -i0 -o0 -e0 adb logcat -v threadtime | stdbuf -i0 -o0 -e0 grep -i --color=auto "hillview\|rust\|Error\|Exception"
