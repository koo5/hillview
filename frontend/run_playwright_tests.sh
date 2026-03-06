#!/bin/fish
cd "$(dirname "$(readlink -f -- "$0")")"
npx playwright install
bun run test:playwright
