#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyvips"]
# ///
"""
Convert a display-referred EXR panorama to a WebP deep-zoom tile pyramid.

Pipeline: multiply by 255, clip, cast to uchar, dzsave with WebP tiles.
No gamma curve is applied because darktable's default output profile is
sRGB, so values in the EXR are already sRGB-encoded in [0, 1].

If unsure whether the EXR is display-referred, run `exr_sanity.sh` first.
If max is far above 1.0 the EXR is scene-linear; tone-map upstream before
using this script or highlights will clip.

Output is DZI (Deep Zoom): a single <prefix>.dzi XML index plus a
<prefix>_files/ directory of WebP tiles. Loads in OpenSeadragon, Leaflet
with deep-zoom plugins, etc.

Usage:
  exr_to_webp_pyramid.py IN.exr OUT_PREFIX [--quality Q]
"""

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("input")
    ap.add_argument("output_prefix",
                    help="dzsave writes <prefix>.dzi + <prefix>_files/")
    ap.add_argument("--quality", "-Q", type=int, default=85,
                    help="WebP quality 0..100 (default 85)")
    args = ap.parse_args()

    in_path = Path(args.input).resolve()
    if not in_path.is_file():
        print(f"error: not a file: {in_path}", file=sys.stderr)
        return 2

    try:
        import pyvips
    except ImportError:
        print("error: pyvips not installed. Install with: pip install pyvips",
              file=sys.stderr)
        return 2

    img = pyvips.Image.new_from_file(str(in_path), access="sequential")
    print(f"input: {in_path}", file=sys.stderr)
    print(f"  size: {img.width} x {img.height}, {img.bands} bands, "
          f"format: {img.format}", file=sys.stderr)

    out = (img * 255).cast("uchar")
    print(f"writing pyramid to {args.output_prefix}.dzi "
          f"(WebP Q={args.quality})", file=sys.stderr)
    out.dzsave(args.output_prefix, suffix=f".webp[Q={args.quality}]")
    print("done", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
