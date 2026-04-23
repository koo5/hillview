#!/usr/bin/env python3
"""
Keep only the topmost control points per image side in a Hugin .pto.

Per image, split CPs by side of the horizontal midpoint (L/R). For each
(image, side), keep the K CPs with the smallest pixel-y (closest to the
top of the frame). A CP survives if it is topmost-K for at least one of
its two image endpoints.

Useful as an aggressive last-resort reducer when lighter CP cleaning
(celeste, pairwise adjacency, bottom-nuke) still leaves a CP graph the
optimizer can't resolve. Prefer the lighter filters first: this one
throws away a lot of legitimate signal and leaves the horizon nearly
collinear, which weakens pitch constraint.

Usage:
  pto_cp_topmost.py IN.pto -o OUT.pto --per-side K
  pto_cp_topmost.py IN.pto --in-place --per-side K
"""

import argparse
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

RE_W = re.compile(r'\bw(\d+)\b')
RE_CP = re.compile(
    r'^c\s+n(\d+)\s+N(\d+)\s+'
    r'x(-?[\d.]+)\s+y(-?[\d.]+)\s+'
    r'X(-?[\d.]+)\s+Y(-?[\d.]+)\s+'
    r't(\d+)'
)


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.add_argument("--in-place", action="store_true")
    p.add_argument("--per-side", type=int, required=True,
                   help="Keep K topmost CPs per (image, side).")
    args = p.parse_args()

    in_path = Path(args.input)
    text = in_path.read_text()
    lines = text.splitlines(keepends=True)

    widths: list[int] = []
    cps: list[tuple[int, int, float, float, float, float, int]] = []
    cp_line_idx: list[int] = []

    for li, line in enumerate(lines):
        if line.startswith("i "):
            m = RE_W.search(line)
            if not m:
                print(f"error: image line {li+1} has no width", file=sys.stderr)
                return 2
            widths.append(int(m.group(1)))
        elif line.startswith("c "):
            m = RE_CP.match(line)
            if not m:
                continue
            n, N = int(m.group(1)), int(m.group(2))
            x, y, X, Y = map(float, m.group(3, 4, 5, 6))
            t = int(m.group(7))
            cps.append((n, N, x, y, X, Y, t))
            cp_line_idx.append(li)

    if not cps:
        print("no control points to filter", file=sys.stderr)
        return 2

    bucket: dict[tuple[int, str], list[tuple[float, int]]] = defaultdict(list)
    for idx, (n, N, x, y, X, Y, _t) in enumerate(cps):
        bucket[(n, "L" if x < widths[n] / 2.0 else "R")].append((y, idx))
        bucket[(N, "L" if X < widths[N] / 2.0 else "R")].append((Y, idx))

    keep: set[int] = set()
    for entries in bucket.values():
        entries.sort()
        for _y, idx in entries[: args.per_side]:
            keep.add(idx)

    per_image: dict[int, int] = defaultdict(int)
    for idx in keep:
        per_image[cps[idx][0]] += 1
        per_image[cps[idx][1]] += 1

    print(f"--per-side {args.per_side}: {len(keep)}/{len(cps)} CPs kept",
          file=sys.stderr)
    weak = [img for img, cnt in per_image.items() if cnt < 2]
    if weak:
        print(f"warning: {len(weak)} image(s) with <2 CPs", file=sys.stderr)
    missing = [i for i in range(len(widths)) if i not in per_image]
    if missing:
        print(f"warning: {len(missing)} image(s) with 0 CPs", file=sys.stderr)

    drop = {cp_line_idx[i] for i in range(len(cps)) if i not in keep}
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
