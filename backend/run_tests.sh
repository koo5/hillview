#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")"

./api/run_tests.sh && ./worker/run_tests.sh && ./tests/run_tests.sh
