#!/usr/bin/env python3
"""
Batch-convert CR2 raw files to TIFF using the flatpak darktable-cli wrapper.

Respects each CR2's own `.CR2.xmp` sidecar (unlike letting Hugin drive the
conversion, which injects its own stripped XMP on the second image onward
and overrides the sidecar).

The wrapper script also copies lens/camera EXIF from the CR2 onto the TIFF
so Hugin doesn't prompt for lens parameters.

Usage:
	raw_darktable.py [directory] [--output DIR] [--jobs N] [--bpp 8|16|32]

Defaults:
	directory = current working directory
	output    = <directory>/tiff
	jobs      = 4    (darktable is RAM-hungry; raise cautiously)
	bpp       = 16
"""

import argparse
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DARKTABLE_WRAPPER = SCRIPT_DIR / "darktable-cli-flatpak.sh"
RAW_EXTENSIONS = {".cr2", ".CR2"}


def log(msg):
		print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def convert_one(cr2: Path, tiff_dir: Path, bpp: int) -> tuple[Path, bool, str]:
		out = tiff_dir / f"{cr2.stem}.tif"
		if out.exists():
				return out, True, "skipped (exists)"
		log(f"converting {cr2.name}")
		proc = subprocess.run(
				[
						str(DARKTABLE_WRAPPER),
						str(cr2),
						str(out),
						"--core", "--conf", f"plugins/imageio/format/tiff/bpp={bpp}",
				],
				capture_output=True, text=True,
		)
		if proc.returncode != 0 or not out.exists():
				if out.exists():
						out.unlink()
				# Dump full stderr (and stdout as fallback) so the user can actually
				# diagnose failures instead of staring at "unknown error".
				err = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}, no output"
				return out, False, err
		return out, True, "ok"


def main():
		parser = argparse.ArgumentParser(
				description="Batch CR2 -> TIFF via flatpak darktable-cli.",
				formatter_class=argparse.RawDescriptionHelpFormatter,
				epilog=__doc__,
		)
		parser.add_argument("directory", nargs="?", default=".",
												help="Directory containing *.CR2 files (default: cwd)")
		parser.add_argument("--output", "-o", default=None,
												help="Output directory (default: <directory>/tiff)")
		parser.add_argument("--jobs", "-j", type=int, default=4,
												help="Parallel workers (default: 4)")
		parser.add_argument("--bpp", type=int, default=16, choices=[8, 16, 32],
												help="TIFF bits per channel (default: 16)")
		args = parser.parse_args()

		src = Path(args.directory).resolve()
		if not src.is_dir():
				print(f"error: not a directory: {src}", file=sys.stderr)
				return 2

		if not DARKTABLE_WRAPPER.is_file():
				print(f"error: wrapper not found: {DARKTABLE_WRAPPER}", file=sys.stderr)
				return 2
		if shutil.which("exiftool") is None:
				print("warning: exiftool not on PATH — EXIF copy in the wrapper will fail silently",
							file=sys.stderr)

		tiff_dir = Path(args.output).resolve() if args.output else src / "tiff"
		tiff_dir.mkdir(parents=True, exist_ok=True)

		cr2s = sorted(p for p in src.iterdir() if p.suffix in RAW_EXTENSIONS)
		if not cr2s:
				print(f"no CR2 files in {src}", file=sys.stderr)
				return 2

		log(f"{len(cr2s)} CR2 files -> {tiff_dir} (jobs={args.jobs}, bpp={args.bpp})")

		ok = 0
		failed: list[tuple[Path, str]] = []
		with ThreadPoolExecutor(max_workers=args.jobs) as pool:
				futures = [pool.submit(convert_one, c, tiff_dir, args.bpp) for c in cr2s]
				for fut in as_completed(futures):
						out, success, status = fut.result()
						if success:
								ok += 1
								log(f"  {out.name}: {status}")
						else:
								failed.append((out, status))
								log(f"  {out.name}: FAILED — {status}")

		log(f"done: {ok}/{len(cr2s)} ok")
		if failed:
				print("", file=sys.stderr)
				for out, status in failed:
						print(f"--- failed: {out.name}", file=sys.stderr)
						print(status, file=sys.stderr)
				return 1
		return 0


if __name__ == "__main__":
		sys.exit(main())
