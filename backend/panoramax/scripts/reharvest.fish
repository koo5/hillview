#!/usr/bin/env fish
# Pass --full-harvest to refetch everything.
set -l db postgresql://username:password@localhost:5439/panoramax
ssh dev4-2 "cd ~/repos/panoramax/server/meta-catalog/0/meta-catalog/harvester
	and set -x REQUESTS_CA_BUNDLE /etc/ssl/certs/ca-certificates.crt
	and .venv/bin/stac-harvester harvest hillview-jj --db $db $argv
	and .venv/bin/stac-harvester refresh-database-views --db $db"
