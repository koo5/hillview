#!/usr/bin/env python3
"""
Geo-tag photos using Hillview's exported location and orientation CSV files.

Usage:
    python geo_tag_photos.py <csv_dir> <time_offset_seconds> <photo1.jpg> [photo2.jpg ...]

Arguments:
    csv_dir             Directory containing hillview_locations_*.csv and hillview_orientations_*.csv files
    time_offset_seconds Offset in seconds to add to photo EXIF timestamps
                        Positive = photo clock was ahead of real time
                        Negative = photo clock was behind real time

Example:
    python geo_tag_photos.py ./GeoTrackingDumps 0 *.JPG
    python geo_tag_photos.py ./GeoTrackingDumps -2.5 photo1.jpg photo2.jpg
"""

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# RAW file extensions - exiftool support varies
RAW_EXTENSIONS = {'.cr2', '.cr3', '.nef', '.arw', '.orf', '.rw2', '.dng', '.raf', '.pef', '.srw'}


@dataclass
class LocationRecord:
    timestamp: int  # milliseconds
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    accuracy: Optional[float] = None
    speed: Optional[float] = None
    bearing: Optional[float] = None


@dataclass
class OrientationRecord:
    timestamp: int  # milliseconds
    true_heading: float
    pitch: Optional[float] = None
    roll: Optional[float] = None


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
            'timestamp', 'latitude', 'longitude', 'altitude', 'accuracy', 'speed', 'bearing'
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
            'timestamp', 'trueHeading', 'pitch', 'roll'
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
        dt = datetime.strptime(datetime_str, "%Y:%m:%d %H:%M:%S")
        timestamp_ms = int(dt.timestamp() * 1000)
        if subsec:
            subsec_ms = int(float(f"0.{subsec}") * 1000)
            timestamp_ms += subsec_ms
        return timestamp_ms
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"  Error reading timestamp: {e}")
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


def process_photo(photo_path: Path, locations: list[LocationRecord],
                  orientations: list[OrientationRecord], time_offset_ms: int,
                  dry_run: bool) -> bool:
    print(f"\n{'='*60}")
    print(f"Photo: {photo_path.name}")

    # Warn about RAW files
    if photo_path.suffix.lower() in RAW_EXTENSIONS:
        print(f"  Warning: RAW file - exiftool support varies by format")

    photo_ts = get_photo_timestamp(photo_path)
    if photo_ts is None:
        print(f"  Could not read timestamp from photo")
        return False

    corrected_ts = photo_ts - time_offset_ms
    print(f"  EXIF creation: {format_ts_utc(photo_ts)}")
    if time_offset_ms != 0:
        print(f"  Corrected:     {format_ts_utc(corrected_ts)} (offset: {time_offset_ms/1000:+.1f}s)")

    location = find_most_recent_before(locations, corrected_ts)
    orientation = find_most_recent_before(orientations, corrected_ts)

    if location:
        age_sec = (corrected_ts - location.timestamp) / 1000
        bearing_str = f"{location.bearing:.1f}°" if location.bearing is not None else "n/a"
        alt_str = f"{location.altitude:.1f}m" if location.altitude is not None else "n/a"
        acc_str = f"{location.accuracy:.1f}m" if location.accuracy is not None else "n/a"
        print(f"  Location:    {location.latitude:.6f}, {location.longitude:.6f} @ {format_ts_utc(location.timestamp)} (age: {age_sec:.1f}s)")
        print(f"               alt: {alt_str}, bearing: {bearing_str}, accuracy: {acc_str}")
    else:
        print(f"  Location:    no data before photo")

    if orientation:
        age_sec = (corrected_ts - orientation.timestamp) / 1000
        pitch_str = f"{orientation.pitch:.1f}°" if orientation.pitch is not None else "n/a"
        roll_str = f"{orientation.roll:.1f}°" if orientation.roll is not None else "n/a"
        print(f"  Orientation: heading={orientation.true_heading:.1f}° @ {format_ts_utc(orientation.timestamp)} (age: {age_sec:.1f}s)")
        print(f"               pitch: {pitch_str}, roll: {roll_str}")
    else:
        print(f"  Orientation: no data before photo")

    if not location and not orientation:
        print(f"  Skipping - no data")
        return False

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

        # Store pitch/roll in UserComment as JSON
        if orientation.pitch is not None or orientation.roll is not None:
            existing = get_existing_user_comment(photo_path) or {}
            if orientation.pitch is not None:
                existing['pitch'] = round(orientation.pitch, 2)
            if orientation.roll is not None:
                existing['roll'] = round(orientation.roll, 2)
            args.append(f'-UserComment={json.dumps(existing)}')

    args.append(str(photo_path))

    print(f"  Command: {' '.join(args)}")

    if dry_run:
        return True

    try:
        result = subprocess.run(args, capture_output=True, text=True, check=True)
        print(f"  Done.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Error: {e.stderr}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Geo-tag photos using Hillview CSV files.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('csv_dir', type=Path, help='Directory containing hillview CSV files')
    parser.add_argument('time_offset', type=float, help='Time offset in seconds (positive = photo clock was ahead)')
    parser.add_argument('photos', type=Path, nargs='+', help='Image files to geo-tag')
    parser.add_argument('--dry-run', '-n', action='store_true', help='Show what would be done without writing')

    args = parser.parse_args()

    if not args.csv_dir.is_dir():
        print(f"Error: {args.csv_dir} is not a directory")
        sys.exit(1)

    # Check for exiftool
    try:
        subprocess.run(['exiftool', '-ver'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: exiftool not found. Install with: sudo apt install libimage-exiftool-perl")
        sys.exit(1)

    locations, orientations = load_csv_dir(args.csv_dir)
    if not locations and not orientations:
        print("Error: No valid CSV files found")
        sys.exit(1)

    time_offset_ms = int(args.time_offset * 1000)
    print(f"\nTime offset: {args.time_offset:+.3f}s")
    if args.dry_run:
        print("DRY RUN - no changes will be made")

    success_count = 0
    for photo_path in args.photos:
        if not photo_path.exists():
            print(f"\nSkipping {photo_path}: not found")
            continue
        if process_photo(photo_path, locations, orientations, time_offset_ms, args.dry_run):
            success_count += 1

    print(f"\n{'Would process' if args.dry_run else 'Processed'} {success_count}/{len(args.photos)} photos")


if __name__ == '__main__':
    main()
