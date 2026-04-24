"""Shared EXIF timestamp utilities for Hillview geotag tools."""

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def check_exiftool():
	"""Check that exiftool is installed, exit if not."""
	try:
		subprocess.run(['exiftool', '-ver'], capture_output=True, check=True)
	except (subprocess.CalledProcessError, FileNotFoundError):
		print("Error: exiftool not found. Install with: sudo apt install libimage-exiftool-perl")
		sys.exit(1)


def get_photo_timestamp(photo_path: Path) -> Optional[datetime]:
	"""Get the EXIF DateTimeOriginal as a datetime.

	Returns a timezone-aware datetime when timezone info is available in EXIF,
	otherwise a naive datetime (caller must handle timezone assumption).
	Subsecond precision is preserved when available.
	"""
	try:
		# SubSecDateTimeOriginal includes subseconds and timezone offset,
		# e.g. "2026:03:10 16:52:43.00+01:00"
		result = subprocess.run(
			['exiftool', '-SubSecDateTimeOriginal', '-s3', str(photo_path)],
			capture_output=True, text=True, check=True
		)
		datetime_str = result.stdout.strip()
		if datetime_str:
			for fmt in ("%Y:%m:%d %H:%M:%S.%f%z", "%Y:%m:%d %H:%M:%S%z",
						"%Y:%m:%d %H:%M:%S.%f", "%Y:%m:%d %H:%M:%S"):
				try:
					return datetime.strptime(datetime_str, fmt)
				except ValueError:
					continue

		# Fallback: separate tags for older files without SubSecDateTimeOriginal
		result = subprocess.run(
			['exiftool', '-DateTimeOriginal', '-SubSecTimeOriginal', '-s3', str(photo_path)],
			capture_output=True, text=True, check=True
		)
		lines = result.stdout.strip().split('\n')
		if not lines or not lines[0]:
			return None
		datetime_str = lines[0].strip()
		subsec = lines[1].strip() if len(lines) > 1 and lines[1].strip() else "0"
		dt = datetime.strptime(datetime_str, "%Y:%m:%d %H:%M:%S")
		if subsec:
			microseconds = int(float(f"0.{subsec}") * 1_000_000)
			dt = dt.replace(microsecond=microseconds)
		return dt
	except (subprocess.CalledProcessError, ValueError) as e:
		print(f"  Error reading timestamp from {photo_path}: {e}")
		return None


def datetime_to_ms(dt: datetime) -> int:
	"""Convert a datetime to Unix timestamp in milliseconds."""
	return int(dt.timestamp() * 1000)
