#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")"

./api/run_unit_tests.sh && ./worker/run_unit_tests.sh && ./tests/run_integration_tests.sh
