#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")"
sudo apt-get install -qqy libimage-exiftool-perl
which node || { echo 'no node' ; exit 1; }
./api/run_unit_tests.sh && ./worker/run_unit_tests.sh && ./tests/run_integration_tests.sh
