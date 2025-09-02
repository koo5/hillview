#!/bin/bash

cd "$(dirname "$(readlink -f -- "$0")")"

if [ $# -eq 0 ]; then
    echo "Running all tests..."
    echo "=================================="
    
    echo "1. Running unit tests..."
    ../api/app/run_unit_tests.sh
    unit_exit=$?

    echo ""

    echo "2. Running integration tests..."
    ./run_integration_tests.sh
    integration_exit=$?
    
    
    echo ""
    echo "=================================="
    if [ $integration_exit -eq 0 ] && [ $unit_exit -eq 0 ]; then
        echo "✅ All tests passed!"
    else
        echo "❌ Some tests failed!"
        exit 1
    fi
else
    echo "For specific tests, use:"
    echo "  ./run_integration_tests.sh <test_path>  # for integration tests"
    echo "  ../api/app/run_unit_tests.sh <test_path>  # for unit tests"
    exit 1
fi