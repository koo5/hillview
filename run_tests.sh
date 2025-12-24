#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")"

./backend/run_tests.sh && ./frontend/run_tests.sh
