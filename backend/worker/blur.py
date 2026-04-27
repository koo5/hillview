import colorsys
import contextlib
import logging
import os
import struct
import threading
import cv2
import numpy as np
import security_utils
import pyvips

from detections import TARGET_CLASSES


# Predefined pretty hues (degrees): pink, coral, teal, lavender, mint, gold, sky blue, salmon
PRETTY_HUES = [330, 15, 175, 270, 155, 45, 200, 5]


# Per-thread slot for collecting _dev_only warnings during a single upload.
# Each upload runs in its own threadpool thread (with its own nested asyncio
# loop running in the same thread), so threading.local is the right scope —
# no contextvar propagation gymnastics needed across the loop-in-thread boundary.
_warnings_tls = threading.local()


@contextlib.contextmanager
def collect_warnings():
	"""Capture _dev_only warnings emitted inside the with-block into a list.

	Restores any prior collector on exit, so it composes with itself if ever
	nested. Safe to call from any thread; each thread has its own TLS slot.
	"""
	warnings: list[str] = []
	prior = getattr(_warnings_tls, 'warnings', None)
	_warnings_tls.warnings = warnings
	try:
		yield warnings
	finally:
		_warnings_tls.warnings = prior


def _dev_only(reason):
	"""Refuse a speculative image-handling heuristic unless DEV_MODE=true.

	These branches handle inputs whose color provenance we can't fully verify
	(unusual ICC profiles, untagged 16-bit TIFFs, cv2 fallback after pyvips
	load failure). Each can silently miscolor an upload, so in production we
	refuse; in DEV_MODE we log loudly, append to the active collect_warnings()
	list (if any), and proceed so test fixtures still work.
	"""
	if os.environ.get('DEV_MODE', 'false').lower() != 'true':
		raise ValueError(
			f"Refusing speculative image handling: {reason}. "
			f"Convert to standard sRGB 8-bit (or tagged EXR with "
			f"hillview:encoding) before upload, or set DEV_MODE=true to "
			f"allow with a warning."
		)
	logging.warning(f"DEV_MODE: speculative image handling — {reason}")
	warnings = getattr(_warnings_tls, 'warnings', None)
	if warnings is not None:
		warnings.append(reason)


def _icc_profile_has_linear_trc(profile_data):
	"""Check if an ICC profile has linear (gamma 1.0) tone response curves.

	Parses the ICC profile binary to inspect rTRC/gTRC/bTRC tags.
	Returns True if any TRC tag indicates linear gamma (identity curve or gamma 1.0).
	"""
	if len(profile_data) < 132:
		return False
	try:
		tag_count = struct.unpack('>I', profile_data[128:132])[0]
		for i in range(tag_count):
			offset = 132 + i * 12
			if offset + 12 > len(profile_data):
				break
			tag_sig = profile_data[offset:offset + 4]
			if tag_sig not in (b'rTRC', b'gTRC', b'bTRC'):
				continue
			tag_offset = struct.unpack('>I', profile_data[offset + 4:offset + 8])[0]
			if tag_offset + 12 > len(profile_data):
				continue
			trc_type = profile_data[tag_offset:tag_offset + 4]
			if trc_type == b'curv':
				count = struct.unpack('>I', profile_data[tag_offset + 8:tag_offset + 12])[0]
				if count == 0:
					return True  # Identity curve = linear
				if count == 1 and tag_offset + 14 <= len(profile_data):
					gamma = struct.unpack('>H', profile_data[tag_offset + 12:tag_offset + 14])[0] / 256.0
					if abs(gamma - 1.0) < 0.01:
						return True
			elif trc_type == b'para':
				if tag_offset + 16 <= len(profile_data):
					gamma = struct.unpack('>I', profile_data[tag_offset + 12:tag_offset + 16])[0] / 65536.0
					if abs(gamma - 1.0) < 0.01:
						return True
	except (struct.error, IndexError):
		return False
	return False


def _exr_encoding(path):
	"""Return the hillview:encoding attribute value from an EXR, or None if
	the attribute is absent.

	Convention defined in scripts/pano/exr_meta.py:
	  "srgb"    pixels are display-referred (sRGB OETF already applied)
	  "linear"  pixels are scene-linear
	Absence → caller must reject; silent defaults silently miscolor uploads.
	"""
	import OpenEXR
	exr = OpenEXR.InputFile(path)
	try:
		header = exr.header()
		if 'hillview:encoding' not in header:
			return None
		raw = header['hillview:encoding']
		return raw.decode() if isinstance(raw, bytes) else str(raw)
	finally:
		exr.close()


def normalize_to_srgb(img, source_path=None):
	"""Convert a pyvips image to sRGB 8-bit RGB (3 bands).

	Handles deterministically (always allowed):
	- Alpha channel removal (4+ bands → 3)
	- EXR files: reads hillview:encoding attribute ('srgb' or 'linear');
	  untagged EXRs are rejected outright
	- ICC profile → sRGB via pyvips icc_transform when it returns a clean result
	- 16-bit ushort with interpretation='rgb16'/'srgb' (standard gamma-encoded)
	- 8-bit sRGB pass-through

	Gated behind DEV_MODE (warning + continue, otherwise refuse): everything
	speculative — linear-TRC ICC profiles (Hugin), 16-bit ushort with
	non-standard interpretation, icc_transform failures or unexpected returns.
	See _dev_only() for the rationale.
	"""
	if img.bands > 3:
		img = img[:3]
	if source_path and source_path.lower().endswith('.exr'):
		encoding = _exr_encoding(source_path)
		if encoding is None:
			raise ValueError(
				f"EXR {source_path} has no hillview:encoding attribute. "
				f"Tag the file before upload: "
				f"scripts/pano/exr_meta.py set FILE --encoding {{linear,srgb}}"
			)
		if encoding == 'srgb':
			# pixels already carry sRGB OETF; prevent colourspace('srgb')
			# below from re-applying the gamma curve
			logging.info("EXR %s: hillview:encoding=srgb, marking interpretation=srgb", source_path)
			img = img.copy(interpretation='srgb')
		elif encoding == 'linear':
			# pixels are scene-linear; colourspace('srgb') below will apply OETF
			logging.info("EXR %s: hillview:encoding=linear, marking interpretation=scrgb", source_path)
			img = img.copy(interpretation='scrgb')
		else:
			raise ValueError(f"unknown hillview:encoding in {source_path}: {encoding!r}")
	if img.get_typeof('icc-profile-data') != 0 and img.format != 'uchar':
		profile_data = img.get('icc-profile-data')
		if _icc_profile_has_linear_trc(profile_data):
			# ICC profile has linear TRC (gamma 1.0). Common with panorama
			# stitching software (Hugin) that uses sRGB primaries but linear encoding.
			# Handle explicitly: normalize to float, mark as linear, let colourspace() apply gamma.
			_dev_only("ICC profile reports linear TRC (gamma 1.0) — interpreting as scene-linear sRGB primaries")
			if img.format == 'ushort':
				img = (img.cast('float') / 65535.0).copy(interpretation='scrgb')
			elif img.format in ('float', 'double'):
				img = img.copy(interpretation='scrgb')
			else:
				img = (img.cast('float') / 255.0).copy(interpretation='scrgb')
			return img.colourspace('srgb')
		try:
			transformed = img.icc_transform('srgb')
			if transformed.format == 'uchar' or transformed.interpretation == 'srgb':
				return transformed
			_dev_only(f"icc_transform returned format={transformed.format} interpretation={transformed.interpretation} — falling through to default handling")
		except pyvips.Error as e:
			_dev_only(f"icc_transform failed ({e}) — falling through to default handling")
	# For 16-bit images without ICC profile, check interpretation.
	# pyvips sets interpretation='rgb16' for gamma-encoded 16-bit sRGB,
	# and interpretation='scrgb' for linear light data.
	if img.format == 'ushort':
		if img.interpretation not in ('rgb16', 'srgb'):
			_dev_only(f"16-bit image with interpretation={img.interpretation} — guessing scene-linear sRGB primaries")
			img = (img.cast('float') / 65535.0).copy(interpretation='scrgb')
		else:
			logging.info(f"16-bit image with interpretation={img.interpretation}, treating as gamma-encoded sRGB")
	img = img.colourspace('srgb')
	return img


def read_image(source_path):
	# Validate file size before processing to prevent memory exhaustion
	try:
		file_size = os.path.getsize(source_path)
		if file_size > security_utils.MAX_FILE_SIZE:
			logging.warning(f"Image file too large for processing: {file_size} bytes")
			raise ValueError(f"Image file too large for processing: {file_size} bytes")
	except OSError:
		logging.warning(f"Could not access image file: {source_path}")
		raise ValueError("Invalid image file path")

	logging.info(f"Reading image: {source_path}")

	# Use pyvips for loading to correctly handle ICC profiles and 16-bit images.
	# cv2.imread silently drops ICC profiles and crudely converts 16→8 bit,
	# causing images with non-sRGB profiles (e.g. linear gamma from stitching
	# software) to appear dark.

	# Narrow the try/except to the pyvips *load* only. Post-processing
	# failures (bad ICC data, missing OpenEXR for tag lookup, vips->numpy
	# conversion) are bugs — surface them instead of silently falling
	# back to cv2 which likely also fails and produces a misleading
	# "pyvips load failed" warning.
	try:
		img = pyvips.Image.new_from_file(source_path)
		img = img.autorot()
	except pyvips.Error as e:
		_dev_only(f"pyvips load failed for {source_path} ({e}) — falling back to cv2 with no color management")
		image = cv2.imread(source_path)
		if image is None:
			logging.warning(f"Could not read image: {source_path}")
			raise ValueError("Invalid image file content")
	else:
		img = normalize_to_srgb(img, source_path=source_path)
		np_img = img.numpy()
		image = cv2.cvtColor(np_img, cv2.COLOR_RGB2BGR)

	# Validate image dimensions to prevent memory exhaustion
	height, width = image.shape[:2]
	if width > security_utils.MAX_IMAGE_DIMENSIONS[0] or height > security_utils.MAX_IMAGE_DIMENSIONS[1] or width * height > security_utils.MAX_IMAGE_PIXELS:
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


def _draw_smiley(img, cx, cy, radius, color, thickness):
	"""Draw a simple smiley face :)"""
	cv2.circle(img, (cx, cy), radius, color, thickness)
	# eyes
	eye_y = cy - radius // 3
	eye_dx = radius // 3
	eye_r = max(1, radius // 8)
	cv2.circle(img, (cx - eye_dx, eye_y), eye_r, color, -1)
	cv2.circle(img, (cx + eye_dx, eye_y), eye_r, color, -1)
	# smile arc
	smile_r = radius // 2
	cv2.ellipse(img, (cx, cy + radius // 6), (smile_r, smile_r // 2),
				0, 10, 170, color, thickness)


def _draw_person(img, x1, y1, x2, y2, color, rng):
	"""Stick figure person with a smiley head."""
	w, h = x2 - x1, y2 - y1
	cx = x1 + w // 2
	t = max(1, min(w, h) // 30)

	head_r = max(3, min(w // 4, h // 6))
	head_cy = y1 + head_r + h // 10
	_draw_smiley(img, cx, head_cy, head_r, color, t)

	# body
	body_top = head_cy + head_r
	body_bot = y1 + int(h * 0.6)
	cv2.line(img, (cx, body_top), (cx, body_bot), color, t)

	# arms — slight random angle
	arm_y = body_top + (body_bot - body_top) // 3
	arm_len = w / 3
	arm_angle = int(rng.integers(-15, 16))
	dy = int(arm_len * 0.3) + arm_angle
	cv2.line(img, (cx, arm_y), (cx - int(arm_len), arm_y + dy), color, t)
	cv2.line(img, (cx, arm_y), (cx + int(arm_len), arm_y - dy), color, t)

	# legs
	leg_len = h - (body_bot - y1)
	leg_dx = w // 5
	cv2.line(img, (cx, body_bot), (cx - leg_dx, y2 - 2), color, t)
	cv2.line(img, (cx, body_bot), (cx + leg_dx, y2 - 2), color, t)


def _draw_car(img, x1, y1, x2, y2, color, rng):
	"""Childlike car with wheels and a smiley in the window."""
	w, h = x2 - x1, y2 - y1
	t = max(1, min(w, h) // 30)

	# body rectangle (lower 60%)
	body_top = y1 + int(h * 0.35)
	cv2.rectangle(img, (x1 + t, body_top), (x2 - t, y2 - int(h * 0.15)), color, t)

	# roof / cabin (trapezoid-ish)
	roof_l = x1 + w // 4
	roof_r = x1 + int(w * 0.75)
	pts = np.array([
		[roof_l, body_top],
		[roof_l + w // 8, y1 + int(h * 0.1)],
		[roof_r - w // 8, y1 + int(h * 0.1)],
		[roof_r, body_top],
	], dtype=np.int32)
	cv2.polylines(img, [pts], True, color, t)

	# wheels
	wheel_r = max(3, h // 8)
	wheel_y = y2 - int(h * 0.12)
	cv2.circle(img, (x1 + w // 4, wheel_y), wheel_r, color, t)
	cv2.circle(img, (x1 + int(w * 0.75), wheel_y), wheel_r, color, t)

	# smiley in the cabin window
	smiley_r = max(2, min(w, h) // 10)
	smiley_cx = x1 + w // 2
	smiley_cy = y1 + int(h * 0.28)
	_draw_smiley(img, smiley_cx, smiley_cy, smiley_r, color, max(1, t // 2))


def _draw_bicycle(img, x1, y1, x2, y2, color, rng):
	"""Simple bicycle: two wheels, frame triangle, handlebars."""
	w, h = x2 - x1, y2 - y1
	t = max(1, min(w, h) // 30)

	wheel_r = max(3, min(w // 5, h // 4))
	wheel_y = y2 - wheel_r - max(2, h // 10)

	# wheels
	lw_cx = x1 + w // 4
	rw_cx = x1 + int(w * 0.75)
	cv2.circle(img, (lw_cx, wheel_y), wheel_r, color, t)
	cv2.circle(img, (rw_cx, wheel_y), wheel_r, color, t)

	# frame: seat post to pedal area to front
	seat_x, seat_y = x1 + int(w * 0.4), y1 + int(h * 0.3)
	pedal_x, pedal_y = x1 + w // 2, wheel_y
	cv2.line(img, (seat_x, seat_y), (pedal_x, pedal_y), color, t)
	cv2.line(img, (pedal_x, pedal_y), (rw_cx, wheel_y), color, t)
	cv2.line(img, (seat_x, seat_y), (rw_cx, wheel_y), color, t)
	cv2.line(img, (pedal_x, pedal_y), (lw_cx, wheel_y), color, t)

	# handlebar
	hb_x = rw_cx
	hb_y = y1 + int(h * 0.25)
	cv2.line(img, (rw_cx, wheel_y), (hb_x, hb_y), color, t)
	cv2.line(img, (hb_x - w // 8, hb_y), (hb_x + w // 8, hb_y), color, t)

	# seat
	cv2.line(img, (seat_x - w // 10, seat_y), (seat_x + w // 10, seat_y), color, t)


def _draw_motorcycle(img, x1, y1, x2, y2, color, rng):
	"""Motorcycle: like bicycle but beefier, with a smiley rider."""
	w, h = x2 - x1, y2 - y1
	t = max(1, min(w, h) // 25)

	wheel_r = max(3, min(w // 5, h // 4))
	wheel_y = y2 - wheel_r - max(2, h // 10)

	# wheels (filled spokes look)
	lw_cx = x1 + w // 4
	rw_cx = x1 + int(w * 0.75)
	cv2.circle(img, (lw_cx, wheel_y), wheel_r, color, t)
	cv2.circle(img, (rw_cx, wheel_y), wheel_r, color, t)

	# body — thick bar between wheels
	body_y = wheel_y - wheel_r // 2
	cv2.line(img, (lw_cx, body_y), (rw_cx, body_y), color, t * 2)

	# handlebars
	hb_y = y1 + int(h * 0.35)
	cv2.line(img, (rw_cx, body_y), (rw_cx + w // 10, hb_y), color, t)

	# tiny smiley rider
	rider_r = max(2, min(w, h) // 10)
	rider_cx = x1 + int(w * 0.5)
	rider_cy = y1 + int(h * 0.2)
	_draw_smiley(img, rider_cx, rider_cy, rider_r, color, max(1, t // 2))
	# rider body to seat
	cv2.line(img, (rider_cx, rider_cy + rider_r), (rider_cx, body_y), color, max(1, t // 2))


def _draw_bus(img, x1, y1, x2, y2, color, rng):
	"""Big boxy bus with windows and wheels."""
	w, h = x2 - x1, y2 - y1
	t = max(1, min(w, h) // 30)

	# main box
	margin = t + 1
	cv2.rectangle(img, (x1 + margin, y1 + margin), (x2 - margin, y2 - int(h * 0.15)), color, t)

	# windows — row of small rectangles
	win_top = y1 + int(h * 0.2)
	win_bot = y1 + int(h * 0.5)
	n_windows = max(2, w // (h // 3 + 1))
	win_w = max(4, (w - margin * 4) // n_windows)
	for i in range(n_windows):
		wx = x1 + margin * 2 + i * (win_w + margin)
		if wx + win_w > x2 - margin * 2:
			break
		cv2.rectangle(img, (wx, win_top), (wx + win_w, win_bot), color, max(1, t // 2))

	# wheels
	wheel_r = max(3, h // 8)
	wheel_y = y2 - int(h * 0.1)
	cv2.circle(img, (x1 + w // 5, wheel_y), wheel_r, color, t)
	cv2.circle(img, (x1 + int(w * 0.8), wheel_y), wheel_r, color, t)

	# smiley in first window
	if n_windows >= 1:
		sr = max(2, (win_bot - win_top) // 3)
		sx = x1 + margin * 2 + win_w // 2
		sy = (win_top + win_bot) // 2
		_draw_smiley(img, sx, sy, sr, color, max(1, t // 3))


def _draw_truck(img, x1, y1, x2, y2, color, rng):
	"""Truck with cab and cargo box."""
	w, h = x2 - x1, y2 - y1
	t = max(1, min(w, h) // 30)

	# cargo box (rear 60%)
	cargo_l = x1 + t
	cargo_r = x1 + int(w * 0.6)
	cargo_t = y1 + int(h * 0.15)
	cargo_b = y2 - int(h * 0.18)
	cv2.rectangle(img, (cargo_l, cargo_t), (cargo_r, cargo_b), color, t)

	# cab (front 35%)
	cab_l = cargo_r
	cab_r = x2 - t
	cab_t = y1 + int(h * 0.3)
	cv2.rectangle(img, (cab_l, cab_t), (cab_r, cargo_b), color, t)

	# window in cab
	win_margin = max(2, t)
	cv2.rectangle(img, (cab_l + win_margin, cab_t + win_margin),
				  (cab_r - win_margin, cab_t + (cargo_b - cab_t) // 2), color, max(1, t // 2))

	# wheels
	wheel_r = max(3, h // 8)
	wheel_y = y2 - int(h * 0.12)
	cv2.circle(img, (x1 + w // 5, wheel_y), wheel_r, color, t)
	cv2.circle(img, (x1 + int(w * 0.8), wheel_y), wheel_r, color, t)

	# smiley in cab window
	sr = max(2, min(w, h) // 12)
	sx = (cab_l + cab_r) // 2
	sy = cab_t + (cargo_b - cab_t) // 3
	_draw_smiley(img, sx, sy, sr, color, max(1, t // 3))


_DRAW_FUNCTIONS = {
	"person": _draw_person,
	"bicycle": _draw_bicycle,
	"car": _draw_car,
	"motorcycle": _draw_motorcycle,
	"bus": _draw_bus,
	"truck": _draw_truck,
}


def apply_blur(source_path, image, detections):
	"""Replace detected regions with a pretty-color block and a childlike
	stick-figure icon representing the detected object class."""

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

		# background fill — pretty color matched to ROI brightness
		bg_color = _random_pretty_color(rng, roi_hue_deg)
		bg_brightness = 0.114 * bg_color[0] + 0.587 * bg_color[1] + 0.299 * bg_color[2]
		if bg_brightness > 0:
			scale = avg_brightness / bg_brightness
			bg_color = np.clip(bg_color * scale, 0, 255)
		image[y1:y2, x1:x2] = bg_color.astype(np.uint8)

		# draw stick-figure icon in a contrasting color
		icon_color = _random_pretty_color(rng)
		# ensure the icon contrasts with the background
		icon_brightness = 0.114 * icon_color[0] + 0.587 * icon_color[1] + 0.299 * icon_color[2]
		bg_lum = 0.114 * bg_color[0] + 0.587 * bg_color[1] + 0.299 * bg_color[2]
		# push icon toward light if bg is dark, and vice versa
		if bg_lum > 128:
			target_brightness = max(30, bg_lum - 100)
		else:
			target_brightness = min(225, bg_lum + 100)
		if icon_brightness > 0:
			icon_scale = target_brightness / icon_brightness
			icon_color = np.clip(icon_color * icon_scale, 0, 255)
		ic = tuple(int(c) for c in icon_color)

		label = TARGET_CLASSES.get(cls_id, "unknown")
		draw_fn = _DRAW_FUNCTIONS.get(label)
		if draw_fn:
			draw_fn(image, x1, y1, x2, y2, ic, rng)

		logging.info(f"Colored over {label} at ({x1},{y1})-({x2},{y2})")


def apply_blackout(image, detections):
	"""Fill detected regions with black for LLM analysis (no colors, no stick figures)."""
	for det in detections:
		x1 = det['bbox']['x1']
		y1 = det['bbox']['y1']
		x2 = det['bbox']['x2']
		y2 = det['bbox']['y2']

		x1, y1 = max(0, x1), max(0, y1)
		x2, y2 = min(x2, image.shape[1]), min(y2, image.shape[0])

		if x2 <= x1 or y2 <= y1:
			continue

		image[y1:y2, x1:x2] = 0
		logging.info(f"Blacked out detection at ({x1},{y1})-({x2},{y2})")
