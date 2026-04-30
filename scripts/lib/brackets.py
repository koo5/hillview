#!/usr/bin/env python3
"""Canon AEB bracket-stack detection from CR2 EXIF.

API:
  detect_bracket_groups(cr2s)         -> list[list[Path]]
  detect_uniform_bracket_count(cr2s)  -> int
  print_groups(cr2s, stream=stdout)   -> list[list[Path]]   (also prints)

CLI:
  brackets.py [CR2 ...]               # default: all *.CR2 in cwd

Both callers (raw.py auto-fuse, pano/pipeline.py uniform check) use the
same exiftool batch read; the distinction is per-stack vs. whole-batch
detection.

Conservative on parse: any irregularity collapses to "no brackets" rather
than guessing — a wrong autodetect groups unrelated frames downstream.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

_SHOT_COUNT_RE = re.compile(r'(\d+)\s*shots?$')


def _read_aeb_metadata(cr2s: list[Path]) -> list[Optional[tuple[str, str]]]:
	"""Read (AEBShotCount, ExposureTime) per frame in one exiftool call.

	Entry is None for any frame whose row was malformed; whole list is
	None-filled if exiftool itself failed (no exiftool, file unreadable).
	"""
	if not cr2s:
		return []
	try:
		out = subprocess.check_output(
			["exiftool", "-T", "-AEBShotCount", "-ExposureTime",
			 *map(str, cr2s)],
			text=True, stderr=subprocess.DEVNULL,
		)
	except (subprocess.CalledProcessError, FileNotFoundError):
		return [None] * len(cr2s)

	rows = [line.split('\t') for line in out.splitlines()]
	if len(rows) != len(cr2s):
		return [None] * len(cr2s)
	return [
		(r[0].strip(), r[1].strip()) if len(r) == 2 else None
		for r in rows
	]


def _parse_shot_count(value: str) -> int:
	"""'3 shots' -> 3. Out-of-range or unparseable -> 1."""
	m = _SHOT_COUNT_RE.match(value)
	if not m:
		return 1
	n = int(m.group(1))
	return n if 2 <= n <= 9 else 1


def detect_bracket_groups(cr2s: list[Path]) -> list[list[Path]]:
	"""Partition `cr2s` into bracket groups using per-frame AEBShotCount.

	Returns a list of groups in input order. Each group has length 1
	(non-bracketed single shot) or N in 2..9 (bracket stack of N).

	A run of N consecutive frames is committed as a stack iff:
	  - All N frames report AEBShotCount = N.
	  - The N ExposureTime values within the run are all distinct
	    (sanity check that AEB actually fired vs. the user just leaving
	    the AEB setting on without taking a real bracket).

	Anything else collapses to single-frame groups.
	"""
	if not cr2s:
		return []
	metadata = _read_aeb_metadata(cr2s)

	groups: list[list[Path]] = []
	i = 0
	while i < len(cr2s):
		n = _parse_shot_count(metadata[i][0]) if metadata[i] else 1
		if n >= 2 and i + n <= len(cr2s):
			same_count = all(
				metadata[i + j] is not None
				and _parse_shot_count(metadata[i + j][0]) == n
				for j in range(n)
			)
			distinct_exposures = (
				same_count and
				len({metadata[i + j][1] for j in range(n)}) == n
			)
			if distinct_exposures:
				groups.append(list(cr2s[i:i + n]))
				i += n
				continue
		groups.append([cr2s[i]])
		i += 1
	return groups


def detect_uniform_bracket_count(cr2s: list[Path]) -> int:
	"""Pano-style: return N (2..9) if the whole batch is one big AEB session,
	else 1.

	Stricter than `detect_bracket_groups` on purpose — pano commits to a
	single global N for downstream frame grouping. Requires:
	  - At least 6 frames (so a wrong autodetect can't fit on a tiny set).
	  - First frame's AEBShotCount parses to 2..9.
	  - ExposureTime cycles across the whole batch with period N
	    (frame i and i+N must match — same stack position, different stack).
	"""
	if len(cr2s) < 6:
		return 1
	metadata = _read_aeb_metadata(cr2s)
	if any(m is None for m in metadata):
		return 1

	n = _parse_shot_count(metadata[0][0])
	if n < 2:
		return 1

	exposures = [m[1] for m in metadata]
	if not all(exposures[i] == exposures[i + n]
	           for i in range(len(exposures) - n)):
		return 1
	return n


def print_groups(cr2s: list[Path], stream=sys.stdout) -> list[list[Path]]:
	"""Detect groups, print a per-frame breakdown, return the groups.

	Format (one line per frame):

	    <name>   [G]   <pos> *   <exposure>   → <stem>_fused

	Where:
	  - [G] is the group index (1-based; omitted for singles).
	  - <pos> is "p/N" within the group, or "single".
	  - "*" marks the middle frame (the one whose stem becomes the
	    fused output's stem, matching what fuse_brackets in raw.py uses).
	  - "→ <stem>_fused" annotates only on the middle of brackets.

	Returns the same groups list as detect_bracket_groups.
	"""
	groups = detect_bracket_groups(cr2s)
	metadata = _read_aeb_metadata(cr2s)
	idx = {c: i for i, c in enumerate(cr2s)}

	singles = sum(1 for g in groups if len(g) == 1)
	brackets = [g for g in groups if len(g) >= 2]
	if brackets:
		size_summary = ", ".join(
			f"{sum(1 for g in brackets if len(g) == n)}×{n}"
			for n in sorted({len(g) for g in brackets})
		)
		bracket_phrase = f"{len(brackets)} bracket stack(s) [{size_summary}]"
	else:
		bracket_phrase = "0 bracket stacks"
	print(
		f"{len(cr2s)} frame(s) in {len(groups)} group(s): "
		f"{singles} single(s), {bracket_phrase}",
		file=stream, flush=True,
	)

	if not cr2s:
		return groups
	name_w = max(len(c.name) for c in cr2s)

	for group_idx, group in enumerate(groups, start=1):
		n = len(group)
		middle = n // 2
		for pos, cr2 in enumerate(group):
			exp = metadata[idx[cr2]][1] if metadata[idx[cr2]] else "?"
			if n == 1:
				gid, role = "  -", "single   "
			else:
				gid = f"[{group_idx}]"
				role = f"{pos+1}/{n}      " if pos != middle else f"{pos+1}/{n} *    "
			tail = f"   → {cr2.stem}_fused" if (n >= 2 and pos == middle) else ""
			print(
				f"  {cr2.name:<{name_w}}  {gid:>5}  {role}  {exp:>10}{tail}",
				file=stream, flush=True,
			)
	return groups


def _main() -> int:
	import argparse
	p = argparse.ArgumentParser(
		description="Detect Canon AEB bracket stacks among CR2 files "
		            "and print a per-frame breakdown.",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog=__doc__,
	)
	p.add_argument("cr2s", nargs="*", type=Path,
	               help="CR2 files (default: all *.CR2 in cwd)")
	args = p.parse_args()

	cr2s = sorted(args.cr2s) if args.cr2s else sorted(Path(".").glob("*.CR2"))
	if not cr2s:
		print("no CR2 files", file=sys.stderr)
		return 2
	print_groups(cr2s)
	return 0


if __name__ == "__main__":
	sys.exit(_main())
