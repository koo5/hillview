#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")"

bun run test:appium
