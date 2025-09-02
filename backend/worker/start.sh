#!/usr/bin/env bash

set -x

touch /home/worker/.config/Ultralytics/test

if [ ! -z $DEV_MODE ]; then
	pwd
	watchmedo auto-restart --debounce-interval 1 --interval 3 -d /app/worker -d /app/common --patterns="*.py;*.egg" --recursive  --  ./start2.sh
else
	./start2.sh
fi

echo ".process end ======================================================================= end process ."
