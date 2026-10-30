#!/usr/bin/env python3
"""Dev only: share every photo with Panoramax, so a restored prod dump shows up
in a local federation mirror.

`panoramax_owner_share` is the one eligibility flag that defaults off (moderator
approval and the owner's `panoramax_contributor` default on), so a dump
federates nothing until it is flipped. This disables `panoramax_contributor`
for the two excluded users below, sets the share flag on every photo, then runs
one sequencer pass so the result is visible at once instead of on the next
PANORAMAX_SEQUENCER_INTERVAL_S tick. Photos still have to pass every other gate
in eligibility.py: full1 / panoramax_in intake, a capture time, a detector run
with nothing blurred, and the rest.

On a real deployment this would publish every user's photos without their
consent, so it refuses unless the api container runs with DEBUG_ENDPOINTS on,
the same switch that enables /api/debug/clear-database.

	backend/panoramax/scripts/share_all_photos_dev.py

Afterwards recrawl from the catalog: `stac-harvester harvest <instance>`, then
`stac-harvester refresh-database-views` (the harvester only marks map grid
cells expired; the explorer's map stays empty until the refresh).
"""
import argparse
import subprocess
import sys

TRUTHY = ('true', '1', 'yes')


def run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
	return subprocess.run(args, input=stdin, text=True, capture_output=True)


def psql(sql: str) -> str:
	# The container's own credentials, as the integration tests' pg() helper does.
	result = run('docker', 'exec', '-i', 'hillview_postgres', 'sh', '-c',
		'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -tA', stdin=sql)
	if result.returncode != 0:
		sys.exit(f'share_all_photos_dev: psql failed: {result.stderr.strip()}')
	return result.stdout.strip()


def main() -> int:
	argparse.ArgumentParser(description=(__doc__ or '').split('\n')[0]).parse_args()

	debug = run('docker', 'exec', 'hillview_api', 'printenv', 'DEBUG_ENDPOINTS').stdout.strip()
	if debug.lower() not in TRUTHY:
		sys.exit('share_all_photos_dev: refusing — hillview_api does not run with '
			'DEBUG_ENDPOINTS on, so this may not be a dev stack')

	excluded = psql("""
		WITH excluded AS (
			UPDATE users SET panoramax_contributor = false
			WHERE id IN (
				'3ad50fa1-25b3-4282-814f-7fd6b98af1b4',
				'69418102-e0ce-4679-b297-b0921ac34ecc'
			) AND panoramax_contributor
			RETURNING 1
		)
		SELECT count(*) FROM excluded
	""")
	print(f'disabled Panoramax contributions for {excluded} more users')

	flipped = psql("""
		WITH flipped AS (
			UPDATE photos SET panoramax_owner_share = true
			WHERE NOT panoramax_owner_share
			RETURNING 1
		)
		SELECT count(*) FROM flipped
	""")
	total, shared = psql(
		'SELECT count(*), count(*) FILTER (WHERE panoramax_owner_share) FROM photos'
	).split('|')
	print(f'shared {flipped} more photos; {shared} of {total} are now shared')

	sequencer = run('docker', 'exec', 'hillview_panoramax', 'python', '/app/app/sequencer.py', '--once')
	if sequencer.returncode != 0:
		print('hillview_panoramax is not running; the sequencer picks this up on its next pass '
			'once it is (./compose.sh --profile panoramax up -d panoramax)')
		return 0
	# The pass logs its counters as its last line.
	lines = (sequencer.stdout + sequencer.stderr).strip().splitlines()
	print(lines[-1] if lines else 'sequencer pass done')
	return 0


if __name__ == '__main__':
	sys.exit(main())
