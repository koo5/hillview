#!/usr/bin/env python3
"""
Geo-tag photos using Hillview's exported location and orientation CSV files.

Usage:
    python geo_tag_photos.py <csv_dir> <time_offset_seconds> <photo1.jpg> [photo2.jpg ...]
    python geo_tag_photos.py <csv_dir> <time_offset_seconds> --output-dir ./output *.CR2

Arguments:
    csv_dir             Directory containing hillview_locations_*.csv and hillview_orientations_*.csv files
    time_offset_seconds Offset in seconds (can be fractional) to add to photo EXIF timestamps
                        Positive = photo clock was ahead of real time
                        Negative = photo clock was behind real time
    photos              One or more image files to geo-tag (JPEG, WebP, or RAW like CR2, NEF, ARW)

Options:
    --output-dir DIR    Write output files to this directory instead of modifying in place.
                        RAW files will be converted to WebP.
    --format FORMAT     Output format for conversions (default: webp). Options: webp, jpg

Example:
    python geo_tag_photos.py ./GeoTrackingDumps -2.5 photo1.jpg photo2.jpg
    python geo_tag_photos.py ./GeoTrackingDumps 0 --output-dir ./tagged *.CR2
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# RAW file extensions (case-insensitive)
RAW_EXTENSIONS = {'.cr2', '.cr3', '.nef', '.arw', '.orf', '.rw2', '.dng', '.raf', '.pef', '.srw'}

# Extensions that can be written to directly
WRITABLE_EXTENSIONS = {'.jpg', '.jpeg', '.webp', '.png', '.tif', '.tiff'}


@dataclass
class LocationRecord:
    timestamp: int  # milliseconds
    latitude: float
    longitude: float
    source: str
    altitude: Optional[float] = None
    accuracy: Optional[float] = None
    vertical_accuracy: Optional[float] = None
    speed: Optional[float] = None
    bearing: Optional[float] = None


@dataclass
class OrientationRecord:
    timestamp: int  # milliseconds
    true_heading: float
    magnetic_heading: Optional[float] = None
    heading_accuracy: Optional[float] = None
    accuracy_level: Optional[int] = None
    source: str = ""
    pitch: Optional[float] = None
    roll: Optional[float] = None


def parse_float(value: str) -> Optional[float]:
    """Parse a float value, returning None for empty strings."""
    if value.strip() == "":
        return None
    return float(value)


def parse_int(value: str) -> Optional[int]:
    """Parse an int value, returning None for empty strings."""
    if value.strip() == "":
        return None
    return int(value)


def detect_csv_type(filepath: Path) -> Optional[str]:
    """Detect CSV type from header. Returns 'locations', 'orientations', or None."""
    with open(filepath, 'r') as f:
        header = f.readline().strip()
        if header.startswith('#timestamp,latitude,longitude'):
            return 'locations'
        elif header.startswith('#timestamp,trueHeading'):
            return 'orientations'
    return None


def get_column_index(header: list[str], name: str) -> Optional[int]:
    """Get column index by name, handling the # prefix on first column."""
    # Clean up header names (remove # prefix from first column)
    clean_header = [h.lstrip('#') for h in header]
    try:
        return clean_header.index(name)
    except ValueError:
        return None


def load_locations(filepath: Path) -> list[LocationRecord]:
    """Load location records from a CSV file using header-based column lookup."""
    records = []
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)

        # Get column indices
        col = {name: get_column_index(header, name) for name in [
            'timestamp', 'latitude', 'longitude', 'source', 'altitude',
            'accuracy', 'verticalAccuracy', 'speed', 'bearing'
        ]}

        for row in reader:
            if not row or len(row) < 4:
                continue
            try:
                records.append(LocationRecord(
                    timestamp=int(row[col['timestamp']]),
                    latitude=float(row[col['latitude']]),
                    longitude=float(row[col['longitude']]),
                    source=row[col['source']] if col['source'] is not None else "",
                    altitude=parse_float(row[col['altitude']]) if col['altitude'] is not None and col['altitude'] < len(row) else None,
                    accuracy=parse_float(row[col['accuracy']]) if col['accuracy'] is not None and col['accuracy'] < len(row) else None,
                    vertical_accuracy=parse_float(row[col['verticalAccuracy']]) if col['verticalAccuracy'] is not None and col['verticalAccuracy'] < len(row) else None,
                    speed=parse_float(row[col['speed']]) if col['speed'] is not None and col['speed'] < len(row) else None,
                    bearing=parse_float(row[col['bearing']]) if col['bearing'] is not None and col['bearing'] < len(row) else None,
                ))
            except (ValueError, IndexError) as e:
                print(f"  Warning: skipping malformed row in {filepath.name}: {e}")
                continue
    return records


def load_orientations(filepath: Path) -> list[OrientationRecord]:
    """Load orientation records from a CSV file using header-based column lookup."""
    records = []
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)

        # Get column indices
        col = {name: get_column_index(header, name) for name in [
            'timestamp', 'trueHeading', 'magneticHeading', 'headingAccuracy',
            'accuracyLevel', 'source', 'pitch', 'roll'
        ]}

        for row in reader:
            if not row or len(row) < 2:
                continue
            try:
                records.append(OrientationRecord(
                    timestamp=int(row[col['timestamp']]),
                    true_heading=float(row[col['trueHeading']]),
                    magnetic_heading=parse_float(row[col['magneticHeading']]) if col['magneticHeading'] is not None and col['magneticHeading'] < len(row) else None,
                    heading_accuracy=parse_float(row[col['headingAccuracy']]) if col['headingAccuracy'] is not None and col['headingAccuracy'] < len(row) else None,
                    accuracy_level=parse_int(row[col['accuracyLevel']]) if col['accuracyLevel'] is not None and col['accuracyLevel'] < len(row) else None,
                    source=row[col['source']] if col['source'] is not None and col['source'] < len(row) else "",
                    pitch=parse_float(row[col['pitch']]) if col['pitch'] is not None and col['pitch'] < len(row) else None,
                    roll=parse_float(row[col['roll']]) if col['roll'] is not None and col['roll'] < len(row) else None,
                ))
            except (ValueError, IndexError) as e:
                print(f"  Warning: skipping malformed row in {filepath.name}: {e}")
                continue
    return records


def load_csv_dir(csv_dir: Path) -> tuple[list[LocationRecord], list[OrientationRecord]]:
    """Load all CSV files from a directory."""
    locations = []
    orientations = []

    for filepath in csv_dir.glob('*.csv'):
        csv_type = detect_csv_type(filepath)
        if csv_type == 'locations':
            print(f"Loading locations from: {filepath.name}")
            locations.extend(load_locations(filepath))
        elif csv_type == 'orientations':
            print(f"Loading orientations from: {filepath.name}")
            orientations.extend(load_orientations(filepath))
        else:
            print(f"Skipping unknown CSV: {filepath.name}")

    # Sort by timestamp
    locations.sort(key=lambda x: x.timestamp)
    orientations.sort(key=lambda x: x.timestamp)

    print(f"Loaded {len(locations)} location records, {len(orientations)} orientation records")
    return locations, orientations


def find_nearest(records: list, target_timestamp: int, max_diff_ms: int = 60000):
    """Find the record nearest to the target timestamp within max_diff_ms."""
    if not records:
        return None

    # Binary search for efficiency
    left, right = 0, len(records) - 1
    while left < right:
        mid = (left + right) // 2
        if records[mid].timestamp < target_timestamp:
            left = mid + 1
        else:
            right = mid

    # Check neighbors to find the closest
    best = None
    best_diff = max_diff_ms + 1

    for i in range(max(0, left - 1), min(len(records), left + 2)):
        diff = abs(records[i].timestamp - target_timestamp)
        if diff < best_diff:
            best_diff = diff
            best = records[i]

    if best_diff <= max_diff_ms:
        return best
    return None


def get_photo_timestamp(photo_path: Path) -> Optional[int]:
    """Get the EXIF DateTimeOriginal from a photo, return as Unix timestamp in milliseconds."""
    try:
        result = subprocess.run(
            ['exiftool', '-DateTimeOriginal', '-SubSecTimeOriginal', '-s3', str(photo_path)],
            capture_output=True, text=True, check=True
        )
        lines = result.stdout.strip().split('\n')
        if not lines or not lines[0]:
            return None

        datetime_str = lines[0].strip()
        subsec = lines[1].strip() if len(lines) > 1 and lines[1].strip() else "0"

        # Parse datetime (format: "2024:01:15 14:30:45")
        dt = datetime.strptime(datetime_str, "%Y:%m:%d %H:%M:%S")
        timestamp_ms = int(dt.timestamp() * 1000)

        # Add subseconds if available
        if subsec:
            # SubSecTimeOriginal is typically in units where "123" means 0.123 seconds
            subsec_ms = int(float(f"0.{subsec}") * 1000)
            timestamp_ms += subsec_ms

        return timestamp_ms
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"Error reading timestamp from {photo_path}: {e}")
        return None


def is_raw_file(filepath: Path) -> bool:
    """Check if file is a RAW image format."""
    return filepath.suffix.lower() in RAW_EXTENSIONS


def convert_raw_to_output(src_path: Path, output_dir: Path, output_format: str,
                          dry_run: bool = False) -> Optional[Path]:
    """Convert a RAW file to WebP/JPEG using ImageMagick or dcraw.

    Returns the path to the converted file, or None on failure.
    """
    output_ext = '.webp' if output_format == 'webp' else '.jpg'
    output_path = output_dir / (src_path.stem + output_ext)

    if dry_run:
        print(f"  Would convert {src_path.name} -> {output_path.name}")
        return output_path

    # Try using ImageMagick (requires dcraw/ufraw delegate for RAW)
    try:
        # First try with magick (ImageMagick 7) then convert (ImageMagick 6)
        for cmd in ['magick', 'convert']:
            try:
                args = [cmd, str(src_path)]
                if output_format == 'webp':
                    args.extend(['-quality', '90'])
                else:
                    args.extend(['-quality', '95'])
                args.append(str(output_path))

                result = subprocess.run(args, capture_output=True, text=True, timeout=120)
                if result.returncode == 0 and output_path.exists():
                    print(f"  Converted {src_path.name} -> {output_path.name}")
                    return output_path
            except FileNotFoundError:
                continue

        print(f"  Error: ImageMagick not found or failed to convert {src_path.name}")
        return None

    except subprocess.TimeoutExpired:
        print(f"  Error: Conversion timed out for {src_path.name}")
        return None
    except Exception as e:
        print(f"  Error converting {src_path.name}: {e}")
        return None


def copy_to_output(src_path: Path, output_dir: Path, dry_run: bool = False) -> Optional[Path]:
    """Copy a file to the output directory."""
    output_path = output_dir / src_path.name

    if dry_run:
        print(f"  Would copy {src_path.name} -> {output_path}")
        return output_path

    try:
        shutil.copy2(src_path, output_path)
        return output_path
    except Exception as e:
        print(f"  Error copying {src_path.name}: {e}")
        return None


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


def write_exif_tags(photo_path: Path, location: Optional[LocationRecord],
                    orientation: Optional[OrientationRecord], dry_run: bool = False) -> bool:
    """Write GPS and orientation EXIF tags to a photo using exiftool."""
    args = ['exiftool', '-overwrite_original']

    if location:
        # GPS coordinates
        lat_ref = 'N' if location.latitude >= 0 else 'S'
        lon_ref = 'E' if location.longitude >= 0 else 'W'
        args.extend([
            f'-GPSLatitude={abs(location.latitude)}',
            f'-GPSLatitudeRef={lat_ref}',
            f'-GPSLongitude={abs(location.longitude)}',
            f'-GPSLongitudeRef={lon_ref}',
        ])

        if location.altitude is not None:
            alt_ref = 0 if location.altitude >= 0 else 1  # 0 = above sea level, 1 = below
            args.extend([
                f'-GPSAltitude={abs(location.altitude)}',
                f'-GPSAltitudeRef={alt_ref}',
            ])

        if location.speed is not None:
            # Convert m/s to km/h for GPSSpeed
            speed_kmh = location.speed * 3.6
            args.extend([
                f'-GPSSpeed={speed_kmh}',
                '-GPSSpeedRef=K',  # K = km/h
            ])

        if location.accuracy is not None:
            args.append(f'-GPSHPositioningError={location.accuracy}')

    if orientation:
        # Image direction (compass heading)
        args.extend([
            f'-GPSImgDirection={orientation.true_heading}',
            '-GPSImgDirectionRef=T',  # T = True north
        ])

        # Store pitch and roll in UserComment as JSON (extend existing if present)
        if orientation.pitch is not None or orientation.roll is not None:
            existing = get_existing_user_comment(photo_path) or {}
            if orientation.pitch is not None:
                existing['pitch'] = round(orientation.pitch, 2)
            if orientation.roll is not None:
                existing['roll'] = round(orientation.roll, 2)
            args.append(f'-UserComment={json.dumps(existing)}')

    if len(args) == 2:  # Only 'exiftool' and '-overwrite_original'
        print(f"  No data to write for {photo_path.name}")
        return False

    args.append(str(photo_path))

    if dry_run:
        print(f"  Would run: {' '.join(args)}")
        return True

    try:
        result = subprocess.run(args, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Error writing EXIF to {photo_path}: {e.stderr}")
        return False


def process_photo(photo_path: Path, locations: list[LocationRecord],
                  orientations: list[OrientationRecord], time_offset_ms: int,
                  max_time_diff_ms: int, output_dir: Optional[Path],
                  output_format: str, dry_run: bool) -> bool:
    """Process a single photo: find matching records and write EXIF tags.

    If output_dir is specified:
    - RAW files are converted to output_format (webp/jpg)
    - Other files are copied to output_dir
    - EXIF is written to the output file

    If output_dir is None:
    - EXIF is written directly to the input file (RAW files are skipped)
    """
    print(f"\nProcessing: {photo_path.name}")

    # Get photo timestamp from source file
    photo_ts = get_photo_timestamp(photo_path)
    if photo_ts is None:
        print(f"  Could not read timestamp from photo")
        return False

    # Apply time offset (positive offset means photo clock was ahead)
    corrected_ts = photo_ts - time_offset_ms

    photo_dt = datetime.fromtimestamp(photo_ts / 1000)
    corrected_dt = datetime.fromtimestamp(corrected_ts / 1000)
    print(f"  Photo timestamp: {photo_dt} (corrected: {corrected_dt})")

    # Find nearest records
    location = find_nearest(locations, corrected_ts, max_time_diff_ms)
    orientation = find_nearest(orientations, corrected_ts, max_time_diff_ms)

    if location:
        diff_sec = (location.timestamp - corrected_ts) / 1000
        print(f"  Found location: {location.latitude:.6f}, {location.longitude:.6f} "
              f"(diff: {diff_sec:+.1f}s, accuracy: {location.accuracy}m)")
    else:
        print(f"  No location found within {max_time_diff_ms/1000:.0f}s")

    if orientation:
        diff_sec = (orientation.timestamp - corrected_ts) / 1000
        print(f"  Found orientation: heading={orientation.true_heading:.1f}° "
              f"pitch={orientation.pitch}° roll={orientation.roll}° (diff: {diff_sec:+.1f}s)")
    else:
        print(f"  No orientation found within {max_time_diff_ms/1000:.0f}s")

    if not location and not orientation:
        print(f"  Skipping - no matching data")
        return False

    # Determine target file for EXIF writing
    target_path = photo_path
    is_raw = is_raw_file(photo_path)

    if output_dir:
        if is_raw:
            # Convert RAW to output format
            target_path = convert_raw_to_output(photo_path, output_dir, output_format, dry_run)
            if target_path is None:
                return False
        else:
            # Copy non-RAW file to output directory
            target_path = copy_to_output(photo_path, output_dir, dry_run)
            if target_path is None:
                return False
    elif is_raw:
        print(f"  Skipping RAW file (use --output-dir to convert)")
        return False

    # Write EXIF tags to target file
    success = write_exif_tags(target_path, location, orientation, dry_run)
    if success:
        print(f"  {'Would write' if dry_run else 'Wrote'} EXIF tags to {target_path.name}")
    return success


def main():
    parser = argparse.ArgumentParser(
        description='Geo-tag photos using Hillview exported CSV files.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('csv_dir', type=Path,
                        help='Directory containing hillview CSV files')
    parser.add_argument('time_offset', type=float,
                        help='Time offset in seconds (positive = photo clock was ahead)')
    parser.add_argument('photos', type=Path, nargs='+',
                        help='Image files to geo-tag (JPEG, WebP, or RAW)')
    parser.add_argument('--output-dir', '-o', type=Path, default=None,
                        help='Output directory (RAW files will be converted)')
    parser.add_argument('--format', '-f', choices=['webp', 'jpg'], default='webp',
                        help='Output format for RAW conversion (default: webp)')
    parser.add_argument('--max-time-diff', type=float, default=60.0,
                        help='Maximum time difference in seconds to match (default: 60)')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Show what would be done without making changes')

    args = parser.parse_args()

    # Validate CSV directory
    if not args.csv_dir.is_dir():
        print(f"Error: {args.csv_dir} is not a directory")
        sys.exit(1)

    # Create output directory if specified
    if args.output_dir:
        if not args.dry_run:
            args.output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Output directory: {args.output_dir}")

    # Check for exiftool
    try:
        subprocess.run(['exiftool', '-ver'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: exiftool is not installed or not in PATH")
        print("Install it with: sudo apt install libimage-exiftool-perl")
        sys.exit(1)

    # Check for ImageMagick if we have RAW files and output dir
    has_raw_files = any(is_raw_file(p) for p in args.photos if p.exists())
    if has_raw_files and args.output_dir:
        has_imagemagick = False
        for cmd in ['magick', 'convert']:
            try:
                subprocess.run([cmd, '-version'], capture_output=True, check=True)
                has_imagemagick = True
                break
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        if not has_imagemagick:
            print("Warning: ImageMagick not found. RAW conversion may fail.")
            print("Install it with: sudo apt install imagemagick dcraw")

    # Load CSV data
    locations, orientations = load_csv_dir(args.csv_dir)

    if not locations and not orientations:
        print("Error: No valid CSV files found")
        sys.exit(1)

    # Convert offset to milliseconds
    time_offset_ms = int(args.time_offset * 1000)
    max_time_diff_ms = int(args.max_time_diff * 1000)

    print(f"\nTime offset: {args.time_offset:+.3f}s")
    print(f"Max time difference: {args.max_time_diff:.1f}s")
    if args.dry_run:
        print("DRY RUN - no changes will be made")

    # Process each photo
    success_count = 0
    for photo_path in args.photos:
        if not photo_path.exists():
            print(f"\nSkipping {photo_path}: file not found")
            continue
        if process_photo(photo_path, locations, orientations,
                        time_offset_ms, max_time_diff_ms,
                        args.output_dir, args.format, args.dry_run):
            success_count += 1

    print(f"\n{'Would process' if args.dry_run else 'Processed'} {success_count}/{len(args.photos)} photos")


if __name__ == '__main__':
    main()
