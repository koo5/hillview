#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["OpenEXR", "numpy"]
# ///
"""
Produce the canonical archival linear EXR for the Hillview pano pipeline:
apply inverse sRGB OETF to RGB so pixels represent linear light, drop
the alpha channel, tag hillview:encoding=linear.

Why these three things together: the pipeline's downstream consumers
(darktable, the worker, exr_to_webp_pyramid) all need scene-linear RGB.
Alpha from enblend is a coverage mask with edge overshoots (values
outside [0, 1]) that has no consumer downstream and just skews stats
on the linearized EXR. Pass `--keep-alpha` for the rare case (CG
renders, deliberate compositing).

After this runs the pixel values represent linear light intensity, which
is what every EXR-reading tool (darktable, Nuke, OpenCV) assumes. The
hillview:encoding tag is updated to 'linear' to match.

Writes atomically (temp file + rename) so an interrupted run never leaves
a half-converted EXR in place of the original.

Uses the OpenEXR Python library directly (not pyvips), because some
libvips builds have openexrload without openexrsave.

Usage:
	exr_linearize.py FILE.exr              # overwrite in place, drop alpha
	exr_linearize.py FILE.exr -o OUT.exr   # write to a new file
	exr_linearize.py FILE.exr --keep-alpha # preserve alpha (rare)

Memory: loads all channels into numpy arrays via OpenEXR.File
(separate_channels=True). For a gigapixel 4-channel half-float pano
that's ~4.5 GB; for float32 ~9 GB. Modern File API is required because
the legacy InputFile/OutputFile path silently drops custom-named string
attributes — exr_meta.py set's hillview:encoding=linear write would be
a no-op there.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
import OpenEXR

EXR_META = Path(__file__).resolve().parent / "exr_meta.py"


def inv_srgb(v: np.ndarray) -> np.ndarray:
		"""Inverse sRGB OETF, piecewise, element-wise. Returns float32.

		Input is clipped to [0, ∞) first. enblend's multi-band blending can
		produce pixels slightly below 0; raising a small negative to 2.4
		gives NaN (via numpy's eager evaluation of both np.where branches),
		which triggers RuntimeWarnings even though the NaN would've been
		discarded by np.where. Clipping nips it.
		"""
		v = np.maximum(v, 0.0)
		return np.where(
				v > 0.04045,
				((v + 0.055) / 1.055) ** 2.4,
				v / 12.92,
		).astype(np.float32)


def linearize(in_path: Path, out_path: Path, keep_alpha: bool = False) -> None:
		f = OpenEXR.File(str(in_path), separate_channels=True)
		src_channels = f.channels()
		print(f"  channels in:  {list(src_channels.keys())}", file=sys.stderr)

		new_channels: dict[str, np.ndarray] = {}
		for name, ch in src_channels.items():
				if name.upper() == "A":
						if not keep_alpha:
								# Default: drop. Alpha is a coverage mask with no
								# downstream consumer; enblend's edge overshoots in it
								# also skew vips min/max on the result.
								continue
						# Alpha is light-coverage, not light intensity — pass through.
						new_channels[name] = ch.pixels.copy()
						continue
				src_dtype = ch.pixels.dtype
				# Compute in float32 for precision; cast back to the channel's
				# native storage type so HALF stays HALF and FLOAT stays FLOAT.
				new_channels[name] = inv_srgb(ch.pixels.astype(np.float32)).astype(src_dtype)

		print(f"  channels out: {list(new_channels.keys())}", file=sys.stderr)

		# Strip computed/derived header keys; OpenEXR.File regenerates them
		# from the channels dict and the resulting array shapes. Leaving
		# them in the dict produces a redundancy that the constructor may
		# accept but isn't guaranteed to.
		hdr = {k: v for k, v in f.header().items()
					 if k not in ("channels", "dataWindow", "displayWindow")}

		OpenEXR.File(hdr, new_channels).write(str(out_path))


def main() -> int:
		ap = argparse.ArgumentParser(
				description=__doc__,
				formatter_class=argparse.RawDescriptionHelpFormatter,
		)
		ap.add_argument("input")
		ap.add_argument("-o", "--output", default=None,
										help="Output path (default: overwrite input)")
		ap.add_argument("--keep-alpha", action="store_true",
										help="Preserve alpha channel (default: drop). "
												 "Rare — useful only for deliberate compositing.")
		args = ap.parse_args()

		in_path = Path(args.input).resolve()
		if not in_path.is_file():
				print(f"error: not a file: {in_path}", file=sys.stderr)
				return 2

		out_path = Path(args.output).resolve() if args.output else in_path

		tmp = out_path.with_name(out_path.stem + ".linearize.exr")
		print(f"linearizing {in_path.name} -> {tmp.name}", file=sys.stderr)
		linearize(in_path, tmp, keep_alpha=args.keep_alpha)
		tmp.replace(out_path)
		print(f"linearized: {out_path}", file=sys.stderr)

		print(f"tagging hillview:encoding=linear ...", file=sys.stderr)
		subprocess.check_call([str(EXR_META), "set", str(out_path),
													 "--encoding", "linear"])
		return 0


if __name__ == "__main__":
		sys.exit(main())
