#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyvips", "OpenEXR"]
# ///
"""
Resize and split an EXR panorama into a strip of Instagram carousel tiles.

A carousel post takes up to 10 images. 4:5 portrait (1080x1350) maximises
on-screen area, so it's the default tile shape; posting a panorama as N
such tiles gives a sliding-strip effect when viewers swipe.

Reads hillview:encoding (linear/srgb) and applies the sRGB OETF the same
way exr_to_webp_pyramid.py does. Untagged EXRs are rejected; override
with --encoding.

Fits the source by height, picks the largest N that fully fits along the
width (capped at --max-tiles), then center-crops the strip to N*tile_w.
Excess width on either side is discarded — no upscaling beyond the height
fit, no squashing.

Output:
	<prefix>_01.jpg .. <prefix>_NN.jpg

Usage:
	exr_to_instagram_tiles.py IN.exr OUT_PREFIX
		[--tile-size WxH]      default 1080x1350 (Instagram 4:5 portrait)
		[--max-tiles N]        default 10 (carousel limit)
		[--quality Q]          default 90
		[--encoding linear|srgb]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exr_meta


def parse_size(s: str) -> tuple[int, int]:
		w, sep, h = s.lower().partition("x")
		if not sep:
				raise ValueError(f"expected WxH, got {s!r}")
		return int(w), int(h)


def main() -> int:
		ap = argparse.ArgumentParser(
				description=__doc__,
				formatter_class=argparse.RawDescriptionHelpFormatter,
		)
		ap.add_argument("input")
		ap.add_argument("output_prefix",
										help="tiles named <prefix>_NN.jpg")
		ap.add_argument("--tile-size", default="1080x1350",
										help="per-tile WxH (default 1080x1350, Instagram 4:5)")
		ap.add_argument("--max-tiles", type=int, default=10,
										help="hard cap on tile count (default 10)")
		ap.add_argument("--quality", "-Q", type=int, default=90,
										help="JPEG quality 0..100 (default 90)")
		ap.add_argument("--encoding", choices=("linear", "srgb"), default=None,
										help="Override the hillview:encoding attribute (otherwise "
												 "read from the EXR; missing tag is rejected)")
		args = ap.parse_args()

		try:
				tile_w, tile_h = parse_size(args.tile_size)
		except ValueError as e:
				print(f"error: --tile-size: {e}", file=sys.stderr)
				return 2
		if tile_w <= 0 or tile_h <= 0:
				print(f"error: --tile-size must be positive, got {tile_w}x{tile_h}",
							file=sys.stderr)
				return 2
		if args.max_tiles < 1:
				print("error: --max-tiles must be >= 1", file=sys.stderr)
				return 2

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
				display = img

		display = (display * 255).cast("uchar")

		src_aspect = display.width / display.height
		tile_aspect = tile_w / tile_h
		fits = src_aspect / tile_aspect
		if fits < 1.0:
				print(f"error: source aspect {src_aspect:.3f} is narrower than one tile "
							f"({tile_aspect:.3f}); nothing to split", file=sys.stderr)
				return 2
		n = min(args.max_tiles, int(fits))
		target_w = n * tile_w
		target_h = tile_h
		print(f"  src aspect:   {src_aspect:.3f}  (fits {fits:.2f} tiles, "
					f"tile aspect {tile_aspect:.3f})", file=sys.stderr)
		print(f"  tiles:        {n} (cap {args.max_tiles})", file=sys.stderr)
		print(f"  fit height -> {target_h}, center-crop width -> {target_w}",
					file=sys.stderr)

		scale = target_h / display.height
		if scale > 1.0:
				print(f"  warning: upscaling by {scale:.2f}x — source is below tile height",
							file=sys.stderr)
		display = display.resize(scale)
		# Pin to exact target dimensions, center-cropped. The resize may have
		# rounded height by ±1px; the width is normally larger than target_w
		# (excess is what gets centered away).
		left = (display.width - target_w) // 2
		top = (display.height - target_h) // 2
		display = display.crop(left, top, target_w, target_h)

		# Materialise so each tile crop doesn't re-run the whole pipeline.
		display = display.copy_memory()

		out_prefix = Path(args.output_prefix)
		pad = max(2, len(str(n)))
		for i in range(n):
				tile = display.crop(i * tile_w, 0, tile_w, tile_h)
				tile_path = f"{out_prefix}_{i+1:0{pad}d}.jpg"
				tile.write_to_file(tile_path, Q=args.quality, strip=True)
				print(f"  wrote {tile_path}", file=sys.stderr)

		print("done", file=sys.stderr)
		return 0


if __name__ == "__main__":
		sys.exit(main())
