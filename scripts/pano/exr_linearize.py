#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["OpenEXR", "numpy"]
# ///
"""
Convert a display-referred EXR (sRGB-encoded floats in [0, 1]) into a
genuinely scene-linear EXR by applying the inverse sRGB transfer function.

After this runs the pixel values represent linear light intensity, which
is what every EXR-reading tool (darktable, Nuke, OpenCV) assumes. The
hillview:encoding tag is updated to 'linear' to match.

Writes atomically (temp file + rename) so an interrupted run never leaves
a half-converted EXR in place of the original.

Uses the OpenEXR Python library directly (not pyvips), because some
libvips builds have openexrload without openexrsave.

Usage:
	exr_linearize.py FILE.exr              # overwrite in place
	exr_linearize.py FILE.exr -o OUT.exr   # write to a new file

Memory: reads all channels to float32 numpy arrays in memory. For a
gigapixel 4-channel pano that's ~9 GB of RAM during processing.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
import OpenEXR
import Imath

EXR_META = Path(__file__).resolve().parent / "exr_meta.py"

PT_HALF = Imath.PixelType(Imath.PixelType.HALF)
PT_FLOAT = Imath.PixelType(Imath.PixelType.FLOAT)


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


def linearize(in_path: Path, out_path: Path) -> None:
		exr_in = OpenEXR.InputFile(str(in_path))
		try:
				header = exr_in.header()
				dw = header["dataWindow"]
				width = dw.max.x - dw.min.x + 1
				height = dw.max.y - dw.min.y + 1
				channels = header["channels"]
				print(f"  {width} x {height}, channels: {list(channels.keys())}",
							file=sys.stderr)

				out_bytes: dict[str, bytes] = {}
				for name, ch_info in channels.items():
						# Read as float32 regardless of stored type so the math has precision.
						raw = exr_in.channel(name, PT_FLOAT)
						arr = np.frombuffer(raw, dtype=np.float32).reshape((height, width))

						if name.upper() == "A":
								# Alpha is a coverage mask, not light intensity — pass through.
								processed = arr
						else:
								processed = inv_srgb(arr)

						# Convert back to the channel's declared storage type.
						if ch_info.type == PT_HALF:
								out_bytes[name] = processed.astype(np.float16).tobytes()
						else:
								out_bytes[name] = processed.astype(np.float32).tobytes()
						print(f"    {name} ({ch_info.type}): done", file=sys.stderr)
		finally:
				exr_in.close()

		out_f = OpenEXR.OutputFile(str(out_path), header)
		try:
				out_f.writePixels(out_bytes)
		finally:
				out_f.close()


def main() -> int:
		ap = argparse.ArgumentParser(
				description=__doc__,
				formatter_class=argparse.RawDescriptionHelpFormatter,
		)
		ap.add_argument("input")
		ap.add_argument("-o", "--output", default=None,
										help="Output path (default: overwrite input)")
		args = ap.parse_args()

		in_path = Path(args.input).resolve()
		if not in_path.is_file():
				print(f"error: not a file: {in_path}", file=sys.stderr)
				return 2

		out_path = Path(args.output).resolve() if args.output else in_path

		tmp = out_path.with_name(out_path.stem + ".linearize.exr")
		print(f"linearizing {in_path.name} -> {tmp.name}", file=sys.stderr)
		linearize(in_path, tmp)
		tmp.replace(out_path)
		print(f"linearized: {out_path}", file=sys.stderr)

		print(f"tagging hillview:encoding=linear ...", file=sys.stderr)
		subprocess.check_call([str(EXR_META), "set", str(out_path),
													 "--encoding", "linear"])
		return 0


if __name__ == "__main__":
		sys.exit(main())
