#!/bin/fish
cd "$(dirname "$(readlink -f -- "$0")")"

./run_unit_tests.sh;
and ./run_playwright_tests.sh
and begin
	if test "$ANDROID" != "0"; then
		./run_appium_tests.sh;
	end
end

