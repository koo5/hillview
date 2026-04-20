#!/usr/bin/env bash
# Run the test suite. Assumes ci-start.sh has brought the stack up.
set -euo pipefail
cd "$(dirname "$(readlink -f -- "$0")")/../.."
exec ./run_tests.sh "$@"
