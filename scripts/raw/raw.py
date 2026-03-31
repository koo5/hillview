#!/usr/bin/env python3
"""
CR2 raw photo processing pipeline.

Converts CR2 files in the current directory through:
  CR2 -> TIFF (via RawTherapee) -> WebP (via cwebp)

Then copies EXIF tags and geotags the WebP files.

Run from a directory containing *.CR2 files.
"""
##!/usr/bin/env fish

import argparse
import subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
MAX_WORKERS = 10
RAWTHERAPEE_PROFILES = [
    "/usr/share/rawtherapee/profiles/Auto-Matched Curve - ISO Low.pp3",
#    str(Path(__file__).resolve().parent / "vivid.pp3"),
]
CWEBP_ARGS = ["-preset", "photo", "-q", "98"]
# Disabled cwebp args, kept for future reference:
# "-m", "6", "-af", "-metadata", "all"

def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)

#set DIR (dirname (readlink -m (status --current-filename)))
#mkdir tiff; mkdir webp; mkdir webp_noanon;
def setup_dirs():
    for d in ["tiff", "webp", "webp_noanon"]:
        Path(d).mkdir(exist_ok=True)

def convert_all_cr2_to_tiff(tiff_dir):
  with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
    for f in sorted(Path(".").glob("*.CR2")):
      # skip if the tiff already exists
      stem = f.stem
      if (tiff_dir / f"{stem}.tif").exists() or (tiff_dir / f"{stem}.tiff").exists():
          continue
      pool.submit(cr2_to_tiff, f, tiff_dir)
def cr2_to_tiff(f, tiff_dir):
    log(f"Converting {f.name} -> TIFF")
    profile_args = [arg for p in RAWTHERAPEE_PROFILES for arg in ("-p", p)]
    subprocess.run([
        "rawtherapee-cli",
        *profile_args,
        "-o", str(tiff_dir / f"{f.stem}.tiff"),
        "-tz", "-b8",
        "-c", str(f),
    ])
def copy_cr2_tags_to_tiffs(tiff_dir):
    """Copy lens/camera EXIF tags from CR2 to TIFF for Hugin compatibility."""
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for cr2 in sorted(Path(".").glob("*.CR2")):
            tiff_path = find_tiff(tiff_dir, cr2.stem)
            pool.submit(copy_cr2_tags_to_tiff, cr2, tiff_path)

def copy_cr2_tags_to_tiff(cr2, tiff_path):
    log(f"Copying EXIF tags {cr2.name} -> {tiff_path.name}")
    subprocess.run([
        "exiftool", "-overwrite_original",
        "-TagsFromFile", str(cr2),
        "-Make", "-Model", "-LensModel", "-FocalLength", "-FocalLengthIn35mmFilm",
        "-DateTimeOriginal",
        # RawTherapee physically rotates pixels, so force Orientation=Normal
        # to avoid viewers applying the rotation a second time
        "-Orientation=1",
        str(tiff_path),
    ], check=True)

def find_tiff(tiff_dir, stem):
    """Find a .tif or .tiff file for the given stem (rawtherapee may produce either)."""
    for ext in (".tiff", ".tif"):
        p = tiff_dir / f"{stem}{ext}"
        if p.exists():
            return p
    raise FileNotFoundError(f"No .tif or .tiff found for {stem} in {tiff_dir}")

# profile was: -preset photo -q 98  # -m 6 -af -metadata all
def convert_all_tiff_to_webp(tiff_dir, webp_dir):
  with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
    for f in sorted(Path(".").glob("*.CR2")):
      stem = f.stem
      if (webp_dir / f"{stem}.webp").exists():
          continue
      pool.submit(tiff_to_webp, find_tiff(tiff_dir, stem), webp_dir)

def tiff_to_webp(tiff_path, webp_dir):
    stem = tiff_path.stem
    log(f"Converting {tiff_path.name} -> WebP")
    subprocess.run([
        "cwebp", *CWEBP_ARGS,
        str(tiff_path),
        "-o", str(webp_dir / f"{stem}.webp"),
    ])

def copy_exif():
    subprocess.run([str(SCRIPT_DIR / "exif_tags_from_cr2_to_webp.sh")], check=True)

def geotag(webp_dir, geotag_args):
    webp_files = sorted(webp_dir.glob("*.webp"))
    if not webp_files:
        log("No webp files to geotag")
        return
    geotag_project = SCRIPT_DIR / "../geotag"
    subprocess.run([
        "uv", "run",
        "--project", str(geotag_project),
        str(geotag_project / "geo_tag_photos.py"),
    ] + geotag_args + [str(f) for f in webp_files], check=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='CR2 raw photo processing pipeline.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--correction', '-c', default=None,
                        help='Time correction for geotagging (seconds or "auto", default: auto)')
    parser.add_argument('--csv-dir', default=None,
                        help='Directory containing hillview CSV files (default: ~/GeoTrackingDumps)')
    args = parser.parse_args()

    geotag_args = []
    if args.correction is not None:
        geotag_args += ['--correction', args.correction]
    if args.csv_dir is not None:
        geotag_args += ['--csv-dir', args.csv_dir]

    tiff_dir = Path("tiff")
    webp_dir = Path("webp")
    setup_dirs()
    convert_all_cr2_to_tiff(tiff_dir)
    copy_cr2_tags_to_tiffs(tiff_dir)
    convert_all_tiff_to_webp(tiff_dir, webp_dir)
    copy_exif()
    geotag(webp_dir, geotag_args)
