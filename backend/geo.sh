#!/bin/fish
cd ~/repos/koo5/hillview/0/hillview/backend/
. venv/bin/activate.fish
flock -w 0 /tmp/geo ./geo2.sh
