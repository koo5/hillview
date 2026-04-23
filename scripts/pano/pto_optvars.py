#!/usr/bin/env python3
"""
Rewrite the optimizer variable block ("v" lines) in a Hugin .pto.

Replaces the existing block with a fresh one that frees only the variables
listed in --free, for every image except --anchor (default 0, which stays
locked as the coordinate origin).

Usage:
  pto_optvars.py IN.pto -o OUT.pto --free y,p [--anchor 0]
  pto_optvars.py IN.pto --in-place --free y

Common recipes:
  --free y            yaw only (safest when baseline is trustworthy)
  --free y,p          yaw + pitch
  --free y,p,r        positions (yaw, pitch, roll)
  --free y,p,r,Eev    positions + per-image exposure

Per-image photometric/lens params (Ra..Re, Vb..Vy, v, a, b, c, d, e, g, t)
work too — they're just emitted verbatim. If your i-lines link them to
image 0 via `=0`, also exclude image 0 from the anchor if you want them
to actually vary.
"""

import argparse
import shutil
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.add_argument("--in-place", action="store_true")
    p.add_argument("--free", required=True,
                   help="Comma-separated variable names, e.g. y,p or y,p,r,Eev")
    p.add_argument("--anchor", type=int, default=0,
                   help="Image index to lock entirely (default 0)")
    args = p.parse_args()

    inp = Path(args.input)
    lines = inp.read_text().splitlines(keepends=True)

    n = sum(1 for ln in lines if ln.startswith("i "))
    if n == 0:
        print("error: no image lines", file=sys.stderr)
        return 2
    if not (0 <= args.anchor < n):
        print(f"error: --anchor {args.anchor} out of range (0..{n - 1})", file=sys.stderr)
        return 2

    vars_list = [v.strip() for v in args.free.split(",") if v.strip()]
    if not vars_list:
        print("error: --free produced an empty list", file=sys.stderr)
        return 2

    def is_v_line(ln: str) -> bool:
        # A v block line: "v <something>\n" or bare "v\n" terminator.
        s = ln.rstrip("\n").rstrip()
        return s == "v" or s.startswith("v ")

    v_positions = [i for i, ln in enumerate(lines) if is_v_line(ln)]
    if v_positions:
        insert_at_orig = v_positions[0]
    else:
        insert_at_orig = next(
            (i for i, ln in enumerate(lines)
             if ln.startswith("c ") or ln.lower().startswith("# control points")),
            len(lines),
        )

    new_block = [f"v {var}{i}\n"
                 for var in vars_list
                 for i in range(n) if i != args.anchor]
    new_block.append("v\n")

    kept = [ln for ln in lines if not is_v_line(ln)]
    insert_at = sum(1 for i in range(insert_at_orig) if not is_v_line(lines[i]))
    out = kept[:insert_at] + new_block + kept[insert_at:]
    new_text = "".join(out)

    free_count = (n - 1) * len(vars_list)
    print(f"{free_count} optimization variables freed "
          f"({', '.join(vars_list)} × {n - 1} images; anchor=i{args.anchor})",
          file=sys.stderr)

    if args.in_place:
        backup = inp.with_suffix(inp.suffix + ".bak")
        if not backup.exists():
            shutil.copy2(inp, backup)
        inp.write_text(new_text)
        print(f"wrote {inp} (backup: {backup})", file=sys.stderr)
    elif args.output:
        Path(args.output).write_text(new_text)
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(new_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
