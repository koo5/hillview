#!/bin/fish
cd "$(dirname "$(readlink -f -- "$0")")"/tests-playwright
npx playwright install
bun run test --trace on
