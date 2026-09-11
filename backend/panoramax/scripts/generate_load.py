"""Bulk-generate a production-shaped photo corpus straight into the database,
for the heavy mode of e2e_federation.sh.

The light mode uploads a dozen photos through the real worker path; this one
skips the worker (50k photos through YOLO + derivative generation would take a
day) and writes rows the way the worker would have left them: completed,
with `sizes`, geometry, capture time and licence set. Everything the
federation service reads is a database row, so this is exactly the input it
sees in production — only the image files behind the `sizes` URLs don't exist,
and neither the sequencer, the API, the harvester nor pystac ever fetch them.

Shape (all knobs are flags; RNG is seeded so a run is reproducible):

- N users with heavy-tailed activity (a few big contributors, a long tail),
  each with a home area (mostly Czechia, some elsewhere in Europe).
- Each user's photos fall into *sessions*: singles (one photo), short bursts,
  medium walks and long walks of hundreds of photos, spread over --years.
  Inside a session consecutive captures are seconds to minutes apart and the
  position random-walks with a drifting heading; between sessions the gap is
  always > 2 × PANORAMAX_SESSION_GAP_HOURS, so the expected number of
  sequences is exact, not statistical.
- ~10% of photos are ineligible in every way the eligibility filter knows
  (ARR licence, private, soft-deleted, failed processing, thumbs-down rated,
  unresolved flag), plus one inactive user and one test user whose photos
  are all ineligible. The expectation written to --summary accounts for all
  of it.

All synthetic rows are tagged by the username prefix; --cleanup removes them
(and their sequences) and a normal run cleans up first, so reruns are exact.

Usage (from anywhere; talks to the DB through `docker exec ... psql`):

    generate_load.py --photos 50000 --users 40 --years 3 --seed 1 --summary out.json
    generate_load.py --cleanup
"""
import argparse
import json
import math
import os
import random
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

NS = uuid.UUID('7d0f2b3a-5c1e-4c6f-9a8e-2f4b6c8d0e1f')  # namespace for deterministic ids

# --- geography -------------------------------------------------------------
CZ_BBOX = (12.1, 48.55, 18.9, 51.05)          # lon_min, lat_min, lon_max, lat_max
EU_BBOX = (-5.0, 42.0, 25.0, 58.0)
CAMERAS = [  # (name pattern, width, height)
	('IMG_{ts}.jpg', 4032, 3024),
	('PXL_{ts}{ms}.jpg', 4000, 3000),
	('DSC_{n:05d}.JPG', 6000, 4000),
	('IMG_{ts}.jpg', 3840, 2160),
	('{ts}.jpg', 1920, 1080),
]
DERIVATIVE_SIZES = [2048, 1024, 640, 320]


@dataclass
class User:
	idx: int
	id: str
	username: str
	email: str
	is_active: bool
	is_test: bool
	weight: float
	home_lon: float
	home_lat: float
	camera: tuple
	quota: int = 0
	photos: list = field(default_factory=list)


@dataclass
class Photo:
	id: str
	owner: User
	session_idx: int
	at: datetime          # naive UTC capture time
	lon: float
	lat: float
	bearing: float | None
	width: int
	height: int
	original_filename: str
	# ineligibility reason, or None when servable
	excluded: str | None = None


# --- random helpers --------------------------------------------------------

def lognormal(rng: random.Random, median: float, sigma: float, lo: float, hi: float) -> float:
	return min(hi, max(lo, rng.lognormvariate(math.log(median), sigma)))


def session_size(rng: random.Random) -> int:
	r = rng.random()
	if r < 0.35:
		return 1                                   # singles
	if r < 0.65:
		return rng.randint(2, 8)                   # short bursts
	if r < 0.90:
		return rng.randint(9, 60)                  # medium walks
	return int(lognormal(rng, 150, 0.6, 61, 600))  # long walks


def uniform_in(rng: random.Random, bbox) -> tuple[float, float]:
	return rng.uniform(bbox[0], bbox[2]), rng.uniform(bbox[1], bbox[3])


def step(lon: float, lat: float, heading_deg: float, metres: float) -> tuple[float, float]:
	h = math.radians(heading_deg)
	dlat = metres * math.cos(h) / 111_320.0
	dlon = metres * math.sin(h) / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
	return lon + dlon, lat + dlat


# --- generation ------------------------------------------------------------

def make_users(rng: random.Random, n: int, prefix: str) -> list[User]:
	users = []
	for i in range(n):
		home = uniform_in(rng, CZ_BBOX if rng.random() < 0.85 else EU_BBOX)
		users.append(User(
			idx=i,
			id=str(uuid.uuid5(NS, f'{prefix}:user:{i}')),
			username=f'{prefix}_u{i:03d}',
			email=f'{prefix}_u{i:03d}@example.invalid',
			is_active=True,
			is_test=False,
			weight=rng.lognormvariate(0.0, 1.1),
			home_lon=home[0], home_lat=home[1],
			camera=rng.choice(CAMERAS),
		))
	if n >= 4:
		users[-1].is_active = False   # everything they have must be excluded
		users[-2].is_test = True
	return users


def plan_session_starts(rng: random.Random, sizes: list[int], span_start: datetime,
		span_end: datetime, min_between: timedelta, mean_gap_s: float) -> list[datetime]:
	"""Start times for sessions of the given sizes: uniformly random in the
	span, then swept forward so consecutive sessions are separated by at least
	min_between plus the earlier session's duration. Falls back to even
	spacing (with jitter) if the random draw doesn't fit."""
	n = len(sizes)
	durations = [timedelta(seconds=(s - 1) * mean_gap_s * 1.5) for s in sizes]
	starts = sorted(span_start + (span_end - span_start) * rng.random() for _ in range(n))
	for i in range(1, n):
		earliest = starts[i - 1] + durations[i - 1] + min_between
		if starts[i] < earliest:
			starts[i] = earliest
	if n and starts[-1] + durations[-1] > span_end:
		total_needed = sum(durations, timedelta()) + min_between * n
		if total_needed > span_end - span_start:
			raise SystemExit(f"sessions don't fit in the span: need {total_needed}, have "
				f"{span_end - span_start}; raise --years or lower --photos/--users ratio")
		slack = (span_end - span_start - total_needed) / n
		t = span_start
		starts = []
		for i in range(n):
			t = t + slack * rng.uniform(0.2, 1.8) * 0.5
			starts.append(t)
			t = t + durations[i] + min_between
	return starts


def generate(rng: random.Random, users: list[User], total_photos: int, years: float,
		gap: timedelta, prefix: str) -> list[Photo]:
	weight_sum = sum(u.weight for u in users)
	for u in users:
		u.quota = max(1, round(total_photos * u.weight / weight_sum))

	now = datetime.now(timezone.utc).replace(tzinfo=None)
	span_end = now - timedelta(days=1)
	span_start = span_end - timedelta(days=365.25 * years)
	min_between = gap * 2 + timedelta(minutes=30)
	within_median_s = 40.0

	photos: list[Photo] = []
	for u in users:
		sizes: list[int] = []
		remaining = u.quota
		while remaining > 0:
			s = min(session_size(rng), remaining)
			sizes.append(s)
			remaining -= s
		starts = plan_session_starts(rng, sizes, span_start, span_end, min_between, within_median_s)
		seq_no = 0
		for si, (size, start) in enumerate(zip(sizes, starts)):
			if rng.random() < 0.9:
				lon = u.home_lon + rng.gauss(0, 0.25)
				lat = u.home_lat + rng.gauss(0, 0.18)
			else:
				lon, lat = uniform_in(rng, EU_BBOX)
			heading = rng.uniform(0, 360)
			at = start
			for k in range(size):
				if k:
					at = at + timedelta(seconds=lognormal(rng, within_median_s, 1.0, 2, 600))
					heading = (heading + rng.gauss(0, 25)) % 360
					lon, lat = step(lon, lat, heading, lognormal(rng, 25, 0.8, 1, 500))
				bearing = None if rng.random() < 0.03 else (heading + rng.gauss(0, 30)) % 360
				seq_no += 1
				name = u.camera[0].format(ts=at.strftime('%Y%m%d_%H%M%S'), ms=f'{rng.randint(0, 999):03d}', n=seq_no)
				pid = str(uuid.uuid5(NS, f'{prefix}:photo:{u.idx}:{si}:{k}'))
				photos.append(Photo(
					id=pid, owner=u, session_idx=si, at=at, lon=lon, lat=lat, bearing=bearing,
					width=u.camera[1], height=u.camera[2], original_filename=name,
				))
				u.photos.append(photos[-1])

	# ineligibility: exclusive draw per photo, ~10% overall
	for p in photos:
		r = rng.random()
		if r < 0.03:
			p.excluded = 'arr'
		elif r < 0.05:
			p.excluded = 'private'
		elif r < 0.07:
			p.excluded = 'deleted'
		elif r < 0.08:
			p.excluded = 'failed'
		elif r < 0.09:
			p.excluded = 'thumbs_down'
		elif r < 0.10:
			p.excluded = 'flagged'
		if not p.owner.is_active:
			p.excluded = p.excluded or 'owner_inactive'
		if p.owner.is_test:
			p.excluded = p.excluded or 'owner_test'
	return photos


def expected_sequences(users: list[User], gap: timedelta) -> dict:
	"""Independent re-derivation of what the sequencer must produce: per
	eligible owner, split capture-ordered eligible photos on gaps > gap."""
	per_user = {}
	singles = 0
	largest = (0, None)
	for u in users:
		elig = sorted((p for p in u.photos if p.excluded is None), key=lambda p: (p.at, p.original_filename, p.id))
		n_seq = 0
		cur = 0
		prev = None
		for p in elig:
			if prev is None or p.at - prev > gap:
				if cur == 1:
					singles += 1
				if cur > largest[0]:
					largest = (cur, u.id)
				n_seq += 1
				cur = 0
			cur += 1
			prev = p.at
		if cur == 1:
			singles += 1
		if cur > largest[0]:
			largest = (cur, u.id)
		per_user[u.id] = {'username': u.username, 'eligible': len(elig), 'sequences': n_seq,
			'is_active': u.is_active, 'is_test': u.is_test, 'total': len(u.photos)}
	return {
		'sequences': sum(v['sequences'] for v in per_user.values()),
		'singles': singles,
		'largest_sequence': {'size': largest[0], 'owner_id': largest[1]},
		'per_user': per_user,
	}


# --- database --------------------------------------------------------------

def esc(v) -> str:
	"""COPY text-format cell."""
	if v is None:
		return r'\N'
	if isinstance(v, bool):
		return 't' if v else 'f'
	if isinstance(v, (int, float)):
		return repr(v) if isinstance(v, float) else str(v)
	if isinstance(v, datetime):
		return v.isoformat(sep=' ')
	if isinstance(v, (dict, list)):
		v = json.dumps(v, separators=(',', ':'))
	return str(v).replace('\\', '\\\\').replace('\t', '\\t').replace('\n', '\\n').replace('\r', '\\r')


def sizes_json(p: Photo) -> dict:
	base = f'https://pics.hillview.cz/opt'
	out = {'full': {'path': f'opt/full/{p.owner.id}/{p.id}.webp', 'width': p.width, 'height': p.height,
		'url': f'{base}/full/{p.owner.id}/{p.id}.webp'}}
	for s in DERIVATIVE_SIZES:
		if s >= max(p.width, p.height):
			continue
		scale = s / max(p.width, p.height)
		out[str(s)] = {'path': f'opt/{s}/{p.owner.id}/{p.id}.webp', 'width': round(p.width * scale),
			'height': round(p.height * scale), 'url': f'{base}/{s}/{p.owner.id}/{p.id}.webp'}
	out['640_llm'] = dict(out.get('640', out['full']), path=f'opt/640_llm/{p.owner.id}/{p.id}.webp',
		url=f'{base}/640_llm/{p.owner.id}/{p.id}.webp')
	return out


class Db:
	def __init__(self, psql_cmd: list[str]):
		self.cmd = psql_cmd

	def run(self, sql: str, stdin: str | None = None) -> str:
		r = subprocess.run(self.cmd + ['-v', 'ON_ERROR_STOP=1', '-tA', '-c', sql],
			input=stdin, capture_output=True, text=True)
		if r.returncode != 0:
			raise SystemExit(f"psql failed:\n{sql[:300]}\n{r.stderr}")
		return r.stdout

	def copy(self, table: str, columns: list[str], rows: list[list]) -> None:
		data = '\n'.join('\t'.join(esc(c) for c in row) for row in rows) + '\n'
		self.run(f"COPY {table} ({', '.join(columns)}) FROM STDIN", stdin=data)


def cleanup(db: Db, prefix: str) -> None:
	db.run(f"""
		BEGIN;
		CREATE TEMP TABLE _load_users AS SELECT id FROM users WHERE username LIKE '{prefix}\\_%';
		CREATE TEMP TABLE _load_photos AS SELECT id FROM photos WHERE owner_id IN (SELECT id FROM _load_users);
		DELETE FROM flagged_photos WHERE photo_source = 'hillview' AND photo_id IN (SELECT id FROM _load_photos);
		DELETE FROM photo_ratings WHERE photo_source = 'hillview' AND photo_id IN (SELECT id FROM _load_photos);
		DELETE FROM photo_ratings WHERE user_id IN (SELECT id FROM _load_users);
		DELETE FROM panoramax.sequences WHERE owner_id IN (SELECT id FROM _load_users);
		DELETE FROM photos WHERE id IN (SELECT id FROM _load_photos);
		DELETE FROM users WHERE id IN (SELECT id FROM _load_users);
		COMMIT;
	""")


def insert(db: Db, rng: random.Random, users: list[User], photos: list[Photo], prefix: str) -> None:
	rater = User(idx=len(users), id=str(uuid.uuid5(NS, f'{prefix}:rater')), username=f'{prefix}_rater',
		email=f'{prefix}_rater@example.invalid', is_active=True, is_test=False, weight=0,
		home_lon=0, home_lat=0, camera=CAMERAS[0])
	now = datetime.now(timezone.utc)
	db.copy('users',
		['id', 'email', 'username', 'is_active', 'is_verified', 'is_test', 'role', 'created_at', 'auto_upload_enabled'],
		[[u.id, u.email, u.username, u.is_active, True, u.is_test, 'USER', now, False] for u in users + [rater]])

	cols = ['id', 'filename', 'original_filename', 'file_md5', 'geometry', 'altitude', 'compass_angle',
		'width', 'height', 'captured_at', 'effective_at', 'uploaded_at', 'record_created_ts',
		'processed_at', 'title', 'description', 'is_public', 'processing_status', 'sizes',
		'legal_rights', 'featured', 'deleted', 'version', 'owner_id']
	rows = []
	ratings = []
	flags = []
	for p in photos:
		uploaded = min(now, p.at.replace(tzinfo=timezone.utc) + timedelta(hours=rng.uniform(1, 24 * 30)))
		failed = p.excluded == 'failed'
		rows.append([
			p.id,
			f"{p.owner.id}_{int(p.at.timestamp() * 1000)}_{rng.getrandbits(32):08x}.jpg",
			p.original_filename,
			f'{rng.getrandbits(128):032x}',
			f'SRID=4326;POINT({p.lon:.7f} {p.lat:.7f})',
			None if rng.random() < 0.3 else round(rng.uniform(150, 1500), 1),
			None if p.bearing is None else round(p.bearing, 2),
			p.width, p.height,
			p.at, p.at, uploaded, uploaded,
			None if failed else uploaded + timedelta(minutes=rng.uniform(1, 30)),
			f'{p.owner.username} session {p.session_idx}' if rng.random() < 0.05 else None,
			'generated by generate_load.py' if rng.random() < 0.02 else None,
			p.excluded != 'private',
			'failed' if failed else 'completed',
			None if failed else sizes_json(p),
			'full1' if p.excluded == 'arr' else 'ccbysa4+osm',
			False,
			p.excluded == 'deleted',
			1,
			p.owner.id,
		])
		if p.excluded == 'thumbs_down':
			ratings.append([str(uuid.uuid4()), rater.id, 'hillview', p.id, 'THUMBS_DOWN', now])
		elif p.excluded == 'flagged':
			flags.append([str(uuid.uuid4()), rater.id, 'hillview', p.id, now, 'load test flag', False])
	db.copy('photos', cols, rows)
	if ratings:
		db.copy('photo_ratings', ['id', 'user_id', 'photo_source', 'photo_id', 'rating', 'created_at'], ratings)
	if flags:
		db.copy('flagged_photos', ['id', 'flagging_user_id', 'photo_source', 'photo_id', 'flagged_at', 'reason', 'resolved'], flags)


def main() -> None:
	ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	ap.add_argument('--photos', type=int, default=50_000)
	ap.add_argument('--users', type=int, default=40)
	ap.add_argument('--years', type=float, default=3.0)
	ap.add_argument('--seed', type=int, default=1)
	ap.add_argument('--gap-hours', type=float, default=float(os.getenv('PANORAMAX_SESSION_GAP_HOURS', '3')))
	ap.add_argument('--prefix', default='pnxload')
	ap.add_argument('--summary', help='write the expected counts here (JSON)')
	ap.add_argument('--cleanup', action='store_true', help='remove all synthetic rows and exit')
	ap.add_argument('--psql', default=None,
		help='psql command (default: docker exec -i hillview_postgres psql -U $POSTGRES_USER -d $POSTGRES_DB)')
	args = ap.parse_args()

	psql = args.psql.split() if args.psql else [
		'docker', 'exec', '-i', 'hillview_postgres', 'psql',
		'-U', os.getenv('POSTGRES_USER', 'hillview'), '-d', os.getenv('POSTGRES_DB', 'hillview')]
	db = Db(psql)

	cleanup(db, args.prefix)
	if args.cleanup:
		print(f"removed all '{args.prefix}_*' users, their photos, ratings, flags and sequences")
		return

	rng = random.Random(args.seed)
	gap = timedelta(hours=args.gap_hours)
	users = make_users(rng, args.users, args.prefix)
	photos = generate(rng, users, args.photos, args.years, gap, args.prefix)
	expect = expected_sequences(users, gap)
	insert(db, rng, users, photos, args.prefix)

	eligible = sum(1 for p in photos if p.excluded is None)
	excluded = {}
	for p in photos:
		if p.excluded:
			excluded[p.excluded] = excluded.get(p.excluded, 0) + 1
	summary = {
		'prefix': args.prefix, 'seed': args.seed, 'gap_hours': args.gap_hours, 'years': args.years,
		'users': len(users), 'photos': len(photos), 'eligible': eligible, 'excluded': excluded,
		'expected_sequences': expect['sequences'], 'expected_singles': expect['singles'],
		'largest_sequence': expect['largest_sequence'],
		'heaviest_user': max((v for v in expect['per_user'].values()), key=lambda v: v['eligible'])['username'],
		'per_user': expect['per_user'],
		'user_ids': [u.id for u in users],
	}
	if args.summary:
		with open(args.summary, 'w') as f:
			json.dump(summary, f, indent=1)
	print(f"generated {len(photos)} photos for {len(users)} users over {args.years} years: "
		f"{eligible} eligible ({excluded}), expecting {expect['sequences']} sequences "
		f"({expect['singles']} singles, largest {expect['largest_sequence']['size']})")


if __name__ == '__main__':
	main()
