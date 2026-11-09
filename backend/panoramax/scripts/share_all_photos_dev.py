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
	                 federate), or turning it off as well with --unshare. It
	                 rewrites what the owners granted and writes no licence
	                 history, which only a dev mirror may do

`--max-width <w>` limits any of them to photos at most <w> pixels wide (the
original's `photos.width`; photos without a width are left alone).
`--feature <name>` limits them to photos whose LLM analysis lists that feature
(`photos.analysis->'features'`, the names in SCHEMA_FEATURES in
backend/analyzer/analyze_photo.py, e.g. signage); repeat it to match any of
several. Photos the analyzer has not reached are left alone. Then it
runs one sequencer pass so the result is visible at once instead of on the
next PANORAMAX_SEQUENCER_INTERVAL_S tick.

`--sql <file>` (`-` for stdout) writes the same statements, in one
transaction, to a script for psql instead of running anything: for a database
this cannot reach through `docker exec hillview_postgres`, or to read first.
That skips the DEBUG_ENDPOINTS check below, which cannot travel with the file,
and the sequencer pass, so whoever runs the script owns both. Photos still have to pass every other
gate in eligibility.py: full1 / panoramax_in intake, a capture time, a detector
run with nothing blurred, an LLM analysis listing no signage, and the rest.

On a real deployment this would publish every user's photos without their
consent, so it refuses unless the api container runs with DEBUG_ENDPOINTS on,
the same switch that enables /api/debug/clear-database.

	backend/panoramax/scripts/share_all_photos_dev.py all
	backend/panoramax/scripts/share_all_photos_dev.py license full1
	backend/panoramax/scripts/share_all_photos_dev.py none
	backend/panoramax/scripts/share_all_photos_dev.py all --max-width 8192
	backend/panoramax/scripts/share_all_photos_dev.py regrant ccbysa4+osm panoramax_in
	backend/panoramax/scripts/share_all_photos_dev.py none --sql unshare.sql
	backend/panoramax/scripts/share_all_photos_dev.py regrant panoramax_in ccbysa4+osm --unshare --feature signage --sql signage.sql

Afterwards recrawl from the catalog: `stac-harvester harvest <instance>`, then
`stac-harvester refresh-database-views` (the harvester only marks map grid
cells expired; the explorer's map stays empty until the refresh). After a
regrant use `--full-harvest`: a grant change that keeps a photo in its sequence
does not move the sequence's `updated`, so an incremental harvest skips it.
"""
import argparse
import re
import subprocess
import sys
import textwrap

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
	common.add_argument('--feature', action='append', metavar='NAME',
		help='only act on photos whose analysis lists this feature (e.g. signage); repeat for any of several')
	common.add_argument('--sql', metavar='FILE',
		help='write the statements to FILE (- for stdout) instead of running them')
	commands = parser.add_subparsers(dest='command', required=True)
	commands.add_parser('all', parents=[common], help='share every photo')
	commands.add_parser('none', parents=[common], help='unshare every photo')
	commands.add_parser('license', parents=[common], help='share every photo with this intake grant').add_argument(
		'grant', choices=GRANTS)
	regrant = commands.add_parser('regrant', parents=[common], help='rewrite every <from> intake grant to <to>')
	regrant.add_argument('old', metavar='from', choices=GRANTS, help=', '.join(GRANTS))
	regrant.add_argument('new', metavar='to', choices=GRANTS, help=', '.join(GRANTS))
	regrant.add_argument('--unshare', action='store_true', help='also turn Panoramax sharing off for them')
	args = parser.parse_args()
	if args.command == 'regrant' and args.old == args.new:
		parser.error('regrant: <from> and <to> are the same grant')
	for name in args.feature or ():
		if not re.fullmatch(r'[a-z_]+', name):
			parser.error(f'--feature: {name!r} is not a feature name')

	exclude = """
		WITH excluded AS (
			UPDATE users SET panoramax_contributor = false
			WHERE id IN (
				'3ad50fa1-25b3-4282-814f-7fd6b98af1b4',
				'69418102-e0ce-4679-b297-b0921ac34ecc'
			) AND panoramax_contributor
			RETURNING 1
		)
		SELECT count(*) AS users_excluded FROM excluded
	"""
	# Grants come from argparse choices, the width is an int and feature names
	# are checked above, never free text, so they may be inlined.
	def only(table: str = '') -> str:
		col = f'{table}.' if table else ''
		conditions = ''
		if args.max_width is not None:
			conditions += f' AND {col}width <= {args.max_width}'
		if args.feature:
			names = ', '.join(f"'{name}'" for name in args.feature)
			conditions += f" AND {col}analysis->'features' ?| array[{names}]"
		return conditions
	if args.command == 'regrant':
		unshare = ', panoramax_owner_share = false' if args.unshare else ''
		# The old sharing flag comes from a self-join, since RETURNING sees the new one.
		change = f"""
			WITH regranted AS (
				UPDATE photos SET legal_rights = '{args.new}'{unshare}
				FROM photos AS before
				WHERE before.id = photos.id AND photos.legal_rights = '{args.old}'{only('photos')}
				RETURNING before.panoramax_owner_share AS was_shared
			)
			SELECT count(*) AS photos_regranted, count(*) FILTER (WHERE was_shared) AS {"photos_unshared" if args.unshare else "photos_shared"} FROM regranted
		"""
		done = (f'regranted {{}} photos from {args.old} to {args.new}'
			+ (', turning sharing off for the {} shared ones' if args.unshare else ', {} of them shared'))
	else:
		share = args.command != 'none'
		where = f"AND legal_rights = '{args.grant}'" if args.command == 'license' else ''
		change = f"""
			WITH flipped AS (
				UPDATE photos SET panoramax_owner_share = {str(share).lower()}
				WHERE panoramax_owner_share = {str(not share).lower()} {where}{only()}
				RETURNING 1
			)
			SELECT count(*) AS photos_{"shared" if share else "unshared"} FROM flipped
		"""
		done = f'{"shared" if share else "unshared"} {{}} more photos'
	totals = 'SELECT count(*) AS photos, count(*) FILTER (WHERE panoramax_owner_share) AS shared FROM photos'

	if args.sql:
		script = '\n'.join([
			f'-- share_all_photos_dev.py {" ".join(sys.argv[1:])}',
			'-- Dev only: this changes what every owner shares or granted. Afterwards run',
			'-- the sequencer (sequencer.py --once) and harvest, as the script\'s docstring says.',
			'BEGIN;',
			*(textwrap.dedent(sql).strip() + ';' for sql in (exclude, change, totals)),
			'COMMIT;',
			'',
		])
		if args.sql == '-':
			sys.stdout.write(script)
		else:
			with open(args.sql, 'w') as f:
				f.write(script)
			print(f'wrote {args.sql}', file=sys.stderr)
		return 0

	debug = run('docker', 'exec', 'hillview_api', 'printenv', 'DEBUG_ENDPOINTS').stdout.strip()
	if debug.lower() not in TRUTHY:
		sys.exit('share_all_photos_dev: refusing — hillview_api does not run with '
			'DEBUG_ENDPOINTS on, so this may not be a dev stack')

	print(f'disabled Panoramax contributions for {psql(exclude)} more users')
	print(done.format(*psql(change).split('|')))
	total, shared = psql(totals).split('|')
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
