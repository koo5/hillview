#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyvips", "OpenEXR", "numpy", "scikit-image"]
# ///
"""
Pyramid compression benchmark — is there ONE WebP setting that is fast enough
for local previews AND good enough for prod?

Context: the pano pipeline already renders a DZI pyramid (phase_13); if its
quality is prod-worthy, the worker can reuse it instead of re-decoding a
gigapixel EXR, and prod upload becomes "quick resizes + tile transfer".

For a region of a source image, builds a DZI pyramid per (Q, effort, tile
size) combination and reports:
  cpu_s / wall_s   CPU seconds of the dzsave (all vips threads; robust under
                   load) and wall seconds (meaningless under load)
  bytes / tiles    pyramid size and tile count
  L0 tile fidelity PSNR/SSIM of sampled full-resolution tiles vs the lossless
                   raster — what deep-zoom viewers actually see
  derived variants the worker's size variants (full<=8192, 2048, 1200, 320)
                   derived FROM THE PYRAMID (smallest level >= 2x target,
                   tiles stitched, downscaled) vs the same variants derived
                   straight from the lossless raster:
                     pre  = pyramid loss only (before the variant encode)
                     post = after both are encoded at --variant-q, i.e. what a
                            viewer gets; 'ref_post' is today's worker path for
                            comparison

Source region: an EXR is read via chunked OpenEXR scanline reads (vips'
EXR loader materializes the WHOLE decode at open, ~53 GB for the 4.4 Gpx
pano), any other format via a vips crop. hillview:encoding is honored the
same way exr_to_webp_pyramid.py does it.

Usage:
  pyramid_bench.py IN OUT_DIR [--crop WxH] [--q 60,75,85,93] [--effort 4]
                   [--tile-size 1024] [--variant-q 93] [--encoding linear|srgb]
Writes OUT_DIR/results.jsonl (one JSON object per run) and prints a table.
Run on an idle box.
"""

import argparse
import json
import math
import os
import resource
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exr_meta

DZ_NS = "{http://schemas.microsoft.com/deepzoom/2008}"


# --- source region ---------------------------------------------------------

def _oetf(lin: np.ndarray) -> np.ndarray:
	"""Forward sRGB OETF, piecewise (same math as exr_to_webp_pyramid.py)."""
	low = lin * 12.92
	high = np.power(np.clip(lin, 0.0, None), 1.0 / 2.4) * 1.055 - 0.055
	return np.where(lin > 0.0031308, high, low)


def load_exr_region(path: str, x0: int, y0: int, w: int, h: int, encoding: str, rows_per_chunk: int = 64) -> np.ndarray:
	"""Read an EXR window as sRGB uint8 HxWx3 via chunked scanline reads.

	Scanlines are always decompressed full-width, so the cost scales with the
	crop HEIGHT × image width, not the crop area — but memory stays ~crop size.
	"""
	import Imath
	import OpenEXR
	f = OpenEXR.InputFile(path)
	header = f.header()
	dw = header['dataWindow']
	full_w = dw.max.x - dw.min.x + 1
	full_h = dw.max.y - dw.min.y + 1
	if x0 + w > full_w or y0 + h > full_h:
		raise SystemExit(f"crop {w}x{h}@{x0},{y0} exceeds image {full_w}x{full_h}")
	ptype = Imath.PixelType(Imath.PixelType.FLOAT)
	out = np.empty((h, w, 3), dtype=np.uint8)
	for cy in range(0, h, rows_per_chunk):
		n = min(rows_per_chunk, h - cy)
		y1 = dw.min.y + y0 + cy
		y2 = y1 + n - 1
		lin = np.empty((n, w, 3), dtype=np.float32)
		for i, ch in enumerate(('R', 'G', 'B')):
			raw = f.channel(ch, ptype, y1, y2)
			plane = np.frombuffer(raw, dtype=np.float32).reshape(n, full_w)
			lin[:, :, i] = plane[:, x0:x0 + w]
		disp = _oetf(lin) if encoding == 'linear' else lin
		out[cy:cy + n] = np.clip(disp * 255.0 + 0.5, 0, 255).astype(np.uint8)
		print(f"  read rows {cy + n}/{h}", end='\r', file=sys.stderr)
	print(file=sys.stderr)
	f.close()
	return out


def load_region(path: str, crop: tuple[int, int] | None, encoding: str | None) -> np.ndarray:
	import pyvips
	if path.lower().endswith('.exr'):
		enc = encoding or exr_meta.read_encoding(path)
		if enc is None:
			# The pipeline ships encoding out-of-band in a `<file>.exr.encoding`
			# sidecar (the worker gets it via upload metadata); honor it here.
			sidecar = Path(path + '.encoding')
			if sidecar.is_file():
				enc = sidecar.read_text().strip()
		if enc not in ('linear', 'srgb'):
			raise SystemExit(f"{path}: hillview:encoding is {enc!r}; pass --encoding linear|srgb")
		import OpenEXR
		hdr = OpenEXR.InputFile(path).header()['dataWindow']
		full_w, full_h = hdr.max.x - hdr.min.x + 1, hdr.max.y - hdr.min.y + 1
		w, h = crop or (full_w, full_h)
		w, h = min(w, full_w), min(h, full_h)
		x0, y0 = (full_w - w) // 2, (full_h - h) // 2   # centered: pano edges are often black
		print(f"source: {path}\n  {full_w}x{full_h} {enc}; region {w}x{h} @ {x0},{y0}", file=sys.stderr)
		return load_exr_region(path, x0, y0, w, h, enc)
	img = pyvips.Image.new_from_file(path)
	if img.bands > 3:
		img = img[:3]
	img = img.colourspace('srgb')
	if img.format != 'uchar':
		img = (img * 255).cast('uchar')
	if crop:
		w, h = min(crop[0], img.width), min(crop[1], img.height)
		img = img.crop((img.width - w) // 2, (img.height - h) // 2, w, h)
	print(f"source: {path}\n  region {img.width}x{img.height}", file=sys.stderr)
	return img.numpy()


# --- DZI geometry + stitching -----------------------------------------------

def read_dzi(dzi_path: str) -> dict:
	"""Parse the .dzi descriptor (it is XML — query it, don't regex it)."""
	root = ET.parse(dzi_path).getroot()
	size = root.find(f"{DZ_NS}Size")
	return {
		'tile_size': int(root.get('TileSize')),
		'overlap': int(root.get('Overlap')),
		'format': root.get('Format'),
		'width': int(size.get('Width')),
		'height': int(size.get('Height')),
	}


def level_dims(w: int, h: int, level: int, max_level: int) -> tuple[int, int]:
	f = 2 ** (max_level - level)
	return math.ceil(w / f), math.ceil(h / f)


def stitch_level(files_dir: str, level: int, lw: int, lh: int, tile_size: int, overlap: int, fmt: str) -> np.ndarray:
	"""Decode + assemble a whole DZI level into an lh x lw x 3 uint8 array.

	DZI tile (c, r) covers level pixels [c*ts - o, (c+1)*ts + o) clamped to
	the level, so the overlap must be cropped off every interior edge.
	"""
	import pyvips
	out = np.empty((lh, lw, 3), dtype=np.uint8)
	cols, rows = math.ceil(lw / tile_size), math.ceil(lh / tile_size)
	for c in range(cols):
		for r in range(rows):
			tile = pyvips.Image.new_from_file(os.path.join(files_dir, str(level), f"{c}_{r}.{fmt}"))
			arr = tile.numpy()
			if arr.ndim == 3 and arr.shape[2] > 3:
				arr = arr[:, :, :3]
			ox = overlap if c > 0 else 0
			oy = overlap if r > 0 else 0
			x0, y0 = c * tile_size, r * tile_size
			tw, th = min(tile_size, lw - x0), min(tile_size, lh - y0)
			out[y0:y0 + th, x0:x0 + tw] = arr[oy:oy + th, ox:ox + tw]
	return out


# --- metrics ---------------------------------------------------------------

def psnr(a: np.ndarray, b: np.ndarray) -> float:
	mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
	return float('inf') if mse == 0 else 10.0 * math.log10(255.0 ** 2 / mse)


def ssim(a: np.ndarray, b: np.ndarray) -> float:
	from skimage.metrics import structural_similarity
	return float(structural_similarity(a, b, channel_axis=2, data_range=255))


def to_vips(arr: np.ndarray):
	import pyvips
	arr = np.ascontiguousarray(arr)
	return pyvips.Image.new_from_memory(arr.tobytes(), arr.shape[1], arr.shape[0], 3, 'uchar')


def resize_to_width(arr: np.ndarray, target_w: int) -> np.ndarray:
	"""Same resampler for both paths, so only the pyramid loss differs."""
	img = to_vips(arr)
	return img.resize(target_w / img.width, kernel='lanczos3').numpy()


def webp_roundtrip(arr: np.ndarray, q: int) -> np.ndarray:
	import pyvips
	buf = to_vips(arr).webpsave_buffer(Q=q)
	return pyvips.Image.new_from_buffer(buf, "").numpy()


def crop_common(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
	h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
	return a[:h, :w], b[:h, :w]


# --- one run ---------------------------------------------------------------

def bench_one(ref: np.ndarray, out_dir: Path, q: int, effort: int, tile_size: int, overlap: int,
              variant_q: int, sizes: list[int], l0_samples: int) -> dict:
	import pyvips
	h, w = ref.shape[:2]
	prefix = out_dir / f"q{q}_e{effort}_t{tile_size}"
	ref_img = to_vips(ref)

	ru0 = resource.getrusage(resource.RUSAGE_SELF)
	t0 = time.monotonic()
	ref_img.dzsave(str(prefix), tile_size=tile_size, overlap=overlap,
	               suffix=f".webp[Q={q},effort={effort}]")
	wall = time.monotonic() - t0
	ru1 = resource.getrusage(resource.RUSAGE_SELF)
	cpu = (ru1.ru_utime - ru0.ru_utime) + (ru1.ru_stime - ru0.ru_stime)

	files_dir = f"{prefix}_files"
	dzi = read_dzi(f"{prefix}.dzi")
	assert (dzi['width'], dzi['height']) == (w, h), dzi
	total_bytes, tiles = 0, 0
	for root, _dirs, names in os.walk(files_dir):
		for n in names:
			if n.endswith(f".{dzi['format']}"):
				tiles += 1
				total_bytes += os.path.getsize(os.path.join(root, n))
	max_level = math.ceil(math.log2(max(w, h)))

	# L0 tile fidelity: sample tiles evenly across the level
	cols, rows = math.ceil(w / tile_size), math.ceil(h / tile_size)
	all_tiles = [(c, r) for c in range(cols) for r in range(rows)]
	step = max(1, len(all_tiles) // max(1, l0_samples))
	l0_psnr, l0_ssim = [], []
	for c, r in all_tiles[::step][:l0_samples]:
		tile = pyvips.Image.new_from_file(os.path.join(files_dir, str(max_level), f"{c}_{r}.{dzi['format']}")).numpy()[:, :, :3]
		ox = overlap if c > 0 else 0
		oy = overlap if r > 0 else 0
		x0, y0 = c * tile_size, r * tile_size
		tw, th = min(tile_size, w - x0), min(tile_size, h - y0)
		got = tile[oy:oy + th, ox:ox + tw]
		want = ref[y0:y0 + th, x0:x0 + tw]
		l0_psnr.append(psnr(got, want))
		l0_ssim.append(ssim(got, want))

	# derived variants: smallest level with width >= 2*target
	variants = {}
	for target in sizes:
		if target * 2 > w:
			continue  # region too small to honor the >=2x rule for this size
		level = None
		for lv in range(max_level, -1, -1):
			lw, _ = level_dims(w, h, lv, max_level)
			if lw >= 2 * target:
				level = lv
		lw, lh = level_dims(w, h, level, max_level)
		pyr_level = stitch_level(files_dir, level, lw, lh, tile_size, overlap, dzi['format'])
		shrink = 2 ** (max_level - level)
		ref_level = ref_img.shrink(shrink, shrink).numpy() if shrink > 1 else ref
		pyr_level, ref_level = crop_common(pyr_level, ref_level)
		pyr_var = resize_to_width(pyr_level, target)
		ref_var = resize_to_width(ref_level, target)
		pyr_var, ref_var = crop_common(pyr_var, ref_var)
		pyr_post = webp_roundtrip(pyr_var, variant_q)
		ref_post = webp_roundtrip(ref_var, variant_q)
		variants[str(target)] = {
			'level': level, 'level_w': lw, 'downscale': round(lw / target, 2),
			'pre_psnr': round(psnr(pyr_var, ref_var), 2), 'pre_ssim': round(ssim(pyr_var, ref_var), 4),
			'post_psnr': round(psnr(pyr_post, ref_var), 2), 'post_ssim': round(ssim(pyr_post, ref_var), 4),
			'ref_post_psnr': round(psnr(ref_post, ref_var), 2), 'ref_post_ssim': round(ssim(ref_post, ref_var), 4),
		}

	return {
		'q': q, 'effort': effort, 'tile_size': tile_size, 'overlap': overlap,
		'region_w': w, 'region_h': h, 'megapixels': round(w * h / 1e6, 1),
		'cpu_s': round(cpu, 2), 'wall_s': round(wall, 2),
		'cpu_s_per_gpx': round(cpu / (w * h / 1e9), 1),
		'bytes': total_bytes, 'tiles': tiles,
		'bytes_per_mpx': round(total_bytes / (w * h / 1e6)),
		'l0_psnr': round(float(np.mean(l0_psnr)), 2), 'l0_ssim': round(float(np.mean(l0_ssim)), 4),
		'variant_q': variant_q, 'variants': variants,
	}


def main() -> int:
	ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	ap.add_argument("input")
	ap.add_argument("out_dir")
	ap.add_argument("--crop", default="16384x1024", help="WxH region, centered (default 16384x1024); 'full' for the whole image")
	ap.add_argument("--q", default="60,75,85,93", help="WebP Q values, comma-separated")
	ap.add_argument("--effort", default="4", help="WebP effort values (0-6), comma-separated")
	ap.add_argument("--tile-size", default="1024", help="DZI tile sizes, comma-separated")
	ap.add_argument("--overlap", type=int, default=1)
	ap.add_argument("--variant-q", type=int, default=93, help="Q the worker encodes size variants at")
	ap.add_argument("--sizes", default="8192,2048,1200,320", help="variant widths to derive")
	ap.add_argument("--l0-samples", type=int, default=12, help="full-res tiles sampled for L0 fidelity")
	ap.add_argument("--encoding", choices=("linear", "srgb"), default=None)
	ap.add_argument("--keep", action="store_true", help="keep the generated pyramids (default: delete after measuring)")
	args = ap.parse_args()

	crop = None if args.crop == 'full' else tuple(int(v) for v in args.crop.lower().split('x'))
	out_dir = Path(args.out_dir)
	out_dir.mkdir(parents=True, exist_ok=True)
	ref = load_region(args.input, crop, args.encoding)
	sizes = [int(s) for s in args.sizes.split(',')]

	results = []
	results_path = out_dir / "results.jsonl"
	with open(results_path, "a") as fh:
		for tile_size in (int(t) for t in args.tile_size.split(',')):
			for effort in (int(e) for e in args.effort.split(',')):
				for q in (int(v) for v in args.q.split(',')):
					print(f"== Q={q} effort={effort} tile={tile_size}", file=sys.stderr)
					r = bench_one(ref, out_dir, q, effort, tile_size, args.overlap, args.variant_q, sizes, args.l0_samples)
					r['input'] = os.path.abspath(args.input)
					fh.write(json.dumps(r) + "\n")
					fh.flush()
					results.append(r)
					if not args.keep:
						import shutil
						prefix = out_dir / f"q{q}_e{effort}_t{tile_size}"
						shutil.rmtree(f"{prefix}_files", ignore_errors=True)
						Path(f"{prefix}.dzi").unlink(missing_ok=True)

	# summary table
	print(f"\nregion {results[0]['region_w']}x{results[0]['region_h']} ({results[0]['megapixels']} Mpx); "
	      f"variants encoded at Q{args.variant_q}; results in {results_path}")
	hdr = f"{'Q':>3} {'eff':>3} {'tile':>4} {'cpu s':>7} {'cpu/Gpx':>8} {'MB':>7} {'B/Mpx':>7} {'L0 psnr':>7} {'L0 ssim':>7}"
	for s in sizes:
		hdr += f" | {s}: pre/post/ref psnr"
	print(hdr)
	for r in results:
		line = (f"{r['q']:>3} {r['effort']:>3} {r['tile_size']:>4} {r['cpu_s']:>7.1f} {r['cpu_s_per_gpx']:>8.0f} "
		        f"{r['bytes'] / 1e6:>7.1f} {r['bytes_per_mpx']:>7} {r['l0_psnr']:>7.2f} {r['l0_ssim']:>7.4f}")
		for s in sizes:
			v = r['variants'].get(str(s))
			line += " | " + (f"{v['pre_psnr']:.1f}/{v['post_psnr']:.1f}/{v['ref_post_psnr']:.1f}" if v else "  n/a  ")
		print(line)
	return 0


if __name__ == "__main__":
	sys.exit(main())
