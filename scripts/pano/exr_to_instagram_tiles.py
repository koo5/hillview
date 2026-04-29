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

To zoom into a horizontal band of the pano (e.g. drop empty sky/foreground
so the remaining content scales up to fill the tile), pass
`--top P --bottom P` as percentages of source height. The vertical crop is
applied to the source before the height fit, so the band you keep is what
each tile scales from.

Tiles are rendered at `--oversample` times the logical Instagram dimensions
(default 2× → 2160x2700). Instagram recompresses anyway; handing it 2×
input gives its downscale-then-recompress pipeline more detail to work with.
Upscaling is forbidden — if the source (after viewport crop) isn't tall
enough to fill the oversampled tile height, the script bails.

Default output is JPEG Q95 (visually lossless on photographic content).
Pass `--format png` for annotated panos with text or sharp geometric
overlays — JPEG rings on hard edges, and IG's own recompress doubles the
artifact, while PNG into IG means just one round of lossy on top instead
of two. PNG tiles are roughly 5–10× larger; still under IG's 30 MB cap.

Output:
	<prefix>_01.{jpg,png} .. <prefix>_NN.{jpg,png}

Usage:
	exr_to_instagram_tiles.py IN.exr OUT_PREFIX
		[--tile-size WxH]      default 1080x1350 (Instagram 4:5 portrait)
		[--max-tiles N]        default 10 (carousel limit)
		[--top P --bottom P]   keep rows P%..P% of source height (default 0..100)
		[--oversample F]       output size multiplier (default 2.0)
		[--format jpg|png]     default jpg; png for annotated content
		[--quality Q]          JPEG quality (default 95; ignored for png)
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
										help="tiles named <prefix>_NN.<jpg|png>")
		ap.add_argument("--tile-size", default="1080x1350",
										help="per-tile WxH (default 1080x1350, Instagram 4:5)")
		ap.add_argument("--max-tiles", type=int, default=10,
										help="hard cap on tile count (default 10)")
		ap.add_argument("--top", type=float, default=0.0,
										help="crop source above this %% of height (default 0)")
		ap.add_argument("--bottom", type=float, default=100.0,
										help="crop source below this %% of height (default 100)")
		ap.add_argument("--oversample", type=float, default=2.0,
										help="output size multiplier vs --tile-size (default 2.0; "
												 "uploading at 2x IG display size gives IG more detail "
												 "to crush. Pass 1.0 for exact IG dimensions)")
		ap.add_argument("--format", choices=("jpg", "png"), default="jpg",
										help="output format (default jpg; pass png for annotated panos)")
		ap.add_argument("--quality", "-Q", type=int, default=95,
										help="JPEG quality 0..100 (default 95; ignored for png)")
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
		if not (0.0 <= args.top < args.bottom <= 100.0):
				print(f"error: --top {args.top} --bottom {args.bottom} must satisfy "
							"0 <= top < bottom <= 100", file=sys.stderr)
				return 2
		if args.oversample <= 0.0:
				print(f"error: --oversample must be positive, got {args.oversample}",
							file=sys.stderr)
				return 2

		# Bake oversample into the physical tile size. The aspect ratio is
		# unchanged, so N selection downstream is identical whether oversample
		# is 1 or 4.
		tile_w = int(round(tile_w * args.oversample))
		tile_h = int(round(tile_h * args.oversample))

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

		if args.top > 0.0 or args.bottom < 100.0:
				crop_y = int(round(args.top / 100.0 * img.height))
				crop_h = int(round(args.bottom / 100.0 * img.height)) - crop_y
				print(f"  viewport: rows {crop_y}..{crop_y + crop_h} "
							f"({args.top:.1f}%..{args.bottom:.1f}%, height {crop_h})",
							file=sys.stderr)
				img = img.crop(0, crop_y, img.width, crop_h)

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
				print(f"error: source height {display.height}px is below tile height "
							f"{target_h}px (oversample={args.oversample:g}); refusing to upscale. "
							"Reduce --oversample, widen --top/--bottom, or use a taller pano.",
							file=sys.stderr)
				return 2
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
		if args.format == "jpg":
				suffix = "jpg"
				write_kwargs = {"Q": args.quality, "strip": True}
		else:
				suffix = "png"
				write_kwargs = {"strip": True}
		for i in range(n):
				tile = display.crop(i * tile_w, 0, tile_w, tile_h)
				tile_path = f"{out_prefix}_{i+1:0{pad}d}.{suffix}"
				tile.write_to_file(tile_path, **write_kwargs)
				print(f"  wrote {tile_path}", file=sys.stderr)

		print("done", file=sys.stderr)
		return 0


if __name__ == "__main__":
		sys.exit(main())
