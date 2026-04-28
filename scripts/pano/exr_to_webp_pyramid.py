#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyvips", "OpenEXR"]
# ///
"""
Convert an EXR panorama to a WebP deep-zoom tile pyramid.

Reads the hillview:encoding attribute to decide the pipeline:
	linear: apply forward sRGB OETF, scale 0..1 -> 0..255, cast.
	srgb:   values already sRGB-encoded; just scale and cast.

Untagged EXRs are rejected — silent guesses silently miscolor outputs.
Tag the source first (`exr_meta.py set FILE --encoding {linear,srgb}`)
or pass `--encoding` to override per-invocation.

Output is DZI (Deep Zoom): <prefix>.dzi + <prefix>_files/. Loads in
OpenSeadragon, Leaflet with deep-zoom plugins, etc.

Usage:
	exr_to_webp_pyramid.py IN.exr OUT_PREFIX [--quality Q]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exr_meta


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
		ap.add_argument("--encoding", choices=("linear", "srgb"), default=None,
										help="Override the hillview:encoding attribute (otherwise "
												 "read from the EXR; missing tag is rejected)")
		args = ap.parse_args()

		in_path = Path(args.input).resolve()
		if not in_path.is_file():
				print(f"error: not a file: {in_path}", file=sys.stderr)
				return 2

		if args.encoding:
				encoding = args.encoding
		else:
				encoding = exr_meta.read_encoding(str(in_path))
				if encoding is None:
						print(
								f"error: {in_path.name} has no hillview:encoding attribute.\n"
								f"  tag the file:    exr_meta.py set FILE --encoding {{linear,srgb}}\n"
								f"  or override:     --encoding {{linear,srgb}}",
								file=sys.stderr,
						)
						return 2
				if encoding not in ("linear", "srgb"):
						print(f"error: unknown hillview:encoding={encoding!r} in {in_path.name}",
									file=sys.stderr)
						return 2

		import pyvips
		img = pyvips.Image.new_from_file(str(in_path), access="sequential")
		print(f"input:    {in_path}", file=sys.stderr)
		print(f"  size:   {img.width} x {img.height}, {img.bands} bands, "
					f"{img.format}", file=sys.stderr)
		print(f"  encoding: {encoding}", file=sys.stderr)

		# Drop alpha if present. WebP supports it but for a panorama
		# pyramid it just doubles the per-tile size for no visual gain
		# (alpha is ~uniform after pano_modify --crop=AUTO trims to content).
		if img.bands > 3:
				print(f"  dropping alpha: {img.bands} -> 3 bands", file=sys.stderr)
				img = img[:3]

		if encoding == "linear":
				# Forward sRGB OETF, piecewise:
				#   V_srgb = 12.92 * V_lin                            if V_lin <= 0.0031308
				#   V_srgb = 1.055 * V_lin ^ (1/2.4) - 0.055          otherwise
				low = img * 12.92
				high = (img ** (1.0 / 2.4)) * 1.055 - 0.055
				mask = img > 0.0031308
				display = mask.ifthenelse(high, low)
		else:
				# Already sRGB-encoded, just scale.
				display = img

		out = (display * 255).cast("uchar")
		print(f"writing pyramid to {args.output_prefix}.dzi "
					f"(WebP Q={args.quality})", file=sys.stderr)
		out.dzsave(args.output_prefix, suffix=f".webp[Q={args.quality}]")
		print("done", file=sys.stderr)
		return 0


if __name__ == "__main__":
		sys.exit(main())
