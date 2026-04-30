#!/usr/bin/env python3
"""Group CR2s into panoX/ dirs based on star-rating dividers.

Walks *.CR2 in the working dir (or --dir) in name order and reads the
Rating EXIF/XMP tag (sidecar `<stem>.CR2.xmp` is preferred when it exists,
which is the darktable convention). The conventions:

  - rating 1  ->  this frame is the LAST shot of a *non-pano* series.
                  Discard the run; nothing is copied. The frame itself
                  also gets discarded (it's still part of the run).
  - rating 2  ->  this frame is the LAST shot of a *pano* series.
                  cp --reflink the run (everything since the previous
                  1-or-2-star, up to and including this frame) into
                  the next free pano<N>/ dir.

Frames before the very first divider are part of the first series and
get the same treatment based on what divider eventually closes them.
Frames after the final divider are dangling — nothing is done with them.

Each copied CR2 brings along any sibling file sharing its stem
(*.xmp / *.CR2.xmp / *.pp3 / *.dop / etc.) so darktable/RawTherapee
edits travel with the raw.

Usage:
  sort.py [--dir DIR] [--dry-run] [--prefix pano]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def log(msg: str) -> None:
	print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def _read_ratings(cr2s: list[Path]) -> list[int]:
	"""Return the Rating tag per CR2, in input order. Missing/unparseable -> 0.

	Reads from the darktable-style sidecar `<stem>.CR2.xmp` when it exists
	(that's where edits and ratings actually live for darktable users);
	otherwise falls back to the CR2's embedded XMP/MakerNotes. One batched
	exiftool call.
	"""
	if not cr2s:
		return []

	targets: list[Path] = []
	for c in cr2s:
		sidecar = c.parent / f"{c.name}.xmp"   # FOO.CR2.xmp
		alt_sidecar = c.with_suffix(".xmp")    # FOO.xmp
		if sidecar.exists():
			targets.append(sidecar)
		elif alt_sidecar.exists():
			targets.append(alt_sidecar)
		else:
			targets.append(c)

	out = subprocess.check_output(
		["exiftool", "-T", "-Rating", *map(str, targets)],
		text=True, stderr=subprocess.DEVNULL,
	)
	rows = out.splitlines()
	if len(rows) != len(cr2s):
		raise RuntimeError(
			f"exiftool returned {len(rows)} rows for {len(cr2s)} files; aborting"
		)

	def parse(s: str) -> int:
		s = s.strip()
		try:
			return int(s)
		except ValueError:
			return 0

	return [parse(r) for r in rows]


def _next_pano_dir(parent: Path, prefix: str) -> Path:
	"""Return parent/{prefix}{N} for the smallest N>=1 that doesn't exist yet."""
	n = 1
	while True:
		d = parent / f"{prefix}{n}"
		if not d.exists():
			return d
		n += 1


def _siblings_of(cr2: Path) -> list[Path]:
	"""Files in the same dir that travel with this CR2.

	Matches both common sidecar shapes:
	  - FOO.CR2.xmp  (darktable: full filename + .xmp)
	  - FOO.xmp / FOO.dop / FOO.pp3 / ...  (stem + sidecar ext)

	Excludes the CR2 itself and any directories.
	"""
	out = []
	prefix_with_dot = cr2.name + "."  # for FOO.CR2.* matches
	for f in cr2.parent.iterdir():
		if not f.is_file() or f == cr2:
			continue
		if f.stem == cr2.stem or f.name.startswith(prefix_with_dot):
			out.append(f)
	return out


def _cp_reflink(src: Path, dst: Path, dry_run: bool) -> None:
	if dry_run:
		log(f"  would cp --reflink {src.name} -> {dst}")
		return
	subprocess.run(
		["cp", "--reflink=auto", str(src), str(dst)],
		check=True,
	)


def main() -> int:
	parser = argparse.ArgumentParser(
		description=__doc__,
		formatter_class=argparse.RawDescriptionHelpFormatter,
	)
	parser.add_argument("--dir", default=".",
	                    help="Directory to scan for CR2s (default: cwd)")
	parser.add_argument("--prefix", default="pano",
	                    help="Output dir name prefix (default: pano)")
	parser.add_argument("--dry-run", action="store_true",
	                    help="Plan only; don't create dirs or copy files")
	args = parser.parse_args()

	src = Path(args.dir).resolve()
	if not src.is_dir():
		print(f"error: not a directory: {src}", file=sys.stderr)
		return 2
	if shutil.which("exiftool") is None:
		print("error: exiftool not on PATH", file=sys.stderr)
		return 2

	cr2s = sorted(p for p in src.iterdir() if p.suffix == ".CR2")
	if not cr2s:
		print(f"no CR2 files in {src}", file=sys.stderr)
		return 2

	log(f"reading ratings for {len(cr2s)} CR2 files")
	ratings = _read_ratings(cr2s)
	starred = sum(1 for r in ratings if r in (1, 2))
	log(f"found {starred} divider(s): "
	    f"{sum(1 for r in ratings if r == 1)}× 1-star, "
	    f"{sum(1 for r in ratings if r == 2)}× 2-star")

	last_divider = -1   # index of last 1- or 2-star frame
	created = 0

	for i, (cr2, r) in enumerate(zip(cr2s, ratings)):
		if r == 1:
			run = cr2s[last_divider + 1: i + 1]
			log(f"{cr2.name}: 1-star, dropping run of {len(run)} frame(s)")
			last_divider = i
		elif r == 2:
			run = cr2s[last_divider + 1: i + 1]
			pano_dir = _next_pano_dir(src, args.prefix)
			log(f"{cr2.name}: 2-star, pano run of {len(run)} frame(s) -> {pano_dir.name}/")
			if not args.dry_run:
				pano_dir.mkdir()
			for f in run:
				_cp_reflink(f, pano_dir / f.name, args.dry_run)
				for s in _siblings_of(f):
					_cp_reflink(s, pano_dir / s.name, args.dry_run)
			last_divider = i
			created += 1

	tail = len(cr2s) - 1 - last_divider
	if tail > 0:
		log(f"{tail} frame(s) after the last divider were left in place")
	log(f"done: created {created} pano dir(s)" + (" (dry run)" if args.dry_run else ""))
	return 0


if __name__ == "__main__":
	sys.exit(main())
