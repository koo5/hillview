#!/bin/bash

cd "$(dirname "$(readlink -f -- "$0")")"

if [ $# -eq 0 ]; then
    echo "Running all tests..."
    echo "=================================="
    
    echo "1. Running API unit tests..."
    ../api/app/run_unit_tests.sh
    unit_exit=$?

    echo ""

    echo "2. Running worker unit tests..."
    ../worker/run_unit_tests.sh
    worker_exit=$?

    echo ""

    echo "3. Running integration tests..."
    ./run_integration_tests.sh
    integration_exit=$?


    echo ""
    echo "=================================="
    if [ $integration_exit -eq 0 ] && [ $unit_exit -eq 0 ] && [ $worker_exit -eq 0 ]; then
        echo "✅ All tests passed!"
    else
        echo "❌ Some tests failed!"
        exit 1
    fi
else
    echo "For specific tests, use:"
    echo "  ./run_integration_tests.sh <test_path>  # for integration tests"
    echo "  ../api/app/run_unit_tests.sh <test_path>  # for API unit tests"
    echo "  ../worker/run_unit_tests.sh <test_path>  # for worker unit tests"
    exit 1
fi