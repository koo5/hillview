#!/usr/bin/env fish
# Incremental by default: sequences whose `updated` moved, tombstones included,
# so unsharing is picked up. Pass --full-harvest to refetch everything after a
# change to the served JSON. A full harvest only sees what the instance serves,
# never tombstones, and when that is nothing it returns before its cleanup yet
# still moves the incremental start past them — so it runs after an incremental
# pass here. If a run skipped tombstones anyway, pass
# --force-incremental-from-date <ISO time before the change>.
#
# --reset deletes the instance from the catalog (collections, items, harvests and
# providers cascade), registers it again and harvests it from scratch: for after
# a restored dump, whose sequence ids the catalog cannot match to anything.
#
# The map grid is rebuilt from scratch every time. The harvester only marks H3
# cells expired; upstream recomputes them from cron (res 12 minutely, 6–11
# hourly, 3–5 daily), and refresh-database-views defaults to the daily part
# alone. Its incremental functions also only upsert cells that still have items,
# so a removed photo stays on the map, and the full res-12 rebuild
# (compute_h3_items_cells_r12) does not truncate first, unlike the 3–11 and
# aggregate ones — hence the TRUNCATE. Cheap at a few thousand items.
set -l db postgresql://username:password@localhost:5439/panoramax
set -l instance hillview-jj
set -l url https://hv.jj.internal/geovisio
set -l harvester .venv/bin/stac-harvester
set -l before_harvest
if contains -- --reset $argv
	set argv (string match -v -- --reset $argv)
	# dev4-2 lacks the cs_CZ locale ssh forwards, and psql's perl wrapper says so at length.
	set before_harvest "and env LC_ALL=C.UTF-8 psql $db -v ON_ERROR_STOP=1 -c \"DELETE FROM instances WHERE name = '$instance'\"
	and $harvester add-instance $instance --db $db --url $url"
else if contains -- --full-harvest $argv
	set before_harvest "and $harvester harvest $instance --db $db"
end
ssh dev4-2 "cd ~/repos/panoramax/server/meta-catalog/0/meta-catalog/harvester
	and set -x REQUESTS_CA_BUNDLE /etc/ssl/certs/ca-certificates.crt
	$before_harvest
	and $harvester harvest $instance --db $db $argv
	and env LC_ALL=C.UTF-8 psql $db -v ON_ERROR_STOP=1 -c \"TRUNCATE h3_items_cells_r12, h3_items_cells_expired, items_aggregate_grid_expired\"
	and $harvester refresh-database-views --db $db --full-grid"
