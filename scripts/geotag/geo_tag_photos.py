#!/usr/bin/env python3
"""
Geo-tag photos using Hillview's exported location and orientation CSV files.

Usage:
	geo_tag_photos.py --correction auto *.webp
	geo_tag_photos.py --correction +5.0 *.webp
	geo_tag_photos.py --correction 0 photo1.jpg photo2.jpg

The --correction flag accepts a numeric value (seconds to add to photo EXIF
timestamps) or "auto" to detect the correction from QR calibration photos
among the provided files.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from exif import check_exiftool, get_photo_timestamp as get_photo_datetime, datetime_to_ms

# RAW file extensions - exiftool support varies
RAW_EXTENSIONS = {'.cr2', '.cr3', '.nef', '.arw', '.orf', '.rw2', '.dng', '.raf', '.pef', '.srw'}


@dataclass
class PhotoResult:
	photo_path: Path
	success: bool
	message: str
	details: Optional[str] = None


@dataclass
class LocationRecord:
	timestamp: int  # milliseconds
	latitude: float
	longitude: float
	altitude: Optional[float] = None
	accuracy: Optional[float] = None
	speed: Optional[float] = None
	bearing: Optional[float] = None
	source: Optional[str] = None


@dataclass
class OrientationRecord:
	timestamp: int  # milliseconds
	true_heading: float
	pitch: Optional[float] = None
	roll: Optional[float] = None
	source: Optional[str] = None


def parse_float(value: str) -> Optional[float]:
	if value.strip() == "":
		return None
	return float(value)


def get_column_index(header: list[str], name: str) -> Optional[int]:
	clean_header = [h.lstrip('#') for h in header]
	try:
		return clean_header.index(name)
	except ValueError:
		return None


def load_locations(filepath: Path) -> list[LocationRecord]:
	records = []
	with open(filepath, 'r') as f:
		reader = csv.reader(f)
		header = next(reader)
		col = {name: get_column_index(header, name) for name in [
			'timestamp', 'latitude', 'longitude', 'altitude', 'accuracy', 'speed', 'bearing', 'source'
		]}
		for row in reader:
			if not row or len(row) < 3:
				continue
			try:
				records.append(LocationRecord(
					timestamp=int(row[col['timestamp']]),
					latitude=float(row[col['latitude']]),
					longitude=float(row[col['longitude']]),
					altitude=parse_float(row[col['altitude']]) if col['altitude'] is not None and col['altitude'] < len(row) else None,
					accuracy=parse_float(row[col['accuracy']]) if col['accuracy'] is not None and col['accuracy'] < len(row) else None,
					speed=parse_float(row[col['speed']]) if col['speed'] is not None and col['speed'] < len(row) else None,
					bearing=parse_float(row[col['bearing']]) if col['bearing'] is not None and col['bearing'] < len(row) else None,
					source=row[col['source']].strip() if col['source'] is not None and col['source'] < len(row) and row[col['source']].strip() else None,
				))
			except (ValueError, IndexError):
				continue
	return records


def load_orientations(filepath: Path) -> list[OrientationRecord]:
	records = []
	with open(filepath, 'r') as f:
		reader = csv.reader(f)
		header = next(reader)
		col = {name: get_column_index(header, name) for name in [
			'timestamp', 'trueHeading', 'pitch', 'roll', 'source'
		]}
		for row in reader:
			if not row or len(row) < 2:
				continue
			try:
				records.append(OrientationRecord(
					timestamp=int(row[col['timestamp']]),
					true_heading=float(row[col['trueHeading']]),
					pitch=parse_float(row[col['pitch']]) if col['pitch'] is not None and col['pitch'] < len(row) else None,
					roll=parse_float(row[col['roll']]) if col['roll'] is not None and col['roll'] < len(row) else None,
					source=row[col['source']].strip() if col['source'] is not None and col['source'] < len(row) and row[col['source']].strip() else None,
				))
			except (ValueError, IndexError):
				continue
	return records


def load_csv_dir(csv_dir: Path) -> tuple[list[LocationRecord], list[OrientationRecord]]:
	locations = []
	orientations = []

	for filepath in sorted(csv_dir.glob('*.csv')):
		with open(filepath, 'r') as f:
			header = f.readline().strip()
		if header.startswith('#timestamp,latitude,longitude'):
			print(f"Loading locations: {filepath.name}")
			locations.extend(load_locations(filepath))
		elif header.startswith('#timestamp,trueHeading'):
			print(f"Loading orientations: {filepath.name}")
			orientations.extend(load_orientations(filepath))

	locations.sort(key=lambda x: x.timestamp)
	orientations.sort(key=lambda x: x.timestamp)
	print(f"Loaded {len(locations)} locations, {len(orientations)} orientations")
	return locations, orientations


def find_most_recent_before(records: list, target_timestamp: int):
	"""Find the most recent record with timestamp <= target_timestamp."""
	if not records:
		return None
	left, right = 0, len(records) - 1
	result = None
	while left <= right:
		mid = (left + right) // 2
		if records[mid].timestamp <= target_timestamp:
			result = records[mid]
			left = mid + 1
		else:
			right = mid - 1
	return result


def format_ts_utc(timestamp_ms: int) -> str:
	dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
	return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def get_photo_timestamp(photo_path: Path) -> Optional[int]:
	"""Get the EXIF DateTimeOriginal as Unix timestamp in milliseconds."""
	dt = get_photo_datetime(photo_path)
	if dt is None:
		return None
	if dt.tzinfo is None:
		print(f"  Warning: no timezone in EXIF, interpreting as local time")
	return datetime_to_ms(dt)


def get_existing_user_comment(photo_path: Path) -> Optional[dict]:
	"""Try to read and parse existing UserComment as JSON."""
	try:
		result = subprocess.run(
			['exiftool', '-UserComment', '-s3', str(photo_path)],
			capture_output=True, text=True, check=True
		)
		comment = result.stdout.strip()
		if comment:
			return json.loads(comment)
	except (subprocess.CalledProcessError, json.JSONDecodeError):
		pass
	return None


def process_photo(photo_path: Path, locations: list[LocationRecord],
				  orientations: list[OrientationRecord], time_correction_ms: int,
				  dry_run: bool, verbose: bool = True) -> PhotoResult:
	lines = []

	def log(msg: str):
		if verbose:
			lines.append(msg)

	# Warn about RAW files
	if photo_path.suffix.lower() in RAW_EXTENSIONS:
		log(f"  Warning: RAW file - exiftool support varies by format")

	photo_ts = get_photo_timestamp(photo_path)
	if photo_ts is None:
		return PhotoResult(photo_path, False, "Could not read timestamp from photo")

	corrected_ts = photo_ts + time_correction_ms
	log(f"  EXIF timestamp: {format_ts_utc(photo_ts)}")
	if time_correction_ms != 0:
		log(f"  Corrected:      {format_ts_utc(corrected_ts)} (correction: {time_correction_ms/1000:+.1f}s)")

	location = find_most_recent_before(locations, corrected_ts)
	orientation = find_most_recent_before(orientations, corrected_ts)

	if location:
		age_sec = (corrected_ts - location.timestamp) / 1000
		bearing_str = f"{location.bearing:.1f}°" if location.bearing is not None else "n/a"
		alt_str = f"{location.altitude:.1f}m" if location.altitude is not None else "n/a"
		acc_str = f"{location.accuracy:.1f}m" if location.accuracy is not None else "n/a"
		log(f"  Location:    {location.latitude:.6f}, {location.longitude:.6f} @ {format_ts_utc(location.timestamp)} (age: {age_sec:.1f}s)")
		log(f"               alt: {alt_str}, bearing: {bearing_str}, accuracy: {acc_str}")
	else:
		log(f"  Location:    no data before photo")

	if orientation:
		age_sec = (corrected_ts - orientation.timestamp) / 1000
		pitch_str = f"{orientation.pitch:.1f}°" if orientation.pitch is not None else "n/a"
		roll_str = f"{orientation.roll:.1f}°" if orientation.roll is not None else "n/a"
		log(f"  Orientation: heading={orientation.true_heading:.1f}° @ {format_ts_utc(orientation.timestamp)} (age: {age_sec:.1f}s)")
		log(f"               pitch: {pitch_str}, roll: {roll_str}")
	else:
		log(f"  Orientation: no data before photo")

	if not location and not orientation:
		return PhotoResult(photo_path, False, "No location/orientation data", '\n'.join(lines) if lines else None)

	# Build exiftool command
	args = ['exiftool', '-overwrite_original']

	if location:
		args.append(f'-GPSLatitude*={location.latitude}')
		args.append(f'-GPSLongitude*={location.longitude}')

		if location.altitude is not None:
			args.append(f'-GPSAltitude*={location.altitude}')

		if location.accuracy is not None:
			args.append(f'-GPSHPositioningError={location.accuracy}')

		if location.speed is not None:
			speed_kmh = location.speed * 3.6  # m/s to km/h
			args.append(f'-GPSSpeed={speed_kmh}')
			args.append('-GPSSpeedRef=K')

	if orientation:
		args.append(f'-GPSImgDirection*={orientation.true_heading}')
		args.append('-GPSImgDirectionRef=True North')

	# Build UserComment JSON with extra metadata
	comment = get_existing_user_comment(photo_path) or {}
	if location:
		comment['location_age_s'] = round((corrected_ts - location.timestamp) / 1000, 1)
		if location.source:
			comment['location_source'] = location.source
	if orientation:
		if orientation.pitch is not None:
			comment['pitch'] = round(orientation.pitch, 2)
		if orientation.roll is not None:
			comment['roll'] = round(orientation.roll, 2)
		comment['orientation_age_s'] = round((corrected_ts - orientation.timestamp) / 1000, 1)
		if orientation.source:
			comment['orientation_source'] = orientation.source
	if comment:
		args.append(f'-UserComment={json.dumps(comment)}')

	args.append(str(photo_path))

	log(f"  Command: {' '.join(args)}")

	# Build summary with ages
	loc_age_sec = (corrected_ts - location.timestamp) / 1000 if location else None
	bearing_age_sec = (corrected_ts - orientation.timestamp) / 1000 if orientation else None
	loc_str = f"{location.latitude:.6f}, {location.longitude:.6f} (age: {loc_age_sec:.1f}s)" if location else "n/a"
	heading_str = f"{orientation.true_heading:.1f}° (age: {bearing_age_sec:.1f}s)" if orientation else "n/a"

	if dry_run:
		return PhotoResult(photo_path, True, f"Would tag: {loc_str}, heading: {heading_str}", '\n'.join(lines) if lines else None)

	try:
		subprocess.run(args, capture_output=True, text=True, check=True)
		return PhotoResult(photo_path, True, f"Tagged: {loc_str}, heading: {heading_str}", '\n'.join(lines) if lines else None)
	except subprocess.CalledProcessError as e:
		return PhotoResult(photo_path, False, f"exiftool error: {e.stderr}", '\n'.join(lines) if lines else None)


def print_result(result: PhotoResult, verbose: bool = False):
	"""Print a single photo result."""
	status = "✓" if result.success else "✗"
	print(f"{status} {result.photo_path.name}: {result.message}")
	if verbose and result.details:
		print(result.details)


def process_photos_sequential(photos: list[Path], locations: list[LocationRecord],
							  orientations: list[OrientationRecord],
							  time_correction_ms: int, dry_run: bool,
							  verbose: bool) -> list[PhotoResult]:
	"""Process photos sequentially."""
	results = []
	for photo_path in photos:
		if not photo_path.exists():
			results.append(PhotoResult(photo_path, False, "File not found"))
			print_result(results[-1], verbose)
			continue
		result = process_photo(photo_path, locations, orientations, time_correction_ms, dry_run, verbose)
		results.append(result)
		print_result(result, verbose)
	return results


def process_photos_parallel(photos: list[Path], locations: list[LocationRecord],
							orientations: list[OrientationRecord],
							time_correction_ms: int, dry_run: bool,
							verbose: bool, workers: int) -> list[PhotoResult]:
	"""Process photos in parallel using ThreadPoolExecutor."""
	results = []
	valid_photos = []

	# Filter out non-existent files first
	for photo_path in photos:
		if not photo_path.exists():
			result = PhotoResult(photo_path, False, "File not found")
			results.append(result)
			print_result(result, verbose)
		else:
			valid_photos.append(photo_path)

	if not valid_photos:
		return results

	print(f"Processing {len(valid_photos)} photos with {workers} workers...")

	with ThreadPoolExecutor(max_workers=workers) as executor:
		# Submit all tasks
		future_to_photo = {
			executor.submit(
				process_photo, photo_path, locations, orientations,
				time_correction_ms, dry_run, verbose
			): photo_path
			for photo_path in valid_photos
		}

		# Collect results as they complete
		for future in as_completed(future_to_photo):
			photo_path = future_to_photo[future]
			try:
				result = future.result()
			except Exception as e:
				result = PhotoResult(photo_path, False, f"Exception: {e}")
			results.append(result)
			print_result(result, verbose)

	return results


def run_geotagging(csv_dir: Path, time_correction: float, photos: list[Path],
				   dry_run: bool = False, parallel: int | None = None,
				   verbose: bool = False) -> int:
	if not csv_dir.is_dir():
		print(f"Error: {csv_dir} is not a directory")
		return 1

	check_exiftool()

	locations, orientations = load_csv_dir(csv_dir)
	if not locations and not orientations:
		print("Error: No valid CSV files found")
		return 1

	time_correction_ms = int(time_correction * 1000)
	print(f"\nTime correction: {time_correction:+.3f}s")
	if dry_run:
		print("DRY RUN - no changes will be made")

	photos = sorted(photos, key=lambda p: p.name)

	if parallel is not None:
		workers = parallel if parallel > 0 else os.cpu_count() or 4
		results = process_photos_parallel(
			photos, locations, orientations, time_correction_ms,
			dry_run, verbose, workers
		)
	else:
		results = process_photos_sequential(
			photos, locations, orientations, time_correction_ms,
			dry_run, verbose
		)

	print()
	print("\nSummary:")

	results = sorted(results, key=lambda r: r.photo_path.name)
	for result in results:
		print_result(result, verbose)

	success_count = sum(1 for r in results if r.success)
	print(f"\n{'Would process' if dry_run else 'Processed'} {success_count}/{len(photos)} photos")
	return 0 if success_count == len(photos) else 1


def resolve_correction(correction_arg: str, photos: list[Path]) -> float:
	"""Resolve the time correction value.

	correction_arg is either a numeric string or "auto".
	"""
	if correction_arg != "auto":
		val = float(correction_arg)
		print(f"Using provided correction: {val:+.3f}s", file=sys.stderr)
		return val

	env_val = os.environ.get("CORRECTION")
	if env_val:
		val = float(env_val)
		print(f"Using CORRECTION from environment: {val:+.3f}s", file=sys.stderr)
		return val

	from qr_time_correction import compute_correction
	print("No numeric correction provided, scanning QR calibration photos...", file=sys.stderr)
	correction_str = compute_correction(photos)
	val = float(correction_str)
	print(f"Auto-detected correction: {val:+.3f}s", file=sys.stderr)
	return val


def main():
	parser = argparse.ArgumentParser(
		description='Geo-tag photos using Hillview CSV files.',
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog=__doc__
	)
	parser.add_argument('photos', type=Path, nargs='+', help='Image files to geo-tag')
	parser.add_argument('--correction', '-c', default='auto',
						help='Time correction in seconds, or "auto" to detect from QR calibration photos. '
							 'Positive = camera slow, negative = camera fast. (default: auto)')
	parser.add_argument('--csv-dir', type=Path, default=Path("~/GeoTrackingDumps").expanduser(),
						help='Directory containing hillview CSV files (default: ~/GeoTrackingDumps)')
	parser.add_argument('--dry-run', '-n', action='store_true', help='Show what would be done without writing')
	parser.add_argument('--parallel', '-p', type=int, default=40,
						metavar='N', help='Number of parallel workers (default: 40)')
	parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output for each photo')

	args = parser.parse_args()

	existing = [p for p in args.photos if p.exists()]
	missing = [p for p in args.photos if not p.exists()]
	for p in missing:
		print(f"Warning: file not found: {p}", file=sys.stderr)
	if not existing:
		print("Error: no existing image files to process", file=sys.stderr)
		sys.exit(1)

	time_correction = resolve_correction(args.correction, existing)

	sys.exit(run_geotagging(
		csv_dir=args.csv_dir,
		time_correction=time_correction,
		photos=existing,
		dry_run=args.dry_run,
		parallel=args.parallel,
		verbose=args.verbose,
	))


if __name__ == "__main__":
	main()
