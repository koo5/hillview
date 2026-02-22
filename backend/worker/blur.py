import colorsys
import logging
import os
import cv2
import numpy as np

from detections import TARGET_CLASSES


# Predefined pretty hues (degrees): pink, coral, teal, lavender, mint, gold, sky blue, salmon
PRETTY_HUES = [330, 15, 175, 270, 155, 45, 200, 5]


def read_image(source_path):
	# Validate file size before processing to prevent memory exhaustion
	try:
		file_size = os.path.getsize(source_path)
		if file_size > 300 * 1024 * 1024:
			logging.warning(f"Image file too large for processing: {file_size} bytes")
			raise ValueError(f"Image file too large for processing: {file_size} bytes")
	except OSError:
		logging.warning(f"Could not access image file: {source_path}")
		raise ValueError("Invalid image file path")

	logging.info(f"Reading image: {source_path}")
	image = cv2.imread(source_path)
	if image is None:
		logging.warning(f"Could not read image: {source_path}")
		raise ValueError("Invalid image file content")

	# Validate image dimensions to prevent memory exhaustion
	height, width = image.shape[:2]
	if width > 65536 or height > 65536 or (width * height) > 65536*10000:
		raise ValueError(f"Image size too large or invalid ({width}x{height}). Please use a smaller image.")

	return image


def _random_pretty_color(rng, roi_hue_deg=None):
	"""Pick a random pretty color as BGR, optionally biased toward the ROI's hue.

	The result blends a random pretty hue with the local hue of the region
	being covered (~40% local influence), so the block feels harmonious but
	still clearly artificial.
	"""
	pretty_hue = PRETTY_HUES[rng.integers(len(PRETTY_HUES))]
	pretty_hue = (pretty_hue + rng.integers(-15, 16)) % 360

	if roi_hue_deg is not None:
		# blend 40% toward the ROI hue (shortest arc on the color wheel)
		diff = (roi_hue_deg - pretty_hue + 180) % 360 - 180
		hue_deg = (pretty_hue + diff * 0.4) % 360
	else:
		hue_deg = pretty_hue

	sat = 0.55 + rng.random() * 0.35   # 0.55-0.90
	lit = 0.50 + rng.random() * 0.15   # 0.50-0.65
	r, g, b = colorsys.hls_to_rgb(hue_deg / 360.0, lit, sat)
	return np.array([b * 255, g * 255, r * 255], dtype=np.float64)


def apply_blur(source_path, image, detections):
	"""Replace detected regions with a solid pretty-color block whose
	brightness roughly matches the original image content."""

	seed = hash(source_path) % (2 ** 32)
	rng = np.random.default_rng(seed)

	for det in detections:
		x1 = det['bbox']['x1']
		y1 = det['bbox']['y1']
		x2 = det['bbox']['x2']
		y2 = det['bbox']['y2']
		cls_id = det['class_id']

		x1, y1 = max(0, x1), max(0, y1)
		x2, y2 = min(x2, image.shape[1]), min(y2, image.shape[0])

		roi = image[y1:y2, x1:x2]
		if roi.size == 0:
			continue

		# extract average brightness and hue from the ROI
		avg_bgr = roi.mean(axis=(0, 1))
		avg_brightness = 0.114 * avg_bgr[0] + 0.587 * avg_bgr[1] + 0.299 * avg_bgr[2]
		# convert average BGR to hue
		r_norm, g_norm, b_norm = avg_bgr[2] / 255.0, avg_bgr[1] / 255.0, avg_bgr[0] / 255.0
		roi_hue, _, _ = colorsys.rgb_to_hls(r_norm, g_norm, b_norm)
		roi_hue_deg = roi_hue * 360.0

		# pick a pretty color biased toward the ROI's hue, then match brightness
		color = _random_pretty_color(rng, roi_hue_deg)
		color_brightness = 0.114 * color[0] + 0.587 * color[1] + 0.299 * color[2]
		if color_brightness > 0:
			scale = avg_brightness / color_brightness
			color = np.clip(color * scale, 0, 255)

		image[y1:y2, x1:x2] = color.astype(np.uint8)

		label = TARGET_CLASSES.get(cls_id, "unknown")
		logging.info(f"Colored over {label} at ({x1},{y1})-({x2},{y2})")