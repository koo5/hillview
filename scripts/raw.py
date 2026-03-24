#!/usr/bin/env python3
##!/usr/bin/env fish

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
# rawtherapee-cli outputs .tif instead of .tiff despite -o flag
def rename_tif_to_tiff(tiff_dir):
    for f in tiff_dir.glob("*.tif"):
        tiff = f.with_suffix(".tiff")
        if not tiff.exists():
            subprocess.run(["cp", "--reflink=auto", str(f), str(tiff)])
#mv *.tiff tiff/
# profile was: -preset photo -q 98  # -m 6 -af -metadata all
def convert_all_tiff_to_webp(tiff_dir, webp_dir):
  with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
    for f in sorted(Path(".").glob("*.CR2")):
      stem = f.stem
      if (webp_dir / f"{stem}.webp").exists():
          continue
      pool.submit(tiff_to_webp, stem, tiff_dir, webp_dir)

def tiff_to_webp(stem, tiff_dir, webp_dir):
    log(f"Converting {stem}.tiff -> WebP")
    subprocess.run([
        "cwebp", *CWEBP_ARGS,
        str(tiff_dir / f"{stem}.tiff"),
        "-o", str(webp_dir / f"{stem}.webp"),
    ])

def copy_exif():
    subprocess.run([str(SCRIPT_DIR / "exif_tags_from_cr2_to_webp.sh")], check=True)

def geotag():
    geotag_project = SCRIPT_DIR / "geotag"
    subprocess.run([
        "uv", "run",
        "--project", str(geotag_project),
        str(geotag_project / "geo_tag.py"),
    ] + sys.argv[1:], check=True)

if __name__ == "__main__":
    tiff_dir = Path("tiff")
    webp_dir = Path("webp")
    setup_dirs()
    convert_all_cr2_to_tiff(tiff_dir)
    rename_tif_to_tiff(tiff_dir)
    convert_all_tiff_to_webp(tiff_dir, webp_dir)
    copy_exif()
    geotag()
