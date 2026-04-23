#!/usr/bin/env python3
"""
Rewrite image yaw/pitch/roll in a Hugin .pto to a clean horizontal strip.

When control points include parallax-heavy foreground, Hugin's optimizer can
drift images into nonsense positions (pitches of ~60° on what should be a
horizontal pano). This script discards the current r/p/y on every image line
and replaces them with a baseline assuming a single horizontal row at fixed
yaw spacing. Everything else — FOV, lens params, exposure, control points,
optimization flags — is kept verbatim.

Usage:
  pto_horizontal_baseline.py IN.pto -o OUT.pto (--yaw-step DEG | --yaw-span DEG)
                             [--start-yaw DEG] [--pitch DEG] [--roll DEG]
  pto_horizontal_baseline.py IN.pto --in-place ...    # writes IN.pto.bak

With --yaw-span the step is span/(N-1). Without --start-yaw the strip is
centered (start = -(N-1)*step/2).
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

# r, p, y as standalone attributes (not "Ra0", "Eev", "Tpy0" etc — those are
# safe because r/p/y are never at a word boundary in those strings).
RE_ROLL = re.compile(r'\br-?[\d.]+')
RE_PITCH = re.compile(r'\bp-?[\d.]+')
RE_YAW = re.compile(r'\by-?[\d.]+')
# v<float> on an image line = HFOV. "v=<N>" means linked to image N.
RE_HFOV = re.compile(r'\bv(-?[\d.]+)\b')


def read_hfov(text: str) -> float | None:
    """HFOV of the first image line, resolving `v=N` links to image N."""
    i_lines = [ln for ln in text.splitlines() if ln.startswith("i ")]
    if not i_lines:
        return None
    for target in (0, *range(len(i_lines))):
        m = RE_HFOV.search(i_lines[target])
        if m:
            return float(m.group(1))
    return None


def fmt(v: float) -> str:
    return f"{v:.6f}".rstrip("0").rstrip(".") or "0"


def rewrite(text: str, start_yaw: float, step: float, pitch: float, roll: float) -> tuple[str, int]:
    out_lines = []
    idx = 0
    for line in text.splitlines(keepends=True):
        if not line.startswith("i "):
            out_lines.append(line)
            continue
        yaw = start_yaw + idx * step
        line = RE_ROLL.sub(f"r{fmt(roll)}", line, count=1)
        line = RE_PITCH.sub(f"p{fmt(pitch)}", line, count=1)
        line = RE_YAW.sub(f"y{fmt(yaw)}", line, count=1)
        out_lines.append(line)
        idx += 1
    return "".join(out_lines), idx


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", help="Input .pto")
    parser.add_argument("-o", "--output", help="Output .pto (default: print to stdout unless --in-place)")
    parser.add_argument("--in-place", action="store_true",
                        help="Overwrite input (backup to <input>.bak)")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--yaw-step", type=float, help="Yaw spacing between consecutive images (deg)")
    grp.add_argument("--yaw-span", type=float, help="Total yaw range across all images (deg); step = span/(N-1)")
    grp.add_argument("--overlap", type=float,
                     help="Percent overlap between adjacent images; step = HFOV * (1 - overlap/100). "
                          "HFOV is read from the first image line in the .pto.")
    parser.add_argument("--start-yaw", type=float, default=None,
                        help="Yaw of first image (deg). Default: centered strip.")
    parser.add_argument("--pitch", type=float, default=0.0, help="Pitch for all images (deg, default 0)")
    parser.add_argument("--roll", type=float, default=0.0, help="Roll for all images (deg, default 0)")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.is_file():
        print(f"error: not a file: {in_path}", file=sys.stderr)
        return 2
    text = in_path.read_text()

    n = sum(1 for line in text.splitlines() if line.startswith("i "))
    if n == 0:
        print("error: no image lines found", file=sys.stderr)
        return 2

    if args.yaw_step is not None:
        step = args.yaw_step
    elif args.yaw_span is not None:
        step = args.yaw_span / (n - 1) if n > 1 else 0.0
    else:
        hfov = read_hfov(text)
        if hfov is None:
            print("error: --overlap given but HFOV not found on first image line", file=sys.stderr)
            return 2
        step = hfov * (1.0 - args.overlap / 100.0)
        print(f"HFOV={hfov:.4f}°, overlap={args.overlap}% -> step={step:.4f}°", file=sys.stderr)
    start = args.start_yaw if args.start_yaw is not None else -(n - 1) * step / 2.0

    new_text, count = rewrite(text, start, step, args.pitch, args.roll)
    assert count == n

    print(f"{n} images, step={step:.4f}°, start={start:.4f}°, "
          f"end={start + (n - 1) * step:.4f}°, pitch={args.pitch}, roll={args.roll}",
          file=sys.stderr)

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
