"""
Deterministic sharpness measurement: how much in-focus detail a photo has.

Pure — bytes or a pyvips image in, a JSON-ready dict out; no network, no DB.
sharpness_cli.py drives it for the backfill; photo_processor is meant to call
measure_image() on the anonymized full variant once the numbers are trusted.

Method, at a fixed working size so photos of any resolution compare:

- Shrink to about WORK_AREA pixels (never enlarge). The score therefore says
  how sharp the photo looks at screen size; softness that only shows at native
  resolution in the deep-zoom view is out of scope for this version.
- Split the grey image into TILE × TILE tiles and, per tile, take the variance
  of the Laplacian (high-frequency energy) and the grey standard deviation
  (contrast).
- Drop tiles with almost no texture (sky, walls, fog): a flat tile has no
  focus information, it is not "blurry". Drop tiles over anonymization boxes:
  those pixels were blurred on purpose, by the worker.
- Report percentiles over the remaining tiles. p90 answers "is anything in
  focus" (a sharp subject on a soft background still scores high), p50 "is
  the photo sharp overall". rel_* divides by the tile's contrast, so a sharp
  but hazy or low-contrast scene is not mistaken for a blurry one.
- Measure that energy along four directions too (0°, 45°, 90°, 135°), because
  motion blur removes detail along ONE direction only: a field shot from a
  moving car keeps crisp vertical gradients in its horizontal rows, and the
  isotropic Laplacian scored exactly such a photo the sharpest of a 40-photo
  sample. weak_rel_* is the score in each tile's weakest direction;
  weak_direction_agreement is the share of tiles whose weakest direction is
  the most common one (0.25 = no preference). Motion blur shows as a low
  weak_rel with high agreement; a sharp scene with strong structure in one
  direction (rows, facades) has its weak direction vary from tile to tile.
- Version 2 adds edge width, because the contrast-relative energy above read
  clean, sparse-edged scenes (a wall, a bin, mesh, dotted glass) as soft:
  phone noise reduction smooths their few textures and the tile contrast is
  high. Per tile with a real step in it (EDGE_MIN_RANGE), the steepest slope
  divided by the step height: an edge blurred by sigma scores about 0.4/sigma,
  whatever the edge count or contrast. edge_p50 is the median over those
  tiles. The same ratio along x and along y alone gives the motion signal:
  x_weaker_share is the share of edge tiles whose horizontal slope is the
  weaker one, axis_ratio_p50 the median weaker/stronger. Shake and vehicle
  motion in this data smear horizontally: 0.95-1.00 for every motion-blurred
  photo in the 2026-11-03 review set, 0.17-0.92 for nearly all sharp ones.
  The version 1 fields stay, so documents of both versions compare.

Any size is measured; the cost is bounded by WORK_AREA. The backfill skips
the curated camera work (image_metrics_backfill.py BACKFILL_MAX_SOURCE_WIDTH),
which practically never has the whole-frame shake this metric exists for.

Numbers only; no "blurry" label yet. Thresholds come from calibrating against
real photos, and a label can be derived from the stored numbers later without
re-measuring. Bump VERSION whenever a change alters the numbers.
"""

import math

import cv2
import numpy as np
import pyvips

VERSION = 2
ALGORITHM = "laplacian-tiles+directional+edge-width"


WORK_AREA = 2_000_000      # working size in pixels, ~1630×1225 for 4:3
TILE = 64                  # tile edge at working size
TEXTURE_MIN_STD = 0.02     # grey std (0..1) below which a tile carries no focus information
MASK_MAX_FRACTION = 0.10   # a tile more than this covered by anonymization boxes is dropped
MASK_PAD = 0.10            # boxes grow by this fraction of their size: the blur bleeds past the box edge
MASK_PAD_MIN_PX = 4        # ...and by at least this many working pixels
DIRECTIONAL_SIGMA = 1.5    # Gaussian pre-smoothing for the directional terms (working pixels)
EDGE_SIGMA = 0.7           # pre-smoothing for the edge slopes: tames pixel noise, widens every edge alike
EDGE_MIN_RANGE = 0.12      # grey range (p2..p98, 0..1) a tile needs to contain a real step
EDGE_SLOPE_PERCENTILE = 99.5   # the tile's steepest slope, robust to single hot pixels


def load_work_image(data: bytes, width: int, height: int) -> pyvips.Image:
	"""
	Decode at roughly WORK_AREA pixels. thumbnail_buffer shrinks on load where
	the format allows it, so a large full variant is never decoded whole.

	no_rotate: boxes are in the stored pixel grid, so the pixels must stay in
	it too; an EXIF orientation tag on the stored file must not turn them.
	"""
	scale = min(1.0, math.sqrt(WORK_AREA / (width * height)))
	target_w = max(1, round(width * scale))
	target_h = max(1, round(height * scale))
	return pyvips.Image.thumbnail_buffer(data, target_w, height=target_h, size="down", no_rotate=True)


def to_grey(image: pyvips.Image) -> np.ndarray:
	"""float32 luminance in 0..1."""
	if image.hasalpha():
		image = image.flatten(background=[255])
	image = image.colourspace("b-w")[0].cast("uchar")
	return np.ndarray(buffer=image.write_to_memory(), dtype=np.uint8,
					  shape=(image.height, image.width)).astype(np.float32) / 255.0


def box_mask(shape: tuple[int, int], boxes, sx: float, sy: float) -> np.ndarray:
	"""bool mask, True over (padded) anonymization boxes. boxes: (x1, y1, x2, y2) in source pixels."""
	mask = np.zeros(shape, dtype=bool)
	h, w = shape
	for x1, y1, x2, y2 in boxes:
		x1, x2 = sorted((x1 * sx, x2 * sx))
		y1, y2 = sorted((y1 * sy, y2 * sy))
		pad_x = max(MASK_PAD_MIN_PX, (x2 - x1) * MASK_PAD)
		pad_y = max(MASK_PAD_MIN_PX, (y2 - y1) * MASK_PAD)
		c1, c2 = max(0, math.floor(x1 - pad_x)), min(w, math.ceil(x2 + pad_x))
		r1, r2 = max(0, math.floor(y1 - pad_y)), min(h, math.ceil(y2 + pad_y))
		if c1 < c2 and r1 < r2:
			mask[r1:r2, c1:c2] = True
	return mask


# Second derivative along a direction. The diagonal ones step √2 pixels, so
# their response is divided by 2 (energy by 4) to stay on the 0°/90° scale.
_DIRECTIONS = ("0", "45", "90", "135")
_DIRECTION_KERNELS = [
	np.array([[0, 0, 0], [1, -2, 1], [0, 0, 0]], np.float32),           # 0°: along x
	np.array([[0, 0, 1], [0, -2, 0], [1, 0, 0]], np.float32) / 2,       # 45°
	np.array([[0, 1, 0], [0, -2, 0], [0, 1, 0]], np.float32),           # 90°: along y
	np.array([[1, 0, 0], [0, -2, 0], [0, 0, 1]], np.float32) / 2,       # 135°
]


def _tile_stats(values: np.ndarray, rows: int, cols: int) -> np.ndarray:
	"""Per-tile mean of a (rows*TILE, cols*TILE) array → (rows, cols)."""
	return values.reshape(rows, TILE, cols, TILE).mean(axis=(1, 3))


def _tiles(values: np.ndarray, rows: int, cols: int) -> np.ndarray:
	"""(rows*TILE, cols*TILE) → (rows, cols, TILE*TILE): each tile's pixels in one row."""
	return values.reshape(rows, TILE, cols, TILE).transpose(0, 2, 1, 3).reshape(rows, cols, TILE * TILE)


def _edge_stats(g: np.ndarray, unmasked: np.ndarray, rows: int, cols: int) -> dict:
	"""Edge-width statistics over the unmasked tiles that contain a real step (see the module doc)."""
	smooth = cv2.GaussianBlur(g, (0, 0), EDGE_SIGMA)
	gx = cv2.Sobel(smooth, cv2.CV_32F, 1, 0, ksize=3) / 8   # /8: Sobel's weights, so slopes are per pixel
	gy = cv2.Sobel(smooth, cv2.CV_32F, 0, 1, ksize=3) / 8
	lo, hi = np.percentile(_tiles(smooth, rows, cols), [2, 98], axis=2)
	step = hi - lo
	edged = unmasked & (step >= EDGE_MIN_RANGE)
	if not edged.any():
		return {"edge_tiles": 0}
	step = step[edged]

	def slope(values):
		return np.percentile(_tiles(values, rows, cols)[edged], EDGE_SLOPE_PERCENTILE, axis=1) / step

	e = slope(np.hypot(gx, gy))
	ex, ey = slope(np.abs(gx)), slope(np.abs(gy))
	axis_ratio = np.minimum(ex, ey) / np.maximum(np.maximum(ex, ey), 1e-6)
	return {
		"edge_tiles": int(edged.sum()),
		"edge_p50": round(float(np.median(e)), 4),
		"edge_p90": round(float(np.percentile(e, 90)), 4),
		"axis_ratio_p50": round(float(np.median(axis_ratio)), 4),
		"x_weaker_share": round(float((ex < ey).mean()), 4),
	}


def measure_grey(grey: np.ndarray, mask: np.ndarray | None = None) -> dict:
	"""The sharpness document for one grey image (and optional exclusion mask) at working size."""
	h, w = grey.shape
	rows, cols = h // TILE, w // TILE
	doc = {
		"version": VERSION,
		"algorithm": ALGORITHM,
		"work_width": w,
		"work_height": h,
		"tile": TILE,
		"tiles_total": rows * cols,
	}
	if rows == 0 or cols == 0:
		return {**doc, "tiles_used": 0}

	lap = cv2.Laplacian(grey, cv2.CV_32F, ksize=3)
	# Crop to whole tiles; the ragged right/bottom strip is ignored.
	g = grey[:rows * TILE, :cols * TILE]
	l = lap[:rows * TILE, :cols * TILE]

	g_mean = _tile_stats(g, rows, cols)
	g_std = np.sqrt(np.maximum(_tile_stats(g * g, rows, cols) - g_mean ** 2, 0))
	l_mean = _tile_stats(l, rows, cols)
	l_var = np.maximum(_tile_stats(l * l, rows, cols) - l_mean ** 2, 0)

	textured = g_std >= TEXTURE_MIN_STD
	if mask is not None:
		masked_frac = _tile_stats(mask[:rows * TILE, :cols * TILE].astype(np.float32), rows, cols)
		unmasked = masked_frac <= MASK_MAX_FRACTION
		doc["masked_fraction"] = round(float(mask.mean()), 4)
	else:
		unmasked = np.ones_like(textured)
		doc["masked_fraction"] = 0.0
	used = textured & unmasked

	doc["tiles_used"] = int(used.sum())
	doc["textured_fraction"] = round(float(textured[unmasked].mean()) if unmasked.any() else 0.0, 4)
	doc.update(_edge_stats(g, unmasked, rows, cols))
	if not used.any():
		return doc

	lv = l_var[used]
	rel = np.sqrt(lv) / g_std[used]

	# Per-direction energy, only for the used tiles: (n_used, 4). On a smoothed
	# copy: at the finest scale sensor noise and codec artifacts are isotropic
	# and drown the smear (the moving-car field read weakest at 135° in 64% of
	# tiles raw, at 0° in 91% after DIRECTIONAL_SIGMA; sharp photos 39-55%).
	g_smooth = cv2.GaussianBlur(g, (0, 0), DIRECTIONAL_SIGMA)
	energies = []
	for kernel in _DIRECTION_KERNELS:
		d = cv2.filter2D(g_smooth, cv2.CV_32F, kernel)
		d_mean = _tile_stats(d, rows, cols)
		energies.append(np.maximum(_tile_stats(d * d, rows, cols) - d_mean ** 2, 0)[used])
	energies = np.stack(energies, axis=1)
	weak = energies.min(axis=1)
	strong = energies.max(axis=1)
	weak_rel = np.sqrt(weak) / g_std[used]
	weakest = energies.argmin(axis=1)
	counts = np.bincount(weakest, minlength=len(_DIRECTIONS))

	for name, values in (("lap_var", lv), ("rel", rel), ("weak_rel", weak_rel)):
		p50, p90 = np.percentile(values, [50, 90])
		doc[f"{name}_p50"] = round(float(p50), 6)
		doc[f"{name}_p90"] = round(float(p90), 6)
		doc[f"{name}_max"] = round(float(values.max()), 6)
	# sqrt(weak/strong) per tile: 1 = isotropic detail, → 0 = detail along one direction only.
	doc["anisotropy_p50"] = round(float(np.median(np.sqrt(weak / np.maximum(strong, 1e-12)))), 4)
	doc["weak_direction"] = _DIRECTIONS[int(counts.argmax())]
	doc["weak_direction_agreement"] = round(float(counts.max() / counts.sum()), 4)
	return doc


def measure_image(image: pyvips.Image, boxes=(), source_size: tuple[int, int] | None = None) -> dict:
	"""
	Measure an already-decoded image at working size (see load_work_image).
	boxes are in source pixels; source_size (w, h) is the frame they were
	detected in, defaulting to the image's own size.
	"""
	grey = to_grey(image)
	h, w = grey.shape
	src_w, src_h = source_size or (w, h)
	mask = box_mask((h, w), boxes, w / src_w, h / src_h) if boxes else None
	doc = measure_grey(grey, mask)
	# Working pixels per source pixel. Tiny for a gigapixel panorama, whose full
	# variant is an 8192-wide preview strip: there the score describes the
	# preview, not the photo, and a reader should discount it.
	doc["scale_from_source"] = round(w / src_w, 5)
	return doc


def measure_bytes(data: bytes, width: int, height: int, boxes=(), source_size: tuple[int, int] | None = None) -> dict:
	"""
	Measure an encoded image. width/height are its stored pixel size;
	source_size the frame the boxes are in (photos.width/height), when it differs.
	"""
	return measure_image(load_work_image(data, width, height), boxes, source_size or (width, height))
