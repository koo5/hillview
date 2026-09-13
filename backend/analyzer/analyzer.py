#!/usr/bin/env python3
"""
Continuous photo analysis service.
Connects to PostgreSQL, queries photos without analysis, and processes them.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx

from dotenv import load_dotenv

load_dotenv()

# Add backend to path for database imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from sqlalchemy import select, func
from common.database import SessionLocal
from common.models import Photo

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
	distill_sessions,
)

# Environment variable to control image fetching
FETCH_IMAGES = os.environ.get("ANALYZER_FETCH_IMAGES", "false").lower() == "true"


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
) -> dict | None:
	"""
	Process a single photo: features + distances analysis.

	Returns distilled analysis or None on error.
	"""
	print(f"  Photo: {photo.id} ({photo.original_filename})")

	# Get image URL
	image_url = get_image_url(photo)
	if not image_url:
		print(f"    ✗ No image URL available")
		return None

	if verbose:
		print(f"    Image URL: {image_url}")

	# Prepare image (fetch if needed)
	try:
		final_image_url, image_hash = prepare_image_url(image_url, FETCH_IMAGES)
	except httpx.HTTPStatusError as e:
		if e.response.status_code == 404:
			print(f"    ✗ Image not found (404)")
			return None
		raise

	# Get focal length from EXIF
	focal_length_35mm = get_focal_length(photo)
	if verbose and focal_length_35mm:
		print(f"    Focal length: {focal_length_35mm}mm")

	# Load existing sessions for this photo
	json_path = datadir / f"{photo.file_md5}.json"
	sessions = load_sessions(json_path)

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

	if features_dup:
		print(f"    Features: cached")
	else:
		if not FETCH_IMAGES and not image_checked and not check_image(image_url):
			return None
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

	if distances_dup:
		print(f"    Distances: cached")
	else:
		if not FETCH_IMAGES and not image_checked and not check_image(image_url):
			return None
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
		else:
			print(f"    Distances: ✓")

	# Save sessions
	save_sessions(json_path, sessions)

	# Distill results
	distilled = distill_sessions(sessions)

	distilled['focal_length_35mm'] = focal_length_35mm

	if distilled:
		if verbose:
			print(f"    Distilled analysis:")
			for k, v in distilled.items():
				print(f"      {k}: {v}")

		# Remove metadata fields not needed in DB
		db_analysis = {k: v for k, v in distilled.items()
					   if k in ["closest_object_distance", "farthest_object_distance", "time_of_day", "location_type",
								"scenic_score", "visibility_distance",
								"tallest_building", "features"]}
		#print(f"    Distilled: {list(db_analysis.keys())}")
		return db_analysis
	else:
		print(f"    Distilled: ✗ no successful sessions")
		return None


async def process_photo_and_update_db(photo, datadir: Path, model: str, verbose: bool, db: SessionLocal, dry_run: bool = False):
	print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing photo...")
	try:
		analysis = await process_photo(photo, datadir, model, verbose)

		if analysis:
			if dry_run:
				print(f"    Database: skipped (dry run)")
			elif photo.analysis != analysis:
				photo.analysis = analysis
				await db.commit()
				print(f"    Database: ✓ updated")
		else:
			print(f"    Database: skipped (no analysis)")

	except Exception as e:
		print(f"    Error: {e}")
		import traceback
		traceback.print_exc()
		print(f"sleeping for a while before continuing...")
		await asyncio.sleep(555)

	print()


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
	seen: set[str] = set()

	print(f"Analyzer started")
	print(f"  Model: {model}")
	print(f"  Datadir: {datadir}")
	print(f"  Dry run: {dry_run}")
	print(f"  Fetch images: {FETCH_IMAGES}")
	print(f"  API key file: {os.environ.get('OPENROUTER_API_KEY_FILE', 'NOT SET')}")
	print()

	while True:
		async with SessionLocal() as db:
			# Count remaining unanalyzed photos
			count_result = await db.execute(
				select(func.count(Photo.id))
				.where(Photo.processing_status == 'completed')
				.where(Photo.deleted == False)
				.where(Photo.analysis.is_(None))
			)
			remaining = count_result.scalar()
			print(f"[{datetime.now().strftime('%H:%M:%S')}] Remaining photos to analyze: {remaining}")

			# Query: photos without analysis, completed processing, oldest first
			result = await db.execute(
				select(Photo)
				.where(Photo.processing_status == 'completed')
				.where(Photo.deleted == False)

				.where(Photo.analysis.is_(None))
#				.order_by(Photo.analysis.is_(None).desc())

				.where(Photo.id.notin_(seen))
				.order_by(Photo.uploaded_at.desc())
				.limit(1)
				.with_for_update(skip_locked=True)
			)
			photo = result.scalars().first()

			if photo:
				seen.add(photo.id)
				await process_photo_and_update_db(photo, datadir, model, verbose, db, dry_run=dry_run)
				print(f"{len(seen)} photos processed in this session, ~{remaining-1} remaining.")
				await asyncio.sleep(1)

			else:
				if once:
					print("No photos to analyze.")
					break
				print(f"[{datetime.now().strftime('%H:%M:%S')}] No photos to analyze, sleeping {sleep_interval}s...")
				await asyncio.sleep(sleep_interval)

	print("INITIAL LOOP FINISHED")
	await asyncio.sleep(5)
	while True:
		print(f"[{datetime.now().strftime('%H:%M:%S')}] Still no photos to analyze, sleeping {sleep_interval}s...")
		await asyncio.sleep(sleep_interval)
		while True:
			async with SessionLocal() as db:
				# Count remaining unanalyzed photos
				count_result = await db.execute(
					select(func.count(Photo.id))
					.where(Photo.processing_status == 'completed')
					.where(Photo.deleted == False)
					.where(Photo.analysis.is_(None))
				)
				remaining = count_result.scalar()
				print(f"[{datetime.now().strftime('%H:%M:%S')}] Remaining photos to analyze: {remaining}")

				# Query: photos without analysis, completed processing, oldest first
				result = await db.execute(
					select(Photo)
					.where(Photo.processing_status == 'completed')
					.where(Photo.deleted == False)
					.where(Photo.analysis.is_(None))
					.order_by(Photo.uploaded_at.desc())
					.limit(1)
					.with_for_update(skip_locked=True)
				)
				photo = result.scalars().first()

				if photo:
					await process_photo_and_update_db(photo, datadir, model, verbose, db, dry_run=dry_run)
				else:
					break


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
