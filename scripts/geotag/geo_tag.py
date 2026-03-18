#!/usr/bin/env python3
"""Wrapper for Hillview geotagging workflow.

Usage:
    python geo_tag.py [correction] [image1 image2 ...]

Correction precedence:
- first CLI positional argument when it is numeric
- CORRECTION environment variable
- auto-detection from the selected image files

If no image files are provided, the wrapper falls back to `webp/*` to preserve
compatibility with the existing external-camera workflow.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from geo_tag_photos import run_geotagging
from qr_time_correction import compute_correction


DEFAULT_IMAGE_GLOB = "webp/*"


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def is_numeric(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def parse_args(argv: list[str]) -> tuple[str | None, list[Path]]:
    correction: str | None = None
    raw_paths = argv

    if argv and is_numeric(argv[0]):
        correction = argv[0]
        raw_paths = argv[1:]

    if raw_paths:
        return correction, [Path(path) for path in raw_paths]

    return correction, sorted(Path().glob(DEFAULT_IMAGE_GLOB))


def validate_image_files(image_files: list[Path]) -> list[Path]:
    if not image_files:
        eprint(f"No image files provided and no matches found for {DEFAULT_IMAGE_GLOB}")
        raise SystemExit(1)

    missing = [path for path in image_files if not path.exists()]
    for path in missing:
        eprint(f"Image file not found: {path}")

    existing = [path for path in image_files if path.exists()]
    if not existing:
        eprint("No existing image files to process")
        raise SystemExit(1)

    return existing


def resolve_correction(cli_correction: str | None, image_files: list[Path]) -> str:
    if cli_correction is not None:
        eprint(f"Using provided correction: {cli_correction}")
        return cli_correction

    env_correction = os.environ.get("CORRECTION")
    if env_correction:
        eprint(f"Using CORRECTION from environment: {env_correction}")
        return env_correction

    eprint("No correction provided, scanning QR calibration photos...")
    correction = compute_correction(image_files)
    eprint(f"Auto-detected correction: {correction}")
    return correction


def main() -> int:
    cli_correction, image_files = parse_args(sys.argv[1:])
    image_files = validate_image_files(image_files)
    correction = resolve_correction(cli_correction, image_files)

    return run_geotagging(
        csv_dir=Path("~/GeoTrackingDumps").expanduser(),
        time_correction=float(correction),
        photos=image_files,
        parallel=40,
    )


if __name__ == "__main__":
    raise SystemExit(main())
