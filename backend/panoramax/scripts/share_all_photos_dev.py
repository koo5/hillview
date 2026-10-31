#!/usr/bin/env python3
"""Dev only: set Panoramax sharing and intake grants in bulk, for a local federation mirror.

`panoramax_owner_share` is the one eligibility flag that defaults off (moderator
approval and the owner's `panoramax_contributor` default on), so a restored
prod dump federates nothing until it is flipped. Every subcommand first disables
`panoramax_contributor` for the two excluded users below, then:

	all              share every photo
	none             unshare every photo
	license <grant>  share every photo with that intake grant (legal_rights),
	                 leaving the others as they are
	regrant <from> <to>
	                 rewrite every <from> intake grant to <to>, leaving sharing
	                 as it is (e.g. ccbysa4+osm panoramax_in, so CC photos can
	                 federate). It rewrites what the owners granted and writes
	                 no licence history, which only a dev mirror may do

`--max-width <w>` limits any of them to photos at most <w> pixels wide (the
original's `photos.width`; photos without a width are left alone). Then it
runs one sequencer pass so the result is visible at once instead of on the
next PANORAMAX_SEQUENCER_INTERVAL_S tick. Photos still have to pass every other
gate in eligibility.py: full1 / panoramax_in intake, a capture time, a detector
run with nothing blurred, and the rest.

On a real deployment this would publish every user's photos without their
consent, so it refuses unless the api container runs with DEBUG_ENDPOINTS on,
the same switch that enables /api/debug/clear-database.

	backend/panoramax/scripts/share_all_photos_dev.py all
	backend/panoramax/scripts/share_all_photos_dev.py license full1
	backend/panoramax/scripts/share_all_photos_dev.py none
	backend/panoramax/scripts/share_all_photos_dev.py all --max-width 8192
	backend/panoramax/scripts/share_all_photos_dev.py regrant ccbysa4+osm panoramax_in

Afterwards recrawl from the catalog: `stac-harvester harvest <instance>`, then
`stac-harvester refresh-database-views` (the harvester only marks map grid
cells expired; the explorer's map stays empty until the refresh). After a
regrant use `--full-harvest`: a grant change that keeps a photo in its sequence
does not move the sequence's `updated`, so an incremental harvest skips it.
"""
import argparse
import subprocess
import sys

TRUTHY = ('true', '1', 'yes')
# The intake grants, as LEGAL_RIGHTS_TO_LICENSE in api/app/hillview_routes.py
# knows them. Only full1 and panoramax_in can federate.
GRANTS = ('full1', 'ccbysa4+osm', 'panoramax_in')


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
	parser = argparse.ArgumentParser(description=(__doc__ or '').split('\n')[0])
	common = argparse.ArgumentParser(add_help=False)
	common.add_argument('--max-width', type=int, metavar='W',
		help='only act on photos at most W pixels wide')
	commands = parser.add_subparsers(dest='command', required=True)
	commands.add_parser('all', parents=[common], help='share every photo')
	commands.add_parser('none', parents=[common], help='unshare every photo')
	commands.add_parser('license', parents=[common], help='share every photo with this intake grant').add_argument(
		'grant', choices=GRANTS)
	regrant = commands.add_parser('regrant', parents=[common], help='rewrite every <from> intake grant to <to>')
	regrant.add_argument('old', metavar='from', choices=GRANTS, help=', '.join(GRANTS))
	regrant.add_argument('new', metavar='to', choices=GRANTS, help=', '.join(GRANTS))
	args = parser.parse_args()
	if args.command == 'regrant' and args.old == args.new:
		parser.error('regrant: <from> and <to> are the same grant')

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

	# Grants come from argparse choices and the width is an int, never free
	# text, so they may be inlined.
	width = f'AND width <= {args.max_width}' if args.max_width is not None else ''
	if args.command == 'regrant':
		regranted = psql(f"""
			WITH regranted AS (
				UPDATE photos SET legal_rights = '{args.new}'
				WHERE legal_rights = '{args.old}' {width}
				RETURNING 1
			)
			SELECT count(*) FROM regranted
		""")
		print(f'regranted {regranted} photos from {args.old} to {args.new}')
	else:
		share = args.command != 'none'
		where = f"AND legal_rights = '{args.grant}'" if args.command == 'license' else ''
		flipped = psql(f"""
			WITH flipped AS (
				UPDATE photos SET panoramax_owner_share = {str(share).lower()}
				WHERE panoramax_owner_share = {str(not share).lower()} {where} {width}
				RETURNING 1
			)
			SELECT count(*) FROM flipped
		""")
		print(f'{"shared" if share else "unshared"} {flipped} more photos')
	total, shared = psql(
		'SELECT count(*), count(*) FILTER (WHERE panoramax_owner_share) FROM photos'
	).split('|')
	print(f'{shared} of {total} photos are shared')

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
