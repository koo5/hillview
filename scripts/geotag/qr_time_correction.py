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
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from exif import check_exiftool, get_photo_timestamp

try:
    from PIL import Image
    import zxingcpp
except ImportError:
    print("Missing dependencies. Install with:")
    print("  cd scripts/geotag && pip install -e .")
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

    return None, None


def process_photo(path: Path) -> PhotoInfo:
    """Read EXIF and scan QR for a single photo. Top-level for multiprocessing."""
    info = PhotoInfo(path=path)
    exif_dt = get_photo_timestamp(path)
    if exif_dt is not None:
        info.exif_dt = exif_dt.replace(microsecond=0)
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


def main():
    parser = argparse.ArgumentParser(
        description='Scan photos for Hillview QR timestamps and calculate camera time correction.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('photos', type=Path, nargs='+', help='Image files to scan')

    args = parser.parse_args()
    check_exiftool()

    # Phase 1: read EXIF timestamps + scan QR codes in parallel
    valid_paths = [p for p in args.photos if p.exists()]
    missing = [p for p in args.photos if not p.exists()]
    for p in missing:
        print(f"  {p.name}: file not found, skipping")

    workers = min(len(valid_paths), os.cpu_count() or 4)
    print(f"Scanning {len(valid_paths)} file(s) with {workers} workers...\n")

    photos: list[PhotoInfo] = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_photo, p): p for p in valid_paths}
        for future in as_completed(futures):
            info = future.result()
            if info.qr_dt is not None and info.exif_dt is not None:
                photos.append(info)
            else:
                reasons = []
                if info.qr_dt is None:
                    reasons.append("no QR")
                if info.exif_dt is None:
                    reasons.append("no EXIF")
                print(f"  {info.path.name}: {', '.join(reasons)}, skipping")

    if not photos:
        print("\nNo photos with both QR and EXIF timestamps found.")
        sys.exit(1)

    # Sort by QR timestamp
    photos.sort(key=lambda p: p.qr_dt)

    # Phase 2: display pairs
    print(f"\n--- {len(photos)} photo(s) with QR+EXIF, sorted by QR time ---\n")
    for info in photos:
        exif_utc = info.exif_dt.astimezone(timezone.utc)
        diff_s = info.qr_dt.timestamp() - info.exif_dt.timestamp()
        print(f"  {info.path.name}")
        print(f"    EXIF (camera):  {format_dt(exif_utc)}")
        print(f"    QR   (real):    {format_dt(info.qr_dt)}  ({info.qr_raw})")
        print(f"    diff:           {diff_s:+.3f}s")
        print()

    # Phase 3: find the correction range
    #
    # For correction c, photo i matches when the corrected EXIF time is
    # within 1 second of the QR time:
    #   abs((exif_s + c) - qr_s) < 1.0
    #
    # exif_s is integer seconds (EXIF precision), qr_s is full-precision.
    # We sweep c from an extreme by 1ms to find where all photos match.

    pairs = []  # (exif_s: int, qr_s: float)
    for info in photos:
        exif_s = int(info.exif_dt.timestamp())
        qr_s = info.qr_dt.timestamp()
        pairs.append((exif_s, qr_s))

    diffs = [qs - es for es, qs in pairs]
    start_c_ms = int((min(diffs) - 2) * 1000)
    end_c_ms = int((max(diffs) + 2) * 1000)

    def all_match(c_ms: int) -> bool:
        c_s = c_ms / 1000.0
        for exif_s, qr_s in pairs:
            if abs(exif_s + c_s - qr_s) >= 1.0:
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
        print("No correction value found that makes all photos match.")
        print("No correction makes all photos match within 1 second.")

        # Show per-photo valid ranges for debugging
        print("\nPer-photo valid ranges (c where |exif+c - qr| < 1):")
        for info, (es, qs) in zip(photos, pairs):
            lo = qs - es - 1
            hi = qs - es + 1
            print(f"  {info.path.name}: ({lo:+.3f}s, {hi:+.3f}s)")
        sys.exit(1)

    if match_end_ms is None:
        # Ran off the end of search range, shouldn't happen but handle it
        match_end_ms = end_c_ms

    match_start_s = match_start_ms / 1000.0
    match_end_s = (match_end_ms - 1) / 1000.0  # last matching value
    midpoint_s = (match_start_s + match_end_s) / 2.0
    range_width_s = match_end_s - match_start_s

    print("=" * 60)
    print(f"  Valid correction range:")
    print(f"    Start:    {match_start_s:+.3f}s")
    print(f"    End:      {match_end_s:+.3f}s")
    print(f"    Width:    {range_width_s:.3f}s")
    print(f"    Midpoint: {midpoint_s:+.3f}s")
    print()

    recommended = round(midpoint_s, 1)
    print(f"  Recommended correction for geo_tag_photos.py:")
    print(f"    python geo_tag_photos.py <csv_dir> {recommended:+.1f} <photos...>")
    print()
    if midpoint_s > 0:
        print(f"  Camera is ~{abs(midpoint_s):.1f}s slow (EXIF behind real time, correction adds time)")
    elif midpoint_s < 0:
        print(f"  Camera is ~{abs(midpoint_s):.1f}s fast (EXIF ahead of real time, correction subtracts time)")
    else:
        print(f"  Camera clock appears accurate")


if __name__ == '__main__':
    main()
