#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")"

./run_unit_tests.sh && ./run_playwright_tests.sh && ./run_appium_tests.sh
