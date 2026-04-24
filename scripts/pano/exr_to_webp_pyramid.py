#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyvips"]
# ///
"""
Convert an EXR panorama to a WebP deep-zoom tile pyramid.

Reads the hillview:encoding attribute to decide the pipeline:
	linear  (preferred): apply forward sRGB OETF, scale 0..1 -> 0..255, cast.
	srgb    (legacy):    values already sRGB-encoded; just scale and cast.

If the tag is missing, defaults to 'srgb' per the Hillview convention
documented in exr_meta.py (hobbyist panorama pipelines produce
display-referred EXRs).

Output is DZI (Deep Zoom): <prefix>.dzi + <prefix>_files/. Loads in
OpenSeadragon, Leaflet with deep-zoom plugins, etc.

Usage:
	exr_to_webp_pyramid.py IN.exr OUT_PREFIX [--quality Q]
"""

import argparse
import subprocess
import sys
from pathlib import Path

EXR_META = Path(__file__).resolve().parent / "exr_meta.py"


def read_encoding(path: Path) -> str:
		"""Return 'linear' / 'srgb', defaulting to 'srgb' when tag is absent."""
		try:
				out = subprocess.check_output([str(EXR_META), "show", str(path)],
																			text=True, stderr=subprocess.STDOUT)
		except (subprocess.CalledProcessError, FileNotFoundError):
				return "srgb"
		for line in out.splitlines():
				if "hillview:encoding" in line and "=" in line:
						value = line.split("=", 1)[1].strip().strip("'\"")
						if value in ("linear", "srgb"):
								return value
		return "srgb"


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
												 "read from the EXR, falling back to 'srgb')")
		args = ap.parse_args()

		in_path = Path(args.input).resolve()
		if not in_path.is_file():
				print(f"error: not a file: {in_path}", file=sys.stderr)
				return 2

		encoding = args.encoding or read_encoding(in_path)

		import pyvips
		img = pyvips.Image.new_from_file(str(in_path), access="sequential")
		print(f"input:    {in_path}", file=sys.stderr)
		print(f"  size:   {img.width} x {img.height}, {img.bands} bands, "
					f"{img.format}", file=sys.stderr)
		print(f"  encoding: {encoding}", file=sys.stderr)

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
