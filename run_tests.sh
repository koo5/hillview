#!/bin/bash
#
# The two suites cannot share a host profile, so this script owns the switching
# rather than leaving it to whoever remembers:
#
#   web      wants an h2 origin. Over plain HTTP/1.1 the ~6-connections-per-origin
#            cap lets SSE streams and lazy chunks starve asset fetches, which
#            surfaces as stalled requests and "module script failed" — worst on
#            WebKit and Firefox.
#   android  cannot use that origin at all: it will not trust Caddy's internal CA.
#
# Which profile each of those means is derived from the hostname — see
# profile_for() in scripts/host_profiles.py.
#
#   ANDROID=0 ./run_tests.sh    web leg only, leaving the host profile alone
#
set -e
cd "$(dirname "$(readlink -f -- "$0")")"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.dev.yml)

echo "=================== web leg ==================="
python3 scripts/set_host.py --for web
# api and worker read WORKER_URL/PICS_URL at container start, so the switch above
# is inert until this.
"${COMPOSE[@]}" up -d

# VITE_* is baked at build time, so a changed origin needs a rebuilt frontend —
# otherwise the app calls the previous profile's host and the failures look like
# a backend outage. --strict turns "stale, or built for another profile" into a
# non-zero exit, which is our signal to rebuild. Conditional on purpose: a run
# that did not change origin pays nothing.
if ! python3 scripts/check_container_freshness.py --strict; then
	echo "--- rebuilding frontend for this profile ---"
	"${COMPOSE[@]}" up -d --build frontend
	python3 scripts/check_container_freshness.py
fi

./backend/run_tests.sh
# ANDROID=0: the android leg runs below, under its own profile.
ANDROID=0 ./frontend/run_tests.sh

if [ "$ANDROID" != "0" ]; then
	echo "=================== android leg ==================="
	python3 scripts/set_host.py --for android
	# Only a restart: Appium drives the APK, which never loads the frontend
	# container, so its bundle is irrelevant here and is deliberately NOT rebuilt.
	# Leaving it on the web origin also means the next web leg needs no rebuild.
	"${COMPOSE[@]}" up -d
	./frontend/run_appium_tests.sh
fi

echo "=================== done ==================="
# The box is left on whichever profile ran last — say so, because it decides what
# a browser opened right now would talk to.
python3 scripts/set_host.py
