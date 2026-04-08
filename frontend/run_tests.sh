#!/bin/fish

set script_dir (dirname (readlink -m (status --current-filename)))
cd $script_dir


./run_unit_tests.sh;
and ./run_playwright_tests.sh
and begin
	if test "$ANDROID" != "0"; then
		./run_appium_tests.sh;
	end
end

