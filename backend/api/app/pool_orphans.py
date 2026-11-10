#!/usr/bin/env python3
"""Report files in the local storage pools that no live photo owns.

Walks every files-type pool in FILE_POOLS (cdn pools are not local and are
skipped) and groups what it finds under opt/ by owner and photo, following the
worker's artifact layout (is_photo_artifact_relative_path in
common/security_utils.py) plus the two layouts that preceded it:

	opt/<variant>/<owner_id>/<photo_id>.webp                  size variants
	opt/dzi/<owner_id>/<photo_id>.dzi                         DZI descriptor
	opt/dzi/<owner_id>/<photo_id>_files/<level>/<tile>.webp   DZI tiles
	opt/imu/<owner_id>/<photo_id>.json.gz                     IMU window
	opt/<variant>/<owner_id>/<photo_id>.jpg                   before 2026-02 (pre-WebP)
	opt/<variant>/<photo_id>.<ext>                            before 2025-09 (no owner dir)

A file is LIVE only when its photo is completed and not deleted AND that row
actually points at the file — sizes[*].url, the full size's DZI pyramid, and
every column in photos._PHOTO_ARTIFACT_URL_COLUMNS, mapped to disk exactly as
the delete path maps them. A path with the right shape is not enough. Every
other file under opt/ is reported with the reason it is not live:

	missing         no photo row has that id
	deleted         the row is deleted
	owner_mismatch  the file sits in another owner's directory than the row's
	not_completed   processing_status is not 'completed' (error, ...)
	unreferenced    the photo is live, but its row does not point at this file:
	                a stale copy on another pool, a pre-WebP .jpg a reprocess
	                left behind, a variant no longer produced
	in_flight       NOT counted as orphaned: status 'authorized' within
	                --in-flight-hours, so the worker may be writing it right now

Nothing outside opt/ is judged — terrain/ holds content-addressed depth
buffers SHARED between photos (see delete_photo_files in photos.py), work/ the
worker's in-flight job dirs — it is summarised per top-level directory.

The database is read before the walk and every photo the walk would report is
read again after it, so a photo uploaded, finished or deleted while a long walk
ran is judged on its current row; files that vanished meanwhile are dropped.
No transaction is held across the walk.

Two sanity numbers close the report. "Dangling references" counts files a live
row points at that the walk did not find; "unresolved references" counts live
URLs no pool in FILE_POOLS matches (a dev DB restored from another host, before
set_host.py rewrote its URLs). Either one large means the walk and the database
disagree about where files live — then the 'unreferenced' verdicts are not to
be trusted.

Report only: deletes nothing.

Run inside the api container, the one place every files pool is mounted at its
FILE_POOLS path. The container cannot write backend/data, so take the JSON out
through stdout (-T: no tty, or the JSON gets CRLF line endings):

	./compose.sh exec -T api sh -lc 'cd /app/app && python3 pool_orphans.py -v'
	./compose.sh exec -T api sh -lc 'cd /app/app && python3 pool_orphans.py --json -' > pool_orphans.json
"""
import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Set, Tuple

from common.config import get_file_pools, resolve_pool_for_url
from photos import _PHOTO_ARTIFACT_URL_COLUMNS, _local_path_for_url, photo_artifacts

ORPHAN_REASONS = ("missing", "deleted", "owner_mismatch", "not_completed", "unreferenced")
IN_FLIGHT = "in_flight"
DEFAULT_IN_FLIGHT_HOURS = 24
# Unrecognized paths kept per pool for the report; the counts stay complete.
UNRECOGNIZED_KEEP = 200
DANGLING_KEEP = 50
DB_BATCH = 2000
RECHECK_CHUNK = 1000


# --- layout ---------------------------------------------------------------

@dataclass(frozen=True)
class Artifact:
	photo_id: str
	owner: Optional[str]         # None for the pre-2025-09 flat layout
	tile_dir: Optional[str]      # opt/dzi/<owner>/<photo>_files for a DZI tile


def parse_artifact(rel: str) -> Optional[Artifact]:
	"""Map a path relative to a pool root (under opt/) to its owner and photo.
	None when the path fits none of the layouts."""
	parts = rel.split("/")
	if parts[0] != "opt" or any(not p for p in parts):
		return None
	if len(parts) == 6 and parts[1] == "dzi" and parts[3].endswith("_files") and len(parts[3]) > len("_files"):
		return Artifact(parts[3][:-len("_files")], parts[2], "/".join(parts[:4]))
	if len(parts) == 4:
		return Artifact(_stem(parts[3]), parts[2], None)
	if len(parts) == 3:
		return Artifact(_stem(parts[2]), None, None)
	return None


def _stem(filename: str) -> str:
	# Photo ids are UUIDs, so the first dot ends the id: <id>.webp, <id>.json.gz.
	return filename.split(".", 1)[0]


# --- what the database says -----------------------------------------------

@dataclass(frozen=True)
class PhotoRow:
	id: str
	owner_id: Optional[str]
	deleted: bool
	status: Optional[str]
	authorized_at: Optional[datetime]

	@property
	def live(self) -> bool:
		return self.status == "completed" and not self.deleted


class Index:
	"""Photo rows by id, and every on-disk path a live row points at."""

	def __init__(self):
		self.rows: Dict[str, PhotoRow] = {}
		self.live_files: Dict[str, str] = {}      # abs path -> pool root
		self.live_tile_dirs: Dict[str, str] = {}  # abs tiles dir -> pool root
		self.unresolved_refs = 0
		self.unresolved_examples: List[str] = []
		self.cdn_refs = 0

	def add(self, row) -> None:
		"""Take a row with the photo columns as attributes (an ORM object, a
		Core Row, a SimpleNamespace)."""
		photo = PhotoRow(
			id=str(row.id),
			owner_id=str(row.owner_id) if row.owner_id is not None else None,
			deleted=bool(row.deleted),
			status=row.processing_status,
			authorized_at=row.upload_authorized_at,
		)
		self.rows[photo.id] = photo
		if photo.live:
			self._add_refs(photo_artifacts(row))

	def _add_refs(self, artifacts: Dict[str, Any]) -> None:
		sizes = artifacts.get("sizes")
		for size_info in (sizes.values() if isinstance(sizes, dict) else ()):
			if not isinstance(size_info, dict):
				continue
			self._ref(size_info.get("url"), self.live_files)
			pyramid = size_info.get("pyramid")
			if isinstance(pyramid, dict):
				self._ref(pyramid.get("dzi_url"), self.live_files)
				self._ref(pyramid.get("tiles_url"), self.live_tile_dirs)
		for url in (artifacts.get("urls") or {}).values():
			self._ref(url, self.live_files)

	def _ref(self, url: Optional[str], into: Dict[str, str]) -> None:
		if not url:
			return
		pool = resolve_pool_for_url(url)
		if pool is None:
			self.unresolved_refs += 1
			if len(self.unresolved_examples) < DANGLING_KEEP:
				self.unresolved_examples.append(url)
		elif pool.get("type", "files") != "files":
			self.cdn_refs += 1
		else:
			into[os.path.normpath(_local_path_for_url(url, pool))] = os.path.normpath(pool["path"])


def judge(art: Artifact, row: Optional[PhotoRow], now: datetime, in_flight: timedelta) -> str:
	"""Why a file that no live row points at is not live. Depends only on the
	(photo, owner directory) pair, so every file of one group shares it."""
	if row is None:
		return "missing"
	if row.deleted:
		return "deleted"
	if art.owner is not None and art.owner != row.owner_id:
		return "owner_mismatch"
	if row.status != "completed":
		if row.status == "authorized" and row.authorized_at is not None and now - row.authorized_at < in_flight:
			return IN_FLIGHT
		return "not_completed"
	return "unreferenced"


# --- the walk ---------------------------------------------------------------

@dataclass
class Group:
	photo_id: str
	owner_dir: Optional[str]
	reason: str
	row: Optional[PhotoRow]
	# (pool root, path relative to it) -> [files, bytes]. A DZI tile directory
	# is one entry, its key ending in "/", so a pyramid is not 10^5 lines.
	entries: Dict[Tuple[str, str], List[int]] = field(default_factory=dict)

	def add(self, root: str, key: str, size: int) -> None:
		e = self.entries.setdefault((root, key), [0, 0])
		e[0] += 1
		e[1] += size

	@property
	def files(self) -> int:
		return sum(e[0] for e in self.entries.values())

	@property
	def bytes(self) -> int:
		return sum(e[1] for e in self.entries.values())


@dataclass
class PoolStats:
	url: str
	path: str
	walked: bool = False
	missing_root: bool = False
	files: int = 0
	bytes: int = 0
	live_files: int = 0
	live_bytes: int = 0
	vanished: int = 0
	unrecognized_files: int = 0
	unrecognized_bytes: int = 0
	unrecognized: List[str] = field(default_factory=list)
	outside_opt: Dict[str, List[int]] = field(default_factory=lambda: defaultdict(lambda: [0, 0]))
	errors: List[str] = field(default_factory=list)


def walk_files(root: str, skip_dirs: Set[str], errors: List[str]) -> Iterator[Tuple[str, int]]:
	"""Every non-directory entry below root as (path, size), symlinks not
	followed. Directories in skip_dirs (other pools' roots) are not entered."""
	stack = [root]
	while stack:
		d = stack.pop()
		try:
			it = os.scandir(d)
		except OSError as e:
			errors.append(f"{d}: {e}")
			continue
		with it:
			for entry in it:
				try:
					if entry.is_dir(follow_symlinks=False):
						if entry.path not in skip_dirs:
							stack.append(entry.path)
						continue
					yield entry.path, entry.stat(follow_symlinks=False).st_size
				except OSError as e:
					errors.append(f"{entry.path}: {e}")


class Scanner:
	def __init__(self, index: Index, now: datetime, in_flight: timedelta, progress: Optional[Callable[[str], None]] = None):
		self.index = index
		self.now = now
		self.in_flight = in_flight
		self.progress = progress
		self.pools: List[PoolStats] = []
		self.groups: Dict[Tuple[str, Optional[str]], Group] = {}
		self.seen_files: Set[str] = set()
		self.seen_tile_dirs: Set[str] = set()

	def walk(self, pool: Dict[str, Any], all_roots: Iterable[str]) -> PoolStats:
		root = os.path.normpath(pool["path"])
		stats = PoolStats(url=pool.get("url") or "", path=root)
		self.pools.append(stats)
		if not os.path.isdir(root):
			stats.missing_root = True
			return stats
		stats.walked = True
		skip = {r for r in all_roots if r != root}
		for path, size in walk_files(root, skip, stats.errors):
			stats.files += 1
			stats.bytes += size
			self._observe(stats, root, path[len(root) + 1:], path, size)
			if self.progress and stats.files % 200_000 == 0:
				self.progress(f"  {root}: {stats.files} files…")
		return stats

	def _observe(self, stats: PoolStats, root: str, rel: str, path: str, size: int) -> None:
		top, sep, _ = rel.partition("/")
		if top != "opt" or not sep:
			o = stats.outside_opt[top if sep else "(files at the pool root)"]
			o[0] += 1
			o[1] += size
			return
		art = parse_artifact(rel)
		if art is None:
			stats.unrecognized_files += 1
			stats.unrecognized_bytes += size
			if len(stats.unrecognized) < UNRECOGNIZED_KEEP:
				stats.unrecognized.append(rel)
			return
		if art.tile_dir:
			key, abs_key = art.tile_dir + "/", os.path.join(root, art.tile_dir)
			live = abs_key in self.index.live_tile_dirs
			if live:
				self.seen_tile_dirs.add(abs_key)
		else:
			key, live = rel, path in self.index.live_files
			if live:
				self.seen_files.add(path)
		if live:
			stats.live_files += 1
			stats.live_bytes += size
			return
		gkey = (art.photo_id, art.owner)
		group = self.groups.get(gkey)
		if group is None:
			row = self.index.rows.get(art.photo_id)
			group = self.groups[gkey] = Group(art.photo_id, art.owner, judge(art, row, self.now, self.in_flight), row)
		group.add(root, key, size)

	def dangling(self) -> List[Tuple[str, str]]:
		"""(pool root, path) a live row points at that the walk did not find, on
		the pools that were walked. Approximate: a photo deleted mid-walk shows."""
		walked = {p.path for p in self.pools if p.walked}
		out = [(r, p) for p, r in self.index.live_files.items() if r in walked and p not in self.seen_files]
		out += [(r, p + "/") for p, r in self.index.live_tile_dirs.items() if r in walked and p not in self.seen_tile_dirs]
		return sorted(out)

	def recheck(self, rows: Dict[str, Any]) -> None:
		"""Judge every reported group again on fresh rows (id -> row, absent when
		the photo has no row). Drops files that vanished and files a fresh live
		row now points at; re-derives every reason."""
		fresh = Index()
		for row in rows.values():
			fresh.add(row)
		by_root = {p.path: p for p in self.pools}
		for gkey, group in list(self.groups.items()):
			for (root, key), (n, b) in list(group.entries.items()):
				abs_path = os.path.join(root, key.rstrip("/"))
				stats = by_root[root]
				if not os.path.lexists(abs_path):
					stats.vanished += n
					del group.entries[(root, key)]
				elif abs_path in (fresh.live_tile_dirs if key.endswith("/") else fresh.live_files):
					stats.live_files += n
					stats.live_bytes += b
					del group.entries[(root, key)]
			if not group.entries:
				del self.groups[gkey]
				continue
			group.row = fresh.rows.get(group.photo_id)
			group.reason = judge(Artifact(group.photo_id, group.owner_dir, None), group.row, self.now, self.in_flight)

	def orphans(self) -> List[Group]:
		return [g for g in self.groups.values() if g.reason != IN_FLIGHT]

	def in_flight_groups(self) -> List[Group]:
		return [g for g in self.groups.values() if g.reason == IN_FLIGHT]


def local_pools(only: List[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
	"""(files pools to walk, every other pool), deduplicated by real path so a
	directory registered twice is walked once."""
	walk, other, seen = [], [], set()
	for pool in get_file_pools():
		if pool.get("type", "files") != "files" or not pool.get("path"):
			other.append(pool)
			continue
		if only and pool["path"] not in only and pool.get("url") not in only:
			continue
		real = os.path.realpath(pool["path"])
		if real in seen:
			continue
		seen.add(real)
		walk.append(pool)
	return walk, other


# --- database -------------------------------------------------------------

def _session():
	from common.database import SessionLocal
	if SessionLocal is None:
		raise SystemExit("Database not initialized (ALEMBIC_SYNC_MODE is set?)")
	return SessionLocal()


def _photo_columns():
	from common.models import Photo
	cols = [Photo.id, Photo.owner_id, Photo.deleted, Photo.processing_status,
		Photo.upload_authorized_at, Photo.sizes]
	return Photo, cols + [getattr(Photo, c) for c in _PHOTO_ARTIFACT_URL_COLUMNS]


async def load_index() -> Index:
	from sqlalchemy import select
	_, cols = _photo_columns()
	index = Index()
	async with _session() as session:
		result = await session.stream(select(*cols).execution_options(yield_per=DB_BATCH))
		async for row in result:
			index.add(row)
	return index


async def fetch_rows(ids: Iterable[str]) -> Dict[str, Any]:
	from sqlalchemy import select
	Photo, cols = _photo_columns()
	ids = sorted(ids)
	out = {}
	async with _session() as session:
		for i in range(0, len(ids), RECHECK_CHUNK):
			result = await session.execute(select(*cols).where(Photo.id.in_(ids[i:i + RECHECK_CHUNK])))
			for row in result:
				out[str(row.id)] = row
	return out


async def fetch_usernames(ids: Iterable[str]) -> Dict[str, Optional[str]]:
	from sqlalchemy import select
	from common.models import User
	ids = sorted({i for i in ids if i})
	out = {}
	async with _session() as session:
		for i in range(0, len(ids), RECHECK_CHUNK):
			result = await session.execute(select(User.id, User.username).where(User.id.in_(ids[i:i + RECHECK_CHUNK])))
			for uid, name in result:
				out[str(uid)] = name
	return out


# --- report -----------------------------------------------------------------

def human(n: int) -> str:
	if n < 1024:
		return f"{n} B"
	x = float(n)
	for unit in ("KiB", "MiB", "GiB"):
		x /= 1024
		if x < 1024:
			return f"{x:.1f} {unit}"
	return f"{x / 1024:.1f} TiB"


def owner_of(g: Group) -> str:
	return g.owner_dir or (g.row.owner_id if g.row and g.row.owner_id else "?")


def user_label(uid: str, usernames: Dict[str, Optional[str]]) -> str:
	if uid not in usernames:
		return f"{uid} (no such user)" if uid != "?" else "? (flat layout, no photo row)"
	return f"{uid} ({usernames[uid]})" if usernames[uid] else uid


def group_reason(g: Group) -> str:
	if g.reason == "not_completed" and g.row:
		return f"not_completed:{g.row.status}"
	if g.reason == "owner_mismatch" and g.row:
		return f"owner_mismatch (row owner {g.row.owner_id})"
	return g.reason


def print_report(scanner: Scanner, other_pools: List[Dict[str, Any]], usernames: Dict[str, Optional[str]], verbose: int, out=None) -> None:
	out = out or sys.stdout
	p = lambda *a: print(*a, file=out)
	orphans = scanner.orphans()
	orphan_by_root: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
	flight_by_root: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
	for g in scanner.groups.values():
		target = flight_by_root if g.reason == IN_FLIGHT else orphan_by_root
		for (root, _), (n, b) in g.entries.items():
			target[root][0] += n
			target[root][1] += b

	p("Storage pools (files):")
	for s in scanner.pools:
		if s.missing_root:
			p(f"  ! {s.path}  {s.url}  — pool root does not exist here, NOT walked")
			continue
		o, f = orphan_by_root[s.path], flight_by_root[s.path]
		p(f"  {s.path}  {s.url}  {s.files} files, {human(s.bytes)}")
		p(f"      live {s.live_files} ({human(s.live_bytes)}) · orphaned {o[0]} ({human(o[1])})"
			+ (f" · in flight {f[0]}" if f[0] else "")
			+ (f" · unrecognized under opt/ {s.unrecognized_files} ({human(s.unrecognized_bytes)})" if s.unrecognized_files else "")
			+ (f" · vanished during the walk {s.vanished}" if s.vanished else ""))
		if s.outside_opt:
			p("      outside opt/ (not judged): " + ", ".join(
				f"{k} {n} ({human(b)})" for k, (n, b) in sorted(s.outside_opt.items())))
		for rel in s.unrecognized[:10 if verbose < 2 else UNRECOGNIZED_KEEP]:
			p(f"      ? {rel}")
		for err in s.errors[:10]:
			p(f"      ! {err}")
		if len(s.errors) > 10:
			p(f"      ! … {len(s.errors) - 10} more errors")
	for pool in other_pools:
		p(f"  (skipped {pool.get('type')} pool {pool.get('url')})")

	p("")
	p("Orphans by reason:")
	if not orphans:
		p("  none")
	for reason in ORPHAN_REASONS:
		gs = [g for g in orphans if g.reason == reason]
		if gs:
			p(f"  {reason:<15}{len(gs):>8} photos{sum(g.files for g in gs):>10} files{human(sum(g.bytes for g in gs)):>12}")
	flights = scanner.in_flight_groups()
	if flights:
		p(f"  ({len(flights)} photos in flight, not counted: {sum(g.files for g in flights)} files)")

	if orphans:
		p("")
		p("Orphaned files by user:")
		by_user: Dict[str, List[Group]] = defaultdict(list)
		for g in orphans:
			by_user[owner_of(g)].append(g)
		for uid, gs in sorted(by_user.items(), key=lambda kv: -sum(g.bytes for g in kv[1])):
			counts = defaultdict(int)
			for g in gs:
				counts[g.reason] += 1
			p(f"  {user_label(uid, usernames)}  {len(gs)} photos, {sum(g.files for g in gs)} files, {human(sum(g.bytes for g in gs))}"
				f"  [{', '.join(f'{r} {c}' for r, c in sorted(counts.items()))}]")
			if verbose:
				for g in sorted(gs, key=lambda g: -g.bytes):
					roots = sorted({root for root, _ in g.entries})
					p(f"      {g.photo_id}  {group_reason(g)}  {g.files} files, {human(g.bytes)}  {' '.join(roots)}")
					if verbose >= 2:
						for (root, key), (n, b) in sorted(g.entries.items()):
							p(f"          {os.path.join(root, key)}" + (f"  ({n} tiles, {human(b)})" if key.endswith("/") else f"  {human(b)}"))

	dangling = scanner.dangling()
	idx = scanner.index
	p("")
	p(f"Sanity: {len(dangling)} dangling references (live row → file not found), "
		f"{idx.unresolved_refs} unresolved references (live URL matches no pool), "
		f"{idx.cdn_refs} references on cdn pools (not checked)")
	for root, path in dangling[:10 if verbose < 2 else DANGLING_KEEP]:
		p(f"  dangling: {path}")
	for url in idx.unresolved_examples[:10 if verbose < 2 else DANGLING_KEEP]:
		p(f"  unresolved: {url}")
	if dangling or idx.unresolved_refs:
		p("  ! the database and the pools disagree about where files live: treat 'unreferenced' verdicts with suspicion")


def report_json(scanner: Scanner, other_pools: List[Dict[str, Any]], usernames: Dict[str, Optional[str]]) -> Dict[str, Any]:
	def group_json(g: Group) -> Dict[str, Any]:
		uid = owner_of(g)
		return {
			"photo_id": g.photo_id,
			"owner_dir": g.owner_dir,
			"row_owner_id": g.row.owner_id if g.row else None,
			"username": usernames.get(uid),
			"reason": g.reason,
			"status": g.row.status if g.row else None,
			"deleted": g.row.deleted if g.row else None,
			"files": g.files,
			"bytes": g.bytes,
			"entries": [
				{"pool": root, "path": key, "tile_dir": key.endswith("/"), "files": n, "bytes": b}
				for (root, key), (n, b) in sorted(g.entries.items())
			],
		}
	dangling = scanner.dangling()
	return {
		"generated_at": scanner.now.isoformat(),
		"pools": [{
			"url": s.url, "path": s.path, "walked": s.walked, "missing_root": s.missing_root,
			"files": s.files, "bytes": s.bytes, "live_files": s.live_files, "live_bytes": s.live_bytes,
			"vanished": s.vanished,
			"unrecognized_files": s.unrecognized_files, "unrecognized_bytes": s.unrecognized_bytes,
			"unrecognized_examples": s.unrecognized,
			"outside_opt": {k: {"files": n, "bytes": b} for k, (n, b) in sorted(s.outside_opt.items())},
			"errors": s.errors,
		} for s in scanner.pools],
		"skipped_pools": [{"type": p.get("type"), "url": p.get("url")} for p in other_pools],
		"orphans": [group_json(g) for g in sorted(scanner.orphans(), key=lambda g: (owner_of(g), g.photo_id))],
		"in_flight": [group_json(g) for g in scanner.in_flight_groups()],
		"sanity": {
			"dangling_refs": len(dangling),
			"dangling_examples": [p for _, p in dangling[:DANGLING_KEEP]],
			"unresolved_refs": scanner.index.unresolved_refs,
			"unresolved_examples": scanner.index.unresolved_examples,
			"cdn_refs": scanner.index.cdn_refs,
		},
	}


# --- main -------------------------------------------------------------------

async def run(args) -> int:
	pools, other = local_pools(args.pool or [])
	if not pools:
		print("No files-type pool to walk (check FILE_POOLS / --pool).", file=sys.stderr)
		return 1
	progress = lambda msg: print(msg, file=sys.stderr)
	# Open the JSON target before the walk: on a big pool a bad path would
	# otherwise surface only after the run it was meant to keep.
	json_out = None
	if args.json == "-":
		json_out = sys.stdout
	elif args.json:
		json_out = open(args.json, "w")
	progress("Reading photos…")
	index = await load_index()
	progress(f"  {len(index.rows)} photos, {len(index.live_files)} live files + {len(index.live_tile_dirs)} DZI tile dirs referenced")
	scanner = Scanner(index, datetime.now(timezone.utc), timedelta(hours=args.in_flight_hours), progress)
	all_roots = [os.path.normpath(p["path"]) for p in get_file_pools() if p.get("type", "files") == "files" and p.get("path")]
	for pool in pools:
		progress(f"Walking {pool['path']}…")
		scanner.walk(pool, all_roots)
	progress(f"Re-reading {len(scanner.groups)} reported photos…")
	scanner.recheck(await fetch_rows({pid for pid, _ in scanner.groups}))
	owners = {owner_of(g) for g in scanner.groups.values()}
	owners |= {g.row.owner_id for g in scanner.groups.values() if g.row and g.row.owner_id}
	usernames = await fetch_usernames(owners)

	# With JSON on stdout the readable report moves to stderr, so a
	# redirect captures clean JSON and the terminal still shows the summary.
	print_report(scanner, other, usernames, args.verbose, out=sys.stderr if json_out is sys.stdout else None)
	if json_out is not None:
		json.dump(report_json(scanner, other, usernames), json_out, indent=1)
		json_out.write("\n")
		if json_out is not sys.stdout:
			json_out.close()
			progress(f"Wrote {args.json}")
	return 1 if any(s.missing_root for s in scanner.pools) else 0


def main() -> None:
	parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
	parser.add_argument("-v", "--verbose", action="count", default=0,
		help="-v lists every orphaned photo, -vv every file (DZI tile dirs collapsed)")
	parser.add_argument("--json", metavar="PATH",
		help="also write the full report as JSON; '-' puts it on stdout and the readable report on stderr")
	parser.add_argument("--pool", action="append", metavar="PATH_OR_URL",
		help="walk only this files pool (repeatable); default: all of them")
	parser.add_argument("--in-flight-hours", type=float, default=DEFAULT_IN_FLIGHT_HOURS,
		help=f"an 'authorized' photo this recent is in flight, not orphaned (default {DEFAULT_IN_FLIGHT_HOURS})")
	sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
	main()
