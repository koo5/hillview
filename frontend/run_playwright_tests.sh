#!/bin/fish
cd "$(dirname "$(readlink -f -- "$0")")"/tests-playwright
nvm use 22; 
and npx playwright install;
and bun run test --trace on
SCREENSHOT_OUT_DIR=/tmp/docs_screenshots/ and bun run screenshots
