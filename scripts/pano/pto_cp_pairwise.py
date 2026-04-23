#!/usr/bin/env python3
"""
Drop control points between non-adjacent images in a linear Hugin .pto.

Panorama CP detection produces many false matches between distant frames
with repeating textures (cloud-vs-cloud, foliage-vs-foliage). Assuming
images in the PTO are in shooting order along a strip, keeping only CPs
between frames within N positions of each other kills those false
matches while preserving legitimate inter-frame overlap.

Usage:
  pto_cp_pairwise.py IN.pto -o OUT.pto [--max-skip N]
  pto_cp_pairwise.py IN.pto --in-place [--max-skip N]

--max-skip:
  0 (default) keeps only adjacent pairs (|i-j| == 1).
  1 allows one skipped image (|i-j| <= 2). Use if your overlap is >50%
    and adjacent+2 frames genuinely share content.
  Higher values for multi-row panos where non-linear pairing is real.
"""

import argparse
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

RE_CP_PAIR = re.compile(r'^c\s+n(\d+)\s+N(\d+)\b')


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.add_argument("--in-place", action="store_true")
    p.add_argument("--max-skip", type=int, default=0,
                   help="Keep CPs where |i-j| <= max_skip + 1. Default 0.")
    args = p.parse_args()

    in_path = Path(args.input)
    text = in_path.read_text()
    lines = text.splitlines(keepends=True)

    n_images = sum(1 for ln in lines if ln.startswith("i "))
    max_gap = args.max_skip + 1

    drop: set[int] = set()
    total = 0
    for li, line in enumerate(lines):
        if not line.startswith("c "):
            continue
        m = RE_CP_PAIR.match(line)
        if not m:
            continue
        total += 1
        if abs(int(m.group(1)) - int(m.group(2))) > max_gap:
            drop.add(li)

    kept = total - len(drop)
    print(f"--max-skip {args.max_skip} (|i-j| <= {max_gap}): "
          f"{kept}/{total} CPs kept across {n_images} images",
          file=sys.stderr)

    # Sanity: count surviving CPs per adjacent pair.
    pair_count: dict[tuple[int, int], int] = defaultdict(int)
    for li, line in enumerate(lines):
        if li in drop or not line.startswith("c "):
            continue
        m = RE_CP_PAIR.match(line)
        if m:
            a, b = sorted((int(m.group(1)), int(m.group(2))))
            pair_count[(a, b)] += 1
    weak_adj = [(i, pair_count.get((i, i + 1), 0))
                for i in range(n_images - 1)
                if pair_count.get((i, i + 1), 0) < 2]
    if weak_adj:
        print(f"warning: {len(weak_adj)} adjacent pair(s) with <2 CPs "
              f"(harder to optimize): "
              + ", ".join(f"{i}->{i+1}={c}" for i, c in weak_adj[:10])
              + (" ..." if len(weak_adj) > 10 else ""),
              file=sys.stderr)

    new_text = "".join(ln for li, ln in enumerate(lines) if li not in drop)

    if args.in_place:
        backup = in_path.with_suffix(in_path.suffix + ".bak")
        if not backup.exists():
            shutil.copy2(in_path, backup)
        in_path.write_text(new_text)
        print(f"wrote {in_path} (backup: {backup})", file=sys.stderr)
    elif args.output:
        Path(args.output).write_text(new_text)
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(new_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
