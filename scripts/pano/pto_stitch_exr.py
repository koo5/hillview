#!/usr/bin/env python3
"""
Stitch a Hugin panorama to OpenEXR, preserving warped intermediates.

Runs nona (warp) and enblend (blend) as two explicit steps. nona produces
one layer per input image, in whatever format the PTO's p-line specifies
(typically TIFF_m -> .tif). enblend reads those layers and writes the
final panorama to <prefix>.exr — the EXR format comes from the --output
filename, so the PTO never needs editing.

Because the steps are separate and we never delete the layers, a failed
blend is cheap to retry: `--reblend-only` skips the warp step.

Usage:
  pto_stitch_exr.py PTO --prefix NAME [--threads N] [--reblend-only]
                        [--nona-cmd CMD] [--enblend-cmd CMD]

Flatpak Hugin example (binary name varies; check `flatpak list`):
  --nona-cmd    'flatpak run --command=nona    net.sourceforge.Hugin'
  --enblend-cmd 'flatpak run --command=enblend net.sourceforge.Hugin'

Clean up layers once happy:  rm <prefix>[0-9]*.<ext>
"""

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

LAYER_EXT_CANDIDATES = ("tif", "tiff", "exr", "png")


def run(cmd: list[str]) -> int:
    print(f"$ {' '.join(shlex.quote(c) for c in cmd)}", file=sys.stderr, flush=True)
    return subprocess.call(cmd)


def find_layers(workdir: Path, prefix: str) -> tuple[list[Path], str | None]:
    for ext in LAYER_EXT_CANDIDATES:
        hits = sorted(workdir.glob(f"{prefix}[0-9]*.{ext}"))
        if hits:
            return hits, ext
    return [], None


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("pto")
    ap.add_argument("--prefix", required=True,
                    help="Panorama prefix: warped layers = <prefix>NNNN.<ext>, "
                         "final = <prefix>.exr")
    ap.add_argument("--threads", type=int, default=None,
                    help="Thread count for enblend")
    ap.add_argument("--reblend-only", action="store_true",
                    help="Skip warp; just run enblend on existing layers.")
    ap.add_argument("--nona-cmd", default="nona",
                    help="nona command line (quoted if multi-token). Default: nona")
    ap.add_argument("--enblend-cmd", default="enblend",
                    help="enblend command line. Default: enblend")
    args = ap.parse_args()

    pto = Path(args.pto).resolve()
    if not pto.is_file():
        print(f"error: not a file: {pto}", file=sys.stderr)
        return 2

    workdir = pto.parent
    os.chdir(workdir)

    nona_cmd = shlex.split(args.nona_cmd)
    enblend_cmd = shlex.split(args.enblend_cmd)

    if not args.reblend_only:
        rc = run(nona_cmd + ["-o", args.prefix, str(pto)])
        if rc != 0:
            print("nona failed; stopping", file=sys.stderr)
            return rc

    layers, ext = find_layers(workdir, args.prefix)
    if not layers:
        print(f"error: no layers at {workdir}/{args.prefix}[0-9]*.<tif|exr|png>",
              file=sys.stderr)
        return 2
    print(f"\n{len(layers)} {ext} layers ready; starting enblend", file=sys.stderr)

    out = enblend_cmd + ["--output", f"{args.prefix}.exr"]
    if args.threads is not None:
        out.append(f"--threads={args.threads}")
    out += [p.name for p in layers]
    rc = run(out)

    final = workdir / f"{args.prefix}.exr"
    if rc != 0:
        print(f"\nenblend failed (rc={rc}); {len(layers)} layers preserved.",
              file=sys.stderr)
        print(f"retry blend only:", file=sys.stderr)
        print(f"  pto_stitch_exr.py {pto.name} --prefix {args.prefix} --reblend-only",
              file=sys.stderr)
        return rc

    print(f"\ndone: {final}", file=sys.stderr)
    print(f"cleanup when satisfied:  rm {args.prefix}[0-9]*.{ext}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
