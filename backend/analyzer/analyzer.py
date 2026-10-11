#!/usr/bin/env python3
"""
Continuous photo analysis service.

Claims photos that lack a current analysis from PostgreSQL, runs the two LLM
passes (features, distances), and writes the distilled result back.

The work queue is photo_analysis_queue, and a row exists only while a photo is
NOT done under the running ANALYZER_VERSION: never analysed, leased, backing
off, or given up. The sync enqueues every completed photo whose document
carries a different analyzer_version (no key = 0); a complete run writes the
document and deletes the row. So a version bump re-queues everything on the
next sync, and "produced by which version" lives in one place only, the
document.

A row carries last_attempted_version (the ANALYZER_VERSION of the last claim
on it; NULL = queued, never claimed) and next_retry, which only means anything
under that version ('infinity' = given up). Eligible = the version differs, or
next_retry has passed.

A photo is claimed by stamping last_attempted_version and pushing next_retry
CLAIM_LEASE into the future in one short transaction; the LLM calls then run
with NO transaction open (common/database.py kills sessions idle in a
transaction for five minutes, and docs/db-session-cancellation.md says why);
the result lands in a second short transaction.

While it works on a photo the analyzer holds the flock on the photo's JSON
cache file. The kernel drops that lock if the process dies, so a second
analyzer that finds an expired lease can tell an abandoned photo (lock free:
claim it) from a slow one (lock held: extend the lease, move on). This assumes
every analyzer instance shares the datadir on a local filesystem.

What happened to a photo and why is recorded in its JSON file (every attempt,
including unparseable ones), not in the database — the queue only says which
version was tried last and when next.

Readers of the database get an overall assessment and nothing else:
photos.analysis is written only by a complete run, and carries schema_version
(for readers: the shape of the document) and analyzer_version (what produced
it); legacy documents have neither, which reads as 0 and 0. Partial or mixed
results never reach it. Assembling the history of disparate LLM sessions into
one result is this module's job, not the readers'.
"""

import argparse
import asyncio
import json
import os
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from dotenv import load_dotenv

load_dotenv()

# Add backend to path for database imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from sqlalchemy import select, func, or_, update, delete, Integer
from sqlalchemy.dialects.postgresql import insert as pg_insert
from common.database import SessionLocal
from common.models import Photo, PhotoAnalysisQueue

from analyze_photo import (
	run_analysis,
	prepare_image_url,
	DEFAULT_MODEL,
	MAX_TOKENS,
	TEMPERATURE,
	build_schema,
	build_prompt_template,
	generate_focal_length_context,
)

from distill import (
	load_sessions,
	save_sessions,
	find_duplicate,
	count_failed_attempts,
	distill_sessions,
	lock_path_for,
	acquire_file_lock,
	release_file_lock,
)

# Environment variable to control image fetching
FETCH_IMAGES = os.environ.get("ANALYZER_FETCH_IMAGES", "false").lower() == "true"

# Two numbers go into every document the database gets.
#
# SCHEMA_VERSION is for readers: bump it when a key is added, renamed, removed
# or changes meaning. During the re-run that follows, old and new shapes coexist
# in the table and a reader tells them apart per row.
#
# ANALYZER_VERSION is for the queue: bump it for anything that should make the
# analyzer revisit photos — prompt or schema changes, distiller fixes, a model
# upgrade (the model is a CLI argument, so a model change is a bump by
# convention). Every photo whose document carries another analyzer_version is
# re-queued on the next sync, and a queued row attempted under another version
# is eligible regardless of its next_retry — never-analysed photos first,
# newest first. A schema bump always comes with an analyzer bump; the reverse
# is not required. Readers never need this number.
SCHEMA_VERSION = 0
ANALYZER_VERSION = 0

# next_retry meaning "given up under this ANALYZER_VERSION". asyncpg encodes
# exactly this value as Postgres 'infinity'. It reads 'infinity' back as a NAIVE
# datetime.max, so never compare a next_retry read from the DB against this in
# Python; the eligibility check compares in SQL.
GIVEN_UP = datetime.max.replace(tzinfo=timezone.utc)

# How long a claim is honoured before another analyzer may take the photo over
# (if the JSON file lock is free by then; if not, the lease is extended instead).
CLAIM_LEASE = timedelta(minutes=float(os.environ.get("ANALYZER_CLAIM_LEASE_MINUTES", "30")))
RETRY_ERROR = timedelta(hours=1)          # an exception anywhere in the run (network, provider, DB)
RETRY_MISSING_IMAGE = timedelta(days=1)   # no image URL, or the image 404s
RETRY_JUNK_STEP = timedelta(days=1)       # × failed attempts, when the model returns unparseable output
MAX_JUNK_ATTEMPTS = 3                     # failed attempts (same model+prompt) before giving up: GIVEN_UP
ERROR_SLEEP = 60                          # pause after an exception, so a dead provider does not burn through the backlog


@dataclass
class Outcome:
	"""What one run over one photo produced. kind: ok | junk | no_image | image_404 | error."""
	kind: str
	analysis: dict | None = None   # the complete document for photos.analysis; only ever set when kind == 'ok'
	junk_attempts: int = 0         # kind == 'junk': failed attempts for the failing pass, counted from the JSON file


# The keys readers get. Everything else distill produces (description, objects,
# the raw object dicts, image_url, focal length) stays in the sessions file.
DB_ANALYSIS_KEYS = ["closest_object_distance", "farthest_object_distance", "time_of_day", "location_type",
					"scenic_score", "visibility_distance",
					"tallest_building", "features"]


def db_document(distilled: dict) -> dict:
	"""
	The overall assessment written to photos.analysis: the reader-facing keys,
	stamped with the shape they are in (schema_version) and what produced them
	(analyzer_version). Only a complete run produces one — readers never see
	partial results.
	"""
	# Remove metadata fields not needed in DB
	doc = {k: v for k, v in distilled.items() if k in DB_ANALYSIS_KEYS}
	#print(f"    Distilled: {list(db_analysis.keys())}")
	doc["schema_version"] = SCHEMA_VERSION
	doc["analyzer_version"] = ANALYZER_VERSION
	return doc


def next_retry_for(outcome: Outcome, now: datetime) -> datetime | None:
	"""
	The retry policy: when the analyzer may next look at a photo, under the
	current ANALYZER_VERSION, after this outcome. None for a complete run —
	there is no retry, its queue row goes away.
	"""
	if outcome.kind == 'ok':
		return None
	if outcome.kind == 'junk':
		if outcome.junk_attempts >= MAX_JUNK_ATTEMPTS:
			return GIVEN_UP
		return now + RETRY_JUNK_STEP * max(outcome.junk_attempts, 1)
	if outcome.kind in ('no_image', 'image_404'):
		return now + RETRY_MISSING_IMAGE
	if outcome.kind == 'error':
		return now + RETRY_ERROR
	raise ValueError(f"unknown outcome kind {outcome.kind!r}")


def json_path_for(datadir: Path, photo: Photo) -> Path:
	return datadir / f"{photo.file_md5}.json"


def get_image_url(photo: Photo) -> str | None:
	"""Extract image URL from photo sizes (prefer 640_llm, then 640, then 1024, then full)."""
	if not photo.sizes:
		return None
	#print(json.dumps(photo.sizes, indent=2))
	#print(f"    Available 640_llm: {'640_llm' in photo.sizes}, photo.sizes keys: {list(photo.sizes.keys())}, 640_llm: {photo.sizes.get('640_llm')}")
	for size in ["640_llm", "640", "1024", "full"]:
		#print(f"    Checking size: {size}, available: {size in photo.sizes}")
		if size in photo.sizes:
			#print(f"    Using size: {size}, URL: {photo.sizes[size].get('url')}")
			return photo.sizes[size].get("url")
	return None


def check_image(image_url: str) -> bool:
	# Verify URL is accessible with HEAD request
	try:
		response = httpx.head(image_url, timeout=30.0)
		response.raise_for_status()
	except httpx.HTTPStatusError as e:
		if e.response.status_code == 404:
			print(f"    ✗ Image not found (404)")
			return None
		raise
	return True


def get_focal_length(photo: Photo) -> float | None:
	"""Extract FocalLength35efl from photo EXIF data."""
	if not photo.exif_data:
		return None
	# Try common field names
	for field in ["FocalLength35efl"]:
		value = photo.exif_data.get('data', {}).get(field)
		if value is not None:
			# Handle string values like "50 mm" or "50.0"
			if isinstance(value, str):
				import re
				match = re.search(r'([\d.]+)', value)
				if match:
					return float(match.group(1))
			elif isinstance(value, (int, float)):
				return float(value)
	return None


def build_prompt_for_mode(distances: bool, features: bool, focal_length_35mm: float | None,
						  focal_length_hints: bool, distance_table: bool) -> str:
	"""Build the full prompt text for duplicate checking."""

	response_schema = build_schema(distances=distances, features=features)
	prompt_template = build_prompt_template(distances=distances, features=features)

	focal_length_note = ""
	if focal_length_35mm and focal_length_35mm > 50 and (focal_length_hints or distance_table):
		context = generate_focal_length_context(focal_length_35mm, include_hints=focal_length_hints,
												include_table=distance_table)
		if context:
			focal_length_note = f"\n{context}"

	return prompt_template.format(
		schema=json.dumps(response_schema, indent=2),
		focal_length_note=focal_length_note
	)


async def process_photo(
	photo: Photo,
	datadir: Path,
	model: str,
	verbose: bool
) -> Outcome:
	"""
	Process a single photo: features + distances analysis.

	The caller holds the flock on the photo's JSON file (see claim_next), so the
	sessions cache is read and written with lock=False here.
	"""
	print(f"  Photo: {photo.id} ({photo.original_filename})")

	# Get image URL
	image_url = get_image_url(photo)
	if not image_url:
		print(f"    ✗ No image URL available")
		return Outcome('no_image')

	if verbose:
		print(f"    Image URL: {image_url}")

	# Prepare image (fetch if needed)
	try:
		final_image_url, image_hash = prepare_image_url(image_url, FETCH_IMAGES)
	except httpx.HTTPStatusError as e:
		if e.response.status_code == 404:
			print(f"    ✗ Image not found (404)")
			return Outcome('image_404')
		raise

	# Get focal length from EXIF
	focal_length_35mm = get_focal_length(photo)
	if verbose and focal_length_35mm:
		print(f"    Focal length: {focal_length_35mm}mm")

	# Load existing sessions for this photo
	json_path = json_path_for(datadir, photo)
	sessions = load_sessions(json_path, lock=False)

	if verbose:
		print(f"    Existing sessions: {len(sessions)}")

	# Phase 1: Features analysis
	features_prompt = build_prompt_for_mode(
		distances=False, features=True,
		focal_length_35mm=None, focal_length_hints=False, distance_table=False
	)

	features_dup = find_duplicate(
		sessions, model, features_prompt, TEMPERATURE, MAX_TOKENS, verbose=verbose
	)

	image_checked = False
	features_ok = True

	if features_dup:
		print(f"    Features: cached")
	else:
		if not FETCH_IMAGES and not image_checked and not check_image(image_url):
			return Outcome('image_404')
		image_checked = True

		print(f"    Features: analyzing...")
		features_session = run_analysis(
			model=model,
			image_url=image_url,
			final_image_url=final_image_url,
			image_hash=image_hash,
			prompt_text=features_prompt,
			verbose=verbose
		)
		sessions.append(features_session)

		if features_session.get("result", {}).get("parse_error"):
			print(f"    Features: ✗ parse error")
			features_ok = False
		else:
			print(f"    Features: ✓")

	# Phase 2: Distances analysis
	distances_prompt = build_prompt_for_mode(
		distances=True, features=False,
		focal_length_35mm=focal_length_35mm,
		focal_length_hints=True,
		distance_table=True
	)

	distances_dup = find_duplicate(
		sessions, model, distances_prompt, TEMPERATURE, MAX_TOKENS, verbose=verbose
	)

	distances_ok = True

	if distances_dup:
		print(f"    Distances: cached")
	else:
		if not FETCH_IMAGES and not image_checked and not check_image(image_url):
			return Outcome('image_404')
		image_checked = True

		print(f"    Distances: analyzing...")
		distances_session = run_analysis(
			model=model,
			image_url=image_url,
			final_image_url=final_image_url,
			image_hash=image_hash,
			prompt_text=distances_prompt,
			verbose=verbose
		)
		sessions.append(distances_session)

		if distances_session.get("result", {}).get("parse_error"):
			print(f"    Distances: ✗ parse error")
			distances_ok = False
		else:
			print(f"    Distances: ✓")

	# Save sessions
	save_sessions(json_path, sessions, lock=False)

	if not (features_ok and distances_ok):
		# A pass came back unparseable this run. Nothing reaches the database —
		# readers get complete assessments only. The sessions file holds every
		# such attempt for this model+prompt; that count drives the backoff.
		junk_attempts = max(
			count_failed_attempts(sessions, model, prompt, TEMPERATURE, MAX_TOKENS)
			for ok, prompt in ((features_ok, features_prompt), (distances_ok, distances_prompt))
			if not ok
		)
		print(f"    Junk: failed attempt #{junk_attempts} for this model+prompt"
			  + (" — giving up" if junk_attempts >= MAX_JUNK_ATTEMPTS else ""))
		return Outcome('junk', junk_attempts=junk_attempts)

	# Distill results
	distilled = distill_sessions(sessions)
	if not distilled:
		# both passes have a successful session, so this cannot happen; treat it as a bug, not a backoff
		raise RuntimeError(f"distill_sessions produced nothing for {photo.id} although both passes succeeded")

	distilled['focal_length_35mm'] = focal_length_35mm

	if verbose:
		print(f"    Distilled analysis:")
		for k, v in distilled.items():
			print(f"      {k}: {v}")

	return Outcome('ok', analysis=db_document(distilled))


# ---------------------------------------------------------------------------
# Work queue
# ---------------------------------------------------------------------------

def document_analyzer_version():
	"""SQL: the analyzer_version a photo's document carries; legacy documents without the key count as 0."""
	return func.coalesce(Photo.analysis['analyzer_version'].astext.cast(Integer), 0)


def eligible_conditions() -> list:
	"""
	Queued photos the analyzer may look at now: never claimed under this
	ANALYZER_VERSION (unconditional), or claimed and the lease/backoff has
	lapsed. Shared by the claim and the remaining count.
	"""
	return [
		Photo.processing_status == 'completed',
		Photo.deleted == False,
		Photo.file_md5.isnot(None),  # the sessions cache and its lock are keyed by md5
		or_(PhotoAnalysisQueue.last_attempted_version.is_distinct_from(ANALYZER_VERSION),
			PhotoAnalysisQueue.next_retry <= func.now()),
	]


def _joined(stmt):
	return stmt.join(PhotoAnalysisQueue, PhotoAnalysisQueue.photo_id == Photo.id)


async def sync_queue(db) -> int:
	"""
	Enqueue every completed, undeleted photo that is not done under the running
	ANALYZER_VERSION — no document, or a document stamped with another version —
	and has no row yet. FOR UPDATE cannot lock the nullable side of an outer
	join, so a photo must have its row before it can be claimed. Idempotent;
	returns how many rows were added.
	"""
	missing = (
		select(Photo.id)
		.where(Photo.processing_status == 'completed')
		.where(Photo.deleted == False)
		.where(Photo.file_md5.isnot(None))
		.where(or_(Photo.analysis.is_(None), document_analyzer_version().is_distinct_from(ANALYZER_VERSION)))
		.where(~select(PhotoAnalysisQueue.photo_id).where(PhotoAnalysisQueue.photo_id == Photo.id).exists())
	)
	stmt = pg_insert(PhotoAnalysisQueue).from_select(["photo_id"], missing).on_conflict_do_nothing()
	result = await db.execute(stmt)
	await db.commit()
	return result.rowcount


async def count_remaining(db) -> int:
	stmt = _joined(select(func.count()).select_from(Photo)).where(*eligible_conditions())
	return (await db.execute(stmt)).scalar_one()


async def claim_next(datadir: Path, dry_run: bool, deferred: dict[str, datetime]):
	"""
	Claim the next eligible photo: newest first, photos without any analysis
	before photos with a stale one.

	Returns (photo, lock_file) with the photo's JSON file lock HELD — the caller
	must release_file_lock() it after recording the outcome — or None when
	nothing is eligible.

	One short transaction: lock the queue row (SKIP LOCKED keeps concurrent
	analyzers apart), try the file lock, stamp last_attempted_version and push
	next_retry out by CLAIM_LEASE, commit. If the file lock is held by someone
	else, their lease merely lapsed while they are still working: extend it and
	look for another photo.

	`deferred` (photo id -> until) is this process's own skip list: photos it
	must not re-pick for a while even though the queue says they are eligible.
	Used for a locked photo whose row still carries another ANALYZER_VERSION (a
	mismatch is unconditionally eligible, so the extended lease alone would not
	keep it off the top of the queue), and in dry_run, which writes no lease.
	"""
	while True:
		now = datetime.now(timezone.utc)
		for photo_id, until in list(deferred.items()):
			if until <= now:
				del deferred[photo_id]

		async with SessionLocal() as db:
			stmt = (
				_joined(select(Photo, PhotoAnalysisQueue))
				.where(*eligible_conditions())
				.order_by(Photo.analysis.is_(None).desc(), Photo.uploaded_at.desc())
				.limit(1)
				.with_for_update(of=PhotoAnalysisQueue, skip_locked=True)
			)
			if deferred:
				stmt = stmt.where(Photo.id.notin_(list(deferred)))
			row = (await db.execute(stmt)).first()
			if row is None:
				return None
			photo, queued = row

			lock_file = acquire_file_lock(lock_path_for(json_path_for(datadir, photo)), blocking=False)
			if lock_file is None:
				queued.next_retry = now + CLAIM_LEASE
				await db.commit()
				deferred[photo.id] = now + CLAIM_LEASE
				print(f"[{datetime.now().strftime('%H:%M:%S')}] {photo.id}: lease lapsed but its JSON file is locked, "
					  f"another analyzer is still on it — lease extended by {CLAIM_LEASE}")
				continue

			try:
				if dry_run:
					deferred[photo.id] = GIVEN_UP  # i.e. never, for this process
				else:
					queued.last_attempted_version = ANALYZER_VERSION
					queued.next_retry = now + CLAIM_LEASE
					await db.commit()
			except BaseException:
				release_file_lock(lock_file)
				raise
			return photo, lock_file


async def record_outcome(photo: Photo, outcome: Outcome, dry_run: bool) -> None:
	"""
	Second short transaction. A complete run writes the document (if it changed
	— the version stamps make a re-run under a new ANALYZER_VERSION count as a
	change) and deletes the queue row. Anything else leaves the document alone
	and sets next_retry on the row; last_attempted_version was stamped at claim.
	"""
	if outcome.kind == 'ok':
		write_analysis = outcome.analysis != photo.analysis
		if dry_run:
			print(f"    Database: skipped (dry run) — would {'write the document and ' if write_analysis else ''}dequeue")
			return
		async with SessionLocal() as db:
			if write_analysis:
				await db.execute(update(Photo).where(Photo.id == photo.id).values(analysis=outcome.analysis))
			await db.execute(delete(PhotoAnalysisQueue).where(PhotoAnalysisQueue.photo_id == photo.id))
			await db.commit()
		print(f"    Database: {'document updated' if write_analysis else 'document unchanged'}, dequeued")
		return

	next_retry = next_retry_for(outcome, datetime.now(timezone.utc))
	next_retry_text = "given up" if next_retry == GIVEN_UP else next_retry.isoformat()
	if dry_run:
		print(f"    Database: skipped (dry run) — would set next_retry={next_retry_text}")
		return
	async with SessionLocal() as db:
		await db.execute(
			update(PhotoAnalysisQueue).where(PhotoAnalysisQueue.photo_id == photo.id).values(next_retry=next_retry)
		)
		await db.commit()
	print(f"    Database: document unchanged, next_retry={next_retry_text}")


async def main_loop(
	datadir: Path,
	model: str,
	verbose: bool,
	once: bool,
	sleep_interval: int,
	dry_run: bool = False
):
	"""Main processing loop."""
	datadir.mkdir(parents=True, exist_ok=True)

	print(f"Analyzer started")
	print(f"  Model: {model}")
	print(f"  Schema version: {SCHEMA_VERSION}")
	print(f"  Analyzer version: {ANALYZER_VERSION}")
	print(f"  Datadir: {datadir}")
	print(f"  Dry run: {dry_run}")
	print(f"  Fetch images: {FETCH_IMAGES}")
	print(f"  Claim lease: {CLAIM_LEASE}")
	print(f"  API key file: {os.environ.get('OPENROUTER_API_KEY_FILE', 'NOT SET')}")
	print()

	deferred: dict[str, datetime] = {}  # this process's own skip list, see claim_next
	processed = 0

	async with SessionLocal() as db:
		added = await sync_queue(db)
		remaining = await count_remaining(db)
	print(f"[{datetime.now().strftime('%H:%M:%S')}] Queued: {added} new. Photos to analyze: {remaining}")

	while True:
		# # Count remaining unanalyzed photos
		# count_result = await db.execute(
		# 	select(func.count(Photo.id))
		# 	.where(Photo.processing_status == 'completed')
		# 	.where(Photo.deleted == False)
		# 	.where(Photo.analysis.is_(None))
		# )
		# remaining = count_result.scalar()
		# print(f"[{datetime.now().strftime('%H:%M:%S')}] Remaining photos to analyze: {remaining}")

		try:
			claimed = await claim_next(datadir, dry_run, deferred)
		except Exception as e:
			print(f"    Error claiming a photo: {e}")
			traceback.print_exc()
			print(f"sleeping {ERROR_SLEEP}s before continuing...")
			await asyncio.sleep(ERROR_SLEEP)
			continue

		if claimed is None:
			async with SessionLocal() as db:
				added = await sync_queue(db)
			if added:
				continue  # photos finished processing (or went stale) since the last sync; try them now

			if once:
				print("No photos to analyze.")
				break

			print(f"[{datetime.now().strftime('%H:%M:%S')}] No photos to analyze, sleeping {sleep_interval}s...")
			await asyncio.sleep(sleep_interval)
			continue

		photo, lock_file = claimed

		print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing photo...")
		try:
			try:
				outcome = await process_photo(photo, datadir, model, verbose)
			except Exception as e:
				print(f"    Error: {e}")
				traceback.print_exc()
				outcome = Outcome('error')

			try:
				await record_outcome(photo, outcome, dry_run)
			except Exception as e:
				print(f"    Error recording outcome: {e}")
				traceback.print_exc()
				outcome = Outcome('error')  # the lease stays; the photo comes back when it lapses
		finally:
			release_file_lock(lock_file)

		processed += 1
		print(f"{processed} photos processed in this session.")
		print()

		if outcome.kind == 'error':
			print(f"sleeping {ERROR_SLEEP}s before continuing...")
			await asyncio.sleep(ERROR_SLEEP)
		else:
			await asyncio.sleep(1)

		if processed % 20 == 0:
			async with SessionLocal() as db:
				if processed % 100 == 0:
					await sync_queue(db)
				remaining = await count_remaining(db)
			print(f"[{datetime.now().strftime('%H:%M:%S')}] Remaining photos to analyze: {remaining}")


def main():
	parser = argparse.ArgumentParser(description="Continuous photo analysis service")
	parser.add_argument(
		"--datadir",
		type=Path,
		default=Path(os.environ.get("ANALYZER_DATA_DIR", Path(__file__).parent / "data")),
		help="Directory to store analysis JSON files (default: $ANALYZER_DATA_DIR or ./data)"
	)
	parser.add_argument(
		"--model",
		default=DEFAULT_MODEL,
		help=f"Model to use (default: {DEFAULT_MODEL})"
	)
	parser.add_argument(
		"-v", "--verbose",
		action="store_true",
		help="Verbose output"
	)
	parser.add_argument(
		"--once",
		action="store_true",
		help="Process available photos and exit (don't loop)"
	)
	parser.add_argument(
		"--dry-run",
		action="store_true",
		help="Run analysis and save JSON files but don't update the database"
	)
	parser.add_argument(
		"--sleep",
		type=int,
		default=30,
		help="Sleep interval in seconds when no photos (default: 30)"
	)

	args = parser.parse_args()

	# Verify API key file is configured
	if not os.environ.get("OPENROUTER_API_KEY_FILE"):
		print("Error: OPENROUTER_API_KEY_FILE environment variable not set.")
		sys.exit(1)

	asyncio.run(main_loop(
		datadir=args.datadir,
		model=args.model,
		verbose=args.verbose,
		once=args.once,
		sleep_interval=args.sleep,
		dry_run=args.dry_run
	))


if __name__ == "__main__":
	main()
