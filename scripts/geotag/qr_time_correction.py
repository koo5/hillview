#!/usr/bin/env python3
"""
Scan photos for Hillview timestamp QR codes and calculate camera time correction.

Takes photos that were taken of the Hillview QR timestamp display, reads the
EXIF timestamp (camera time) and the QR code (real UTC time), and calculates
the correction value needed for geo_tag_photos.py.

Usage:
	python qr_time_correction.py photo1.jpg [photo2.jpg ...]

The QR codes contain ISO 8601 timestamps like: 2026-03-15T14:30:05.123Z

Dependencies (install via pyproject.toml):
	pip install -e .
	sudo apt install libzbar0   # zbar shared library for pyzbar
"""

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from exif import check_exiftool, get_photo_timestamp


def eprint(*args, **kwargs):
	print(*args, file=sys.stderr, **kwargs)

try:
	from PIL import Image
	import zxingcpp
except ImportError:
	eprint("Missing dependencies. Install with:")
	eprint("  cd scripts/geotag && pip install -e .")
	sys.exit(1)


@dataclass
class PhotoInfo:
	path: Path
	exif_dt: Optional[datetime] = None
	qr_dt: Optional[datetime] = None
	qr_raw: Optional[str] = None


def parse_qr_timestamp(text: str) -> Optional[datetime]:
	"""Try to parse a QR code string as a Hillview timestamp."""
	# Unix timestamp in milliseconds (e.g. "1742048405123")
	if text.isdigit() and 10 <= len(text) <= 15:
		epoch_ms = int(text)
		return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)

	# Legacy: ISO 8601 format (e.g. "2026-03-15T14:30:05.123Z")
	for fmt in (
		"%Y-%m-%dT%H:%M:%S.%fZ",
		"%Y-%m-%dT%H:%M:%SZ",
		"%Y-%m-%dT%H:%M:%S.%f%z",
		"%Y-%m-%dT%H:%M:%S%z",
	):
		try:
			dt = datetime.strptime(text, fmt)
			if dt.tzinfo is None:
				dt = dt.replace(tzinfo=timezone.utc)
			return dt
		except ValueError:
			continue
	return None


def scan_qr_timestamp(photo_path: Path) -> tuple[Optional[datetime], Optional[str]]:
	"""Scan a photo for Hillview timestamp QR code(s).

	The display shows two double-buffered QR codes. If both decode,
	we pick the most recent one (that's the active/freshest canvas).
	Garbled or non-timestamp QR codes are silently ignored.

	Returns (parsed_datetime, raw_qr_string).
	"""
	try:
		img = Image.open(photo_path)
		results = zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.QRCode)
	except Exception as e:
		return None, f"Image decode error: {e}"

	best_dt: Optional[datetime] = None
	best_raw: Optional[str] = None

	for result in results:
		text = result.text
		dt = parse_qr_timestamp(text)
		if dt is not None:
			if best_dt is None or dt > best_dt:
				best_dt = dt
				best_raw = text

	return best_dt, best_raw


def process_photo(path: Path) -> PhotoInfo:
	"""Read EXIF and scan QR for a single photo. Top-level for multiprocessing."""
	info = PhotoInfo(path=path)
	info.exif_dt = get_photo_timestamp(path)
	info.qr_dt, info.qr_raw = scan_qr_timestamp(path)
	return info


def format_dt(dt: datetime) -> str:
	fmt = "%Y-%m-%d %H:%M:%S"
	if dt.microsecond:
		fmt += ".%f"
	if dt.tzinfo is not None:
		fmt += " %Z"
	else:
		fmt += " (no tz)"
	return dt.strftime(fmt)


def compute_correction(photo_paths: list[Path]) -> str:
	check_exiftool()

	# Phase 1: read EXIF timestamps + scan QR codes in parallel
	valid_paths = [p for p in photo_paths if p.exists()]
	missing = [p for p in photo_paths if not p.exists()]
	for p in missing:
		eprint(f"  {p.name}: file not found, skipping")

	workers = min(len(valid_paths), os.cpu_count() or 4)
	eprint(f"Scanning {len(valid_paths)} file(s) with {workers} workers...\n")

	photos: list[PhotoInfo] = []
	with ProcessPoolExecutor(max_workers=workers) as executor:
		futures = {executor.submit(process_photo, p): p for p in valid_paths}
		for future in as_completed(futures):
			info = future.result()
			if info.qr_dt is not None and info.exif_dt is not None:
				photos.append(info)
				eprint(f"  {info.path.name}: QR and EXIF timestamps found: {format_dt(info.qr_dt)} (QR), {format_dt(info.exif_dt)} (EXIF)")
			else:
				reasons = []
				if info.qr_dt is None:
					reasons.append("no QR")
				if info.exif_dt is None:
					reasons.append("no EXIF")
				eprint(f"  {info.path.name}: {', '.join(reasons)}, skipping")

	if not photos:
		eprint("\nNo photos with both QR and EXIF timestamps found.")
		raise SystemExit(1)

	# Sort by QR timestamp
	photos.sort(key=lambda p: p.qr_dt)

	# Phase 2: display pairs
	#
	# Canon "work timer" model:  on the first shot of a sequence the camera
	# snapshots the main-clock whole second S and initialises a work timer
	# to S.000.  The work timer ticks forward accurately from there.  The
	# unknown offset δ ∈ [0, 1) is the fractional second lost at init.
	#
	# The work timer reads (exif_whole_s + subsec) exactly.  The real
	# camera time is (exif_whole_s + subsec + δ), so:
	#   real_time ∈ [exif_full, exif_full + 1.0)
	# where exif_full = exif_whole_s + subsec.
	#
	# The camera captures the QR after it was rendered, so:
	#   corrected_time ≥ qr_time,  i.e.  c ≥ qr - exif_full
	# The work timer δ adds up to 1s:
	#   c < qr - exif_full + 1.0
	# Per-photo valid range for c:  [qr_s - exif_full, qr_s - exif_full + 1.0)

	eprint(f"\n--- {len(photos)} photo(s) with QR+EXIF, sorted by QR time ---\n")

	# Build per-photo data: (exif_full, qr_s, range_lo, range_hi)
	photo_data = []
	for info in photos:
		exif_full = info.exif_dt.timestamp()
		qr_s = info.qr_dt.timestamp()
		range_lo = qr_s - exif_full            # inclusive lower bound
		range_hi = qr_s - exif_full + 1.0      # exclusive upper bound
		photo_data.append((exif_full, qr_s, range_lo, range_hi))

		exif_utc = info.exif_dt.astimezone(timezone.utc)
		subsec = exif_full - int(exif_full)
		eprint(f"  {info.path.name}")
		eprint(f"    EXIF (camera):  {format_dt(exif_utc)}  (subsec: {subsec:.3f})")
		eprint(f"    QR   (real):    {format_dt(info.qr_dt)}  ({info.qr_raw})")
		eprint(f"    valid c range:  [{range_lo:+.3f}s, {range_hi:+.3f}s)")
		eprint()

	for leeway_ms in range(1000):
		optimal = find_correction_range(photos, photo_data, leeway_ms)
		if optimal is not None:
			return f"{optimal:+.3f}"

	eprint("No valid correction found even with 999ms leeway.")
	raise SystemExit(1)


def find_correction_range(photos, photo_data, leeway_ms):
	"""Try to find a correction range with the given leeway.

	Leeway widens each photo's valid range by leeway_ms in each direction,
	accounting for timing uncertainty beyond the subsecond lower bound.

	Returns True if a valid range was found.
	"""
	leeway_s = leeway_ms / 1000.0

	all_lo = [lo - leeway_s for _, _, lo, _ in photo_data]
	all_hi = [hi + leeway_s for _, _, _, hi in photo_data]
	start_c_ms = int(min(all_lo) * 1000) - 1000
	end_c_ms = int(max(all_hi) * 1000) + 1000

	def all_match(c_ms: int) -> bool:
		c_s = c_ms / 1000.0
		for lo, hi in zip(all_lo, all_hi):
			if not (lo <= c_s < hi):
				return False
		return True

	match_start_ms = None
	match_end_ms = None

	c_ms = start_c_ms
	while c_ms <= end_c_ms:
		if all_match(c_ms):
			if match_start_ms is None:
				match_start_ms = c_ms
		else:
			if match_start_ms is not None and match_end_ms is None:
				match_end_ms = c_ms
				break
		c_ms += 1

	if match_start_ms is None:
		return None

	if match_end_ms is None:
		match_end_ms = end_c_ms

	match_start_s = match_start_ms / 1000.0
	match_end_s = (match_end_ms - 1) / 1000.0  # last matching ms
	midpoint_s = (match_start_s + match_end_s) / 2.0
	range_width_s = match_end_s - match_start_s

	# Optimal correction: mean of (qr - exif_full) minimizes mean error to 0
	mean_diff = sum(qr_s - exif_full for exif_full, qr_s, _, _ in photo_data) / len(photo_data)
	optimal_s = mean_diff

	eprint("=" * 60)
	if leeway_ms > 0:
		eprint(f"  Leeway:     {leeway_ms}ms (each photo's range widened by +/-{leeway_ms}ms)")
	eprint(f"  Valid correction range:")
	eprint(f"    Start:    {match_start_s:+.3f}s")
	eprint(f"    End:      {match_end_s:+.3f}s")
	eprint(f"    Width:    {range_width_s:.3f}s")
	eprint(f"    Midpoint: {midpoint_s:+.3f}s")
	eprint(f"    Optimal:  {optimal_s:+.3f}s (minimizes mean error)")
	eprint()
	eprint(f"  Recommended correction for geo_tag_photos.py:")
	eprint(f"    python geo_tag_photos.py <csv_dir> {optimal_s:+.3f} <photos...>")
	eprint()
	if optimal_s > 0:
		eprint(f"  Camera is ~{abs(optimal_s):.1f}s slow (EXIF behind real time, correction adds time)")
	elif optimal_s < 0:
		eprint(f"  Camera is ~{abs(optimal_s):.1f}s fast (EXIF ahead of real time, correction subtracts time)")
	else:
		eprint(f"  Camera clock appears accurate")

	# Phase 4: per-photo error analysis using optimal correction
	eprint(f"\n--- Per-photo error (corrected EXIF vs QR) using c = {optimal_s:+.3f}s ---\n")
	errors = []
	for info, (exif_full, qr_s, _, _) in zip(photos, photo_data):
		corrected_s = exif_full + optimal_s
		error_ms = (corrected_s - qr_s) * 1000
		errors.append(error_ms)
		eprint(f"  {info.path.name}:  error = {error_ms:+.0f}ms")

	eprint()
	eprint(f"  Mean error:     {sum(errors) / len(errors):+.0f}ms")
	eprint(f"  Max |error|:    {max(abs(e) for e in errors):.0f}ms")

	return optimal_s


def main():
	parser = argparse.ArgumentParser(
		description='Scan photos for Hillview QR timestamps and calculate camera time correction.',
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog=__doc__
	)
	parser.add_argument('photos', type=Path, nargs='+', help='Image files to scan')

	args = parser.parse_args()
	print(compute_correction(args.photos))


if __name__ == '__main__':
	main()
