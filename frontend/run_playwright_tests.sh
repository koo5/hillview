#!/bin/fish
cd "$(dirname "$(readlink -f -- "$0")")"/tests-playwright
bun install --frozen-lockfile;
and nvm use 22;
and node_modules/.bin/playwright install;
and bun run test --trace on;
and begin
	SCREENSHOT_OUT_DIR=/tmp/docs_screenshots/ bun run screenshots
end

