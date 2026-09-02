"""
photo processing service
"""
import asyncio
import contextlib
import os
import pathlib
import json
import logging
import re
import subprocess
import shlex
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID
from datetime import datetime, timezone, timedelta
import cv2
import numpy as np
from PIL import Image
import httpx
from blur import read_image, apply_blackout, normalize_to_srgb
from detections import should_blur
from throttle import Throttle
from pydantic import BaseModel
from common.security_utils import sanitize_filename, validate_file_path, check_file_content, validate_image_dimensions, SecurityValidationError, validate_user_id, IMAGE_TOOL_TIMEOUT
import processing_state
from common.cdn_uploader import cdn_uploader
from common.config import get_pics_url


logger = logging.getLogger(__name__)

os.environ["OPENCV_IMGCODECS_WEBP_MAX_FILE_SIZE"] = "209715200"  # 200MB

PICS_URL = get_pics_url()
PARALLEL_PROCESSING_START_DELAY = float(os.environ.get("PARALLEL_PROCESSING_START_DELAY", 5))
logger.info(f"PARALLEL_PROCESSING_START_DELAY={PARALLEL_PROCESSING_START_DELAY} seconds")

LLM_VARIANT_SIZE = 640
WEBP_QUALITY_SIZES = 97
WEBP_QUALITY_DZI = 97
NORMAL_WEBP_METHOD = 6
# The worker's own DZI pyramid parameters — also the bar an external pyramid
# must meet on the prod path (see external_pyramid_usable), so they are kept
# in LOCKSTEP with the pics pipeline's src/lib/pyramid_params.py. Effort 2
# (not libvips' default 4): benchmarked 2026-08-18 on the 4.43 Gpx pano
# (scripts/pano/pyramid_bench.2026-08-18.pano1-full.jsonl) — effort is pure
# CPU, derived variants identical to 0.1 dB and bytes within 3% across 0..6,
# while CPU is 87/116/210 s per Gpx at effort 0/2/4; effort 2 halves the
# encode for ~0.5% more bytes. Note the size VARIANTS keep their own method
# logic (NORMAL_WEBP_METHOD / FAST_WEBP_METHOD_*): the partition-0 overflow
# guard there is about single large images, tiles are 1 MP and never near it.
DZI_TILE_SIZE = 1024
DZI_OVERLAP = 1
DZI_FORMAT = 'webp'
DZI_WEBP_EFFORT = 2
# WebP method: 0 = fastest, 6 = slowest/best compression. For fast encoding we
# pick per-variant based on output pixel count: 1 is noticeably quicker than
# 2, but it overflows partition 0 (libwebp error 6) on large images because
# fast methods don't bother optimizing partition layout. ~45 MP (8192×5462,
# the 'full' variant of a 5DS shot) is enough to trip it; 25 MP threshold
# leaves the smaller variants on the fast path.
FAST_WEBP_METHOD_SMALL = 1
FAST_WEBP_METHOD_LARGE = 2
FAST_WEBP_LARGE_THRESHOLD_PIXELS = 5000 * 5000


def _fast_webp_method_for(width: int, height: int) -> int:
	return FAST_WEBP_METHOD_LARGE if width * height >= FAST_WEBP_LARGE_THRESHOLD_PIXELS else FAST_WEBP_METHOD_SMALL


def _save_webp(rgb_array, output_path: str, quality: int, method: int) -> None:
	"""Save an RGB numpy array as WebP, re-raising encoding errors with diagnostics.

	libwebp returns opaque numeric errors (e.g. "encoder error 6") via PIL.
	Error 6 (VP8_ENC_ERROR_PARTITION0_OVERFLOW) is the one we hit in --fast
	mode: methods 1-2 don't optimize the frame header layout, and on large/
	complex images partition 0 won't fit in libwebp's 512KB cap. The fix is
	either bump the encoding method (raise FAST_WEBP_LARGE_THRESHOLD_PIXELS
	threshold's ceiling, or drop --fast) or shrink the image.
	"""
	h, w = rgb_array.shape[:2]
	try:
		Image.fromarray(rgb_array).save(output_path, format='WEBP', quality=quality, method=method)
	except OSError as e:
		msg = str(e)
		if 'encoder error 6' in msg:
			raise OSError(
				f"WebP partition 0 overflow saving {w}x{h} (~{w*h/1e6:.1f} MP) at "
				f"method={method}, quality={quality}. Fast methods can't pack the "
				f"frame header into 512KB on images this size. Lower "
				f"FAST_WEBP_LARGE_THRESHOLD_PIXELS in photo_processor.py so this "
				f"variant uses method>=2, or re-run without --fast. Path: {output_path}"
			) from e
		raise OSError(
			f"WebP save failed for {w}x{h} at method={method}, quality={quality}: {msg}. "
			f"Path: {output_path}"
		) from e


def _assert_output_base_owned(output_base: str, photo_id) -> None:
	"""Guard against cross-job output roots (the 2026-08-03 clobber class).

	Per-job work dirs are named ``{photo_id}-{suffix}`` and live under
	``.../work/`` (see app.process). If ``output_base`` is such a dir, it must
	be THIS job's: another photo's id there means per-job state leaked between
	concurrent pool threads again (e.g. via an attribute on the shared
	photo_processor singleton) — this job's files would land in a dir whose
	owner rmtree's it on completion. The leak is deterministic on job overlap
	(only the downstream ENOENT was intermittent), so failing loud here catches
	the whole class at its first occurrence. Shared roots (the default
	upload_dir) have no ``work/`` parent and are exempt — they are shared by
	design.
	"""
	if not photo_id:
		return
	base = os.path.normpath(output_base)
	if os.path.basename(os.path.dirname(base)) != 'work':
		return
	owner = os.path.basename(base).rsplit('-', 1)[0]  # strip the random hex suffix
	if owner != str(photo_id):
		raise RuntimeError(
			f"output_base {output_base!r} is another job's work dir "
			f"(this photo_id={photo_id}): per-job state leaked across pool threads")


def external_pyramid_usable(keep_pics_in_worker: bool, blur_applied: bool, dzi: Dict[str, Any],
                            required: Dict[str, Any]) -> Tuple[bool, str]:
	"""May an externally rendered pyramid (e.g. the pano pipeline's phase_13
	output) be served for this photo instead of one the worker renders itself?

	Returns (usable, reason). Three layers, in order:

	1. Anonymization — same on every path. An external pyramid is pre-blur, so
	   if this photo's size variants were blurred at all, serving it would leak
	   exactly what anonymization hid. ``blur_applied`` is the RESOLVED
	   answer (computed from the final detections after processing), which is
	   why this is decided here and not at request time: the effective blur
	   set is empty for skip ("[]"), for precomputed detections with zero
	   blurred objects, for empty manual rects AND for auto-detect that found
	   nothing; non-empty for auto-detect with hits, precomputed with any
	   blurred, non-empty manual rects. Only the resolved detections know.

	2. Prod path (keep_pics_in_worker=False: artifacts ship to the API's pool)
	   is STRICT: the pyramid must have been built with the parameters prod
	   would have used for this job — descriptor TileSize/Overlap/Format, plus
	   WebP Q/effort, which a .dzi does not record, so they must be positively
	   attested by a ``<prefix>.dzi.params.json`` sidecar written by whoever
	   rendered the pyramid ({"tile_size","overlap","format","q","effort"}).
	   No sidecar ⇒ not usable. This is the real danger direction: an aux
	   worker on a dev box has the LOCAL_PHOTO_ROOTS mounts AND ships to prod.

	3. Dev path (keep_pics_in_worker=True: served from this worker's own
	   volume / the archive mount, never leaves the box) accepts any pyramid
	   whose descriptor matches the photo's dimensions (checked by the caller).
	"""
	if blur_applied:
		return False, "anonymization blurred this photo; a pre-blur external pyramid would leak it"
	if keep_pics_in_worker:
		return True, "dev preview: served from this worker, any dims-matching pyramid accepted"
	for key in ('tile_size', 'overlap', 'format'):
		if dzi.get(key) != required.get(key):
			return False, f"prod path requires {key}={required.get(key)!r}, pyramid has {dzi.get(key)!r}"
	params = dzi.get('params')
	if not params:
		return False, "prod path requires a <prefix>.dzi.params.json sidecar attesting q/effort; none found"
	for key in ('q', 'effort'):
		if params.get(key) != required.get(key):
			return False, f"prod path requires {key}={required.get(key)!r}, pyramid params attest {params.get(key)!r}"
	return True, "prod path: pyramid parameters match what this worker would have used"


def _override_blur_free(override: Optional["AnonymizationOverride"]) -> Optional[bool]:
	"""Can we tell, BEFORE decoding, that anonymization will blur nothing?

	True: skip ("[]"); precomputed detections with no object to blur; an empty
	manual-rects list. False: precomputed with something to blur; non-empty
	manual rects. None: auto-detect — unknowable until the detector has run
	on the pixels (decided later from the resolved detections).
	"""
	if override is None:
		return None
	if override.detections is not None:
		return not any(o.get('blurred', should_blur(o)) for o in (override.detections.get('objects') or []))
	if override.skip_anonymization:
		return True
	return not any(None not in (r.get('x'), r.get('y'), r.get('width'), r.get('height')) for r in override.rectangles)


class _timed:
	"""Log wall + process-CPU seconds for a processing step, so real pano
	runs tell us where the time goes before we tune anything (encode effort,
	tile size, transfer parallelism...). CPU is process-wide (all vips /
	libwebp threads), so wall << cpu means the step parallelized.

	Use as a context manager, or ``t = _timed(...); ...; t.done()`` around
	blocks that are awkward to indent (loops with awaits)."""

	def __init__(self, label: str, unique_id: str = ''):
		import time
		self._time = time
		self.label, self.unique_id = label, unique_id
		self.t0, self.c0 = time.monotonic(), time.process_time()

	def done(self, extra: str = '') -> None:
		# process_time is process-wide and the pool is one process x N threads
		# (vips/libwebp on their own thread pools, so per-thread CPU would
		# undercount instead): with other jobs in flight their CPU lands in
		# this number too. Log how many jobs this process had in flight so such
		# samples are recognizable — 'concurrent 1' means the cpu figure is
		# clean. (processing_state's own table is empty in the pool child; its
		# updates are piped to the parent — hence worker_processing's counter.)
		try:
			import worker_processing
			concurrent = worker_processing.child_inflight()
		except Exception:
			concurrent = -1
		logger.info(f"[timing] {self.label} for {self.unique_id}: wall {self._time.monotonic() - self.t0:.1f}s, "
		            f"cpu {self._time.process_time() - self.c0:.1f}s (concurrent {concurrent})"
		            f"{(' ' + extra) if extra else ''}")

	def __enter__(self):
		return self

	def __exit__(self, *exc):
		self.done()


def _validate_input_path(filepath: str) -> str:
	"""Validate an input image path for external-tool use: under /app (the
	uploaded copy in the work dir), or under EXTERNAL_DATA_DIR (no-upload
	ingestion — client-named trees bind-mounted read-only, see local_photos).

	The external case is a lexical prefix check, deliberately NOT realpath: the
	path was already resolved hop-by-hop by local_photos.resolve_local_photo_path
	(the only way one is ever produced), and realpath would follow the archive's
	absolute HOST-path symlinks, which do not exist in container space.
	"""
	from local_photos import EXTERNAL_DATA_DIR
	norm = os.path.normpath(filepath)
	if norm.startswith(EXTERNAL_DATA_DIR + '/'):
		return norm
	return validate_file_path(filepath, "/app")


def create_center_crop(image, target_width: int, target_height: int):
	"""Resize and center-crop an image to exact target dimensions.

	Scales the image so the smaller dimension matches the target,
	then center-crops the larger dimension.

	Args:
		image: BGR numpy array (from cv2)
		target_width: Desired output width in pixels
		target_height: Desired output height in pixels

	Returns:
		Cropped BGR numpy array of exactly (target_height, target_width).
	"""
	h, w = image.shape[:2]
	# Scale so that the dimension that would be cropped fills the target
	scale = max(target_width / w, target_height / h)
	# Use round() instead of int() to avoid floating-point truncation
	# (e.g. int(7 * (240/7)) = 239 due to IEEE 754), then clamp to at
	# least target dimensions so the center-crop slice is never short.
	new_w = max(target_width, round(w * scale))
	new_h = max(target_height, round(h * scale))
	resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
	x_start = (new_w - target_width) // 2
	y_start = (new_h - target_height) // 2
	return resized[y_start:y_start + target_height, x_start:x_start + target_width]


class AnonymizationOverride(BaseModel):
	"""Controls anonymization behavior.

	- None (not provided): auto-detect faces/plates and blur them
	- Empty list []: skip anonymization entirely
	- List of rectangles: blur specific areas (future feature)
	- Dict with an "objects" key: PRECOMPUTED detections — the
	  detected_objects value from a previous processing of the same image
	  bytes (e.g. copied from a dev server by the pics pipeline's
	  apply_dev_ratings.py). The objects whose ``blurred`` flag (or the
	  ``should_blur`` fallback for legacy entries) says so are blurred with
	  their real class_ids (stick figures preserved), and the dict is
	  persisted to ``detected_objects`` VERBATIM — class names, confidences,
	  model_name and sub-threshold near-misses all survive for future
	  re-anonymization / threshold tuning.
	"""
	rectangles: List[Dict[str, int]] = []  # Each dict: {x, y, width, height}
	detections: Optional[Dict[str, Any]] = None  # verbatim detected_objects dict

	@classmethod
	def from_json_string(cls, json_str: Optional[str]) -> Optional["AnonymizationOverride"]:
		"""Parse from JSON string (as received from form field)."""
		if json_str is None:
			return None
		try:
			data = json.loads(json_str)
			if isinstance(data, list):
				return cls(rectangles=data)
			elif isinstance(data, dict):
				if "objects" in data:
					return cls(detections=data)
				return cls(**data)
			else:
				logger.warning(f"Invalid anonymization_override type: {type(data)}")
				return None
		except json.JSONDecodeError as e:
			logger.warning(f"Invalid anonymization_override JSON: {e}")
			return None

	@property
	def skip_anonymization(self) -> bool:
		"""Returns True if anonymization should be skipped (empty rectangles
		list and no precomputed detections)."""
		return self.detections is None and len(self.rectangles) == 0


# Canonical definition lives in exceptions.py (lightweight module) so that
# app.py can catch this without importing photo_processor at startup.
from exceptions import PhotoDeletedException, PoolMigrationError


def safe_parse_float(value, field_name: str = "value") -> Optional[float]:
	"""Safely parse a numeric value from exiftool output.

	Exiftool returns 'undef' when tags exist but can't be parsed
	(e.g., malformed EXIF from format conversions like CR2->TIFF).
	"""
	if value is None:
		return None
	if isinstance(value, (int, float)):
		return float(value)
	if isinstance(value, str):
		val_lower = value.lower().strip()
		if val_lower in ('undef', 'undefined', '', 'nan', 'inf', '-inf', 'infinity', '-infinity'):
			logger.debug(f"Exiftool returned '{value}' for {field_name}, treating as None")
			return None
		try:
			return float(value)
		except ValueError:
			logger.warning(f"Could not parse exiftool value '{value}' as float for {field_name}")
			return None
	logger.warning(f"Unexpected type {type(value).__name__} for {field_name}: {value}")
	return None


def _parse_exif_offset(offset_value) -> Optional[timedelta]:
	"""Parse an EXIF OffsetTime tag ('+01:00', '-05:00', 'Z') to a timedelta.

	Returns None if absent/unparseable so the caller can fall back to assuming UTC.
	"""
	if offset_value is None:
		return None
	s = str(offset_value).strip()
	if s in ('Z', 'z'):
		return timedelta(0)
	m = re.match(r"([+-])(\d{2}):?(\d{2})$", s)
	if not m:
		return None
	sign = 1 if m.group(1) == '+' else -1
	return timedelta(minutes=sign * (int(m.group(2)) * 60 + int(m.group(3))))


PROVENANCE_KEYS = (
	'location_source', 'bearing_source', 'alt_location',
	# From the Android fast-write path, which skips the on-device EXIF
	# rewrite and carries the whole stamp in the upload metadata instead —
	# so the synthesized UserComment must say what a written one would.
	'location_age_ms', 'exposure', 'refined',
	'v',
)


def synthesize_provenance(metadata: Optional[dict]) -> Optional[str]:
	"""The UserComment an uploader could not write into the file itself.

	Browser captures cannot write EXIF at all, and the Android fast-write
	path deliberately does not (the rewrite is the throughput cost it
	exists to avoid), so for both the upload metadata is the only carrier.
	Extracted from process() to be testable: which keys survive this hop is
	a contract with the pics pipeline, not an implementation detail.

	Returns None when there is nothing to say, so the caller leaves any
	genuinely embedded UserComment alone.
	"""
	if not metadata:
		return None
	provenance = {k: metadata[k] for k in PROVENANCE_KEYS if metadata.get(k) is not None}
	return json.dumps(provenance) if provenance else None


def parse_exif_datetime(value, offset_value=None) -> Optional[datetime]:
	"""Parse EXIF datetime value and fix corrupted timestamps.

	Handles the bug where milliseconds were written as seconds, causing
	dates like "+58074:03:14 04:05:17". Detects years > 2100 and fixes
	by dividing the timestamp by 1000.

	Returns a UTC datetime. EXIF DateTimeOriginal is a naive local wall-clock; if
	offset_value (OffsetTimeOriginal, e.g. '+01:00') is given, the wall-clock is
	converted to UTC. Without an offset we assume the value is already UTC (true for
	the unix-ms path; best-effort otherwise).
	"""
	if value is None:
		return None

	# If it's already a numeric timestamp (exiftool -n can return these)
	if isinstance(value, (int, float)):
		ts = float(value)
		# Check if this looks like milliseconds (year > 2100)
		if ts > 4102444800:  # 2100-01-01 in seconds
			ts = ts / 1000
		return datetime.fromtimestamp(ts, tz=timezone.utc)

	# String format - try to parse
	value_str = str(value)

	# Handle the corrupted format like "+58074:03:14 04:05:17"
	# Strip leading + if present
	if value_str.startswith('+'):
		value_str = value_str[1:]

	# Common EXIF datetime formats
	formats = [
		"%Y:%m:%d %H:%M:%S",      # Standard EXIF: 2024:01:15 10:30:45
		"%Y-%m-%d %H:%M:%S",      # ISO-ish: 2024-01-15 10:30:45
		"%Y:%m:%d %H:%M:%S.%f",   # With subseconds
		"%Y-%m-%dT%H:%M:%S",      # ISO: 2024-01-15T10:30:45
		"%Y-%m-%dT%H:%M:%S.%f",   # ISO with subseconds
		"%Y-%m-%dT%H:%M:%SZ",     # ISO UTC
		"%Y-%m-%dT%H:%M:%S.%fZ",  # ISO UTC with subseconds (upload metadata's ms-ISO shape)
	]

	# A trailing Z means the value declares itself UTC — it is not a naive
	# wall-clock, so the file's OffsetTimeOriginal must NOT be applied to it.
	# This matters since metadata captured_at overwrites DateTimeOriginal:
	# an EXIF-writing client also stamps a local-time offset, and applying
	# that offset to an already-UTC value shifted it by the timezone.
	value_is_utc = value_str.endswith('Z')

	for fmt in formats:
		try:
			dt = datetime.strptime(value_str, fmt)
			# Check if year is unreasonably large (corrupted timestamp)
			if dt.year > 2100:
				# This was milliseconds interpreted as seconds
				# Convert back: parse to timestamp, divide by 1000
				ts = dt.timestamp()
				corrected_ts = ts / 1000
				corrected_dt = datetime.fromtimestamp(corrected_ts, tz=timezone.utc)
				logger.info(f"Fixed corrupted DateTimeOriginal: {value} -> {corrected_dt.isoformat()}")
				return corrected_dt
			# DateTimeOriginal is local wall-clock; convert to UTC using the EXIF
			# offset when known, else assume it is already UTC.
			offset = _parse_exif_offset(offset_value) if not value_is_utc else None
			if offset is not None:
				return (dt - offset).replace(tzinfo=timezone.utc)
			return dt.replace(tzinfo=timezone.utc)
		except ValueError:
			continue

	logger.warning(f"Could not parse DateTimeOriginal: {value}")
	return None


throttle = Throttle('photo_processor')

class PhotoProcessor:
	"""Unified photo processing service for uploads."""


	def __init__(self, upload_dir: str = "/app/uploads"):
		self.upload_dir = upload_dir


	def extract_exif_data(self, filepath: str) -> Dict[str, Any]:
		"""Extract EXIF data including GPS and bearing information using known-good implementation."""
		logger.info(f"Processing EXIF data from {filepath}")

		result = {
			'exif': {},
			'gps': {},
			'debug': {
				'has_exif': False,
				'has_gps_coords': False,
				'has_bearing': False,
				'found_gps_tags': [],
				'found_bearing_tags': [],
				'parsing_errors': []
			}
		}

		# First try exifread
		# try:
		# 	with open(filepath, 'rb') as f:
		# 		tags = exifread.process_file(f, details=True, debug=False)
		#
		# 	if len(tags) > 0:
		# 		result['debug']['has_exif'] = True
		# 		logger.info(f"EXIF tags found: {len(tags)} tags")
		# 		logger.info(f"All EXIF tags: {[str(tag) for tag in tags.keys()]}")
		#
		# 		# Extract basic EXIF data
		# 		exif_dict = {}
		# 		for tag in tags.keys():
		# 			if tag not in ('JPEGThumbnail', 'TIFFThumbnail', 'Filename', 'EXIF MakerNote'):
		# 				exif_dict[tag] = str(tags[tag])
		# 		result['exif'] = exif_dict
		#
		# 		gps_data = {}
		# 		bearing = None
		# 		latitude = tags.get('GPS GPSLatitude')
		# 		longitude = tags.get('GPS GPSLongitude')
		#
		# 		# Track what GPS tags we found
		# 		if latitude:
		# 			result['debug']['found_gps_tags'].append('GPS GPSLatitude')
		# 		if longitude:
		# 			result['debug']['found_gps_tags'].append('GPS GPSLongitude')
		#
		# 		# Check bearing data (any one of the possible keys) - independent of coordinates
		# 		bearing_keys = ['GPS GPSImgDirection', 'GPS GPSTrack', 'GPS GPSDestBearing']
		# 		for key in bearing_keys:
		# 			if key in tags:
		# 				bearing = tags.get(key)
		# 				result['debug']['found_bearing_tags'].append(key)
		# 				result['debug']['has_bearing'] = True
		# 				break
		#
		# 		if latitude and longitude:
		# 			result['debug']['has_gps_coords'] = True
		#
		# 			if bearing:
		#
		# 				try:
		# 					altitude = tags.get('GPS GPSAltitude')
		# 					logger.info(f"Found GPS data via exifread")
		#
		# 					# Convert coordinates to decimal degrees
		# 					lat = self._convert_to_degrees(latitude)
		# 					lon = self._convert_to_degrees(longitude)
		#
		# 					# Apply hemisphere corrections
		# 					lat_ref = tags.get('GPS GPSLatitudeRef')
		# 					lon_ref = tags.get('GPS GPSLongitudeRef')
		# 					if lat_ref and str(lat_ref).upper().startswith('S'):
		# 						lat = -lat
		# 					if lon_ref and str(lon_ref).upper().startswith('W'):
		# 						lon = -lon
		#
		# 					gps_data['latitude'] = lat
		# 					gps_data['longitude'] = lon
		# 					gps_data['bearing'] = float(str(bearing).split('/')[0]) if '/' in str(bearing) else float(str(bearing))
		# 					if altitude:
		# 						gps_data['altitude'] = float(str(altitude).split('/')[0]) if '/' in str(altitude) else float(str(altitude))
		#
		# 					result['gps'] = gps_data
		# 					return result
		# 				except Exception as e:
		# 					result['debug']['parsing_errors'].append(f"GPS parsing failed: {e}")
		# 					logger.debug(f"GPS parsing failed: {e}")
		# except Exception as e:
		# 	result['debug']['parsing_errors'].append(f"exifread failed: {e}")
		# 	logger.debug(f"exifread failed: {e}")

		# Fallback to exiftool
		try:
			# Validate filepath before passing to external tool
			try:
				validated_filepath = _validate_input_path(filepath)
			except SecurityValidationError as e:
				result['debug']['parsing_errors'].append(f"Path validation failed for exiftool: {e}")
				logger.debug(f"Path validation failed for exiftool: {e}")
				return result

			# EXR carries no EXIF; geo/captured_at arrive via the upload
			# metadata blob and merge downstream. Skipping exiftool here also
			# keeps one parser away from untrusted input for this format.
			if validated_filepath.lower().endswith('.exr'):
				logger.info(f"Skipping exiftool for EXR (no EXIF container): {filepath}")
				return result

			# Use -n flag to get raw numeric values instead of formatted strings
			cmd = ['exiftool', '-json', '-n', validated_filepath]
			logger.debug(f"Trying exiftool fallback: {shlex.join(cmd)}")

			proc_result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

			if proc_result.returncode != 0:
				result['debug']['parsing_errors'].append("exiftool command failed")
				logger.debug(f"Error running exiftool: {proc_result.stderr}")
				return result

			data = json.loads(proc_result.stdout)[0]
			result['data'] = data

			# Check for required GPS data (use safe_parse_float to handle 'undef' etc.)
			latitude = safe_parse_float(data.get('GPSLatitude'), 'GPSLatitude')
			longitude = safe_parse_float(data.get('GPSLongitude'), 'GPSLongitude')
			lat_ref = data.get('GPSLatitudeRef')
			lon_ref = data.get('GPSLongitudeRef')

			# Track what we found
			if latitude is not None:
				result['debug']['found_gps_tags'].append('GPSLatitude')
			if longitude is not None:
				result['debug']['found_gps_tags'].append('GPSLongitude')

			if latitude is None or longitude is None:
				result['debug']['has_gps_coords'] = False
				logger.debug("No GPS coordinates found via exiftool.")
			else:
				result['debug']['has_gps_coords'] = True

				# Apply sign based on reference
				if lat_ref == 'S':
					latitude = -abs(latitude)
				if lon_ref == 'W':
					longitude = -abs(longitude)

			# Check bearing data
			bearing_fields = ['GPSImgDirection', 'GPSTrack', 'GPSDestBearing']
			bearing = None
			for field in bearing_fields:
				raw_bearing = data.get(field)
				if raw_bearing is not None:
					bearing = safe_parse_float(raw_bearing, field)
					if bearing is not None:
						result['debug']['found_bearing_tags'].append(field)
						break

			if bearing is None:
				result['debug']['has_bearing'] = False
				logger.debug("No bearing data found via exiftool")
			else:
				result['debug']['has_bearing'] = True

			# Mark as having EXIF data if we found any GPS-related data (coordinates or bearing)
			if result['debug']['found_gps_tags'] or result['debug']['found_bearing_tags']:
				result['debug']['has_exif'] = True

			altitude = safe_parse_float(data.get('GPSAltitude'), 'GPSAltitude')


			# Validate bearing is in valid range [0, 360]
			if bearing is not None and (bearing < 0 or bearing > 360):
				error_msg = f"Invalid bearing value: {bearing}. Must be between 0 and 360 degrees."
				result['debug']['parsing_errors'].append(error_msg)
				logger.error(error_msg)
				raise ValueError(error_msg)

			gps_data = {
				'latitude': latitude,
				'longitude': longitude,
				'bearing': bearing
			}
			if altitude:
				gps_data['altitude'] = altitude

			result['gps'] = gps_data

		except Exception as e:
			result['debug']['parsing_errors'].append(f"exiftool failed: {e}")
			logger.debug(f"Error reading EXIF data from {filepath}: {e}")

		return result


	def _convert_to_degrees(self, value):
		"""Convert GPS coordinates to decimal degrees."""
		d, m, s = value.values
		return float(d) + float(m)/60 + float(s)/3600

	def has_required_gps_data(self, exif_data: Dict[str, Any]) -> bool:
		"""Check if image has required GPS and bearing data."""
		gps = exif_data.get('gps', {})
		return all(key in gps for key in ['latitude', 'longitude', 'bearing'])


	def get_image_dimensions(self, filepath: str, orientation: int
							 ) -> Tuple[int, int]:
		"""Get image dimensions from the file header, without decoding pixels."""
		try:
			# Validate filepath before passing to external tool
			validated_filepath = _validate_input_path(filepath)
		except SecurityValidationError as e:
			logger.debug(f"Path validation failed for identify: {e}")
			return 0, 0

		if validated_filepath.lower().endswith('.exr'):
			# ImageMagick decodes the full EXR raster even for -format '%w %h'
			# (observed: 8.5 min on a 35 GB pano). Read the header directly via
			# OpenEXR instead — blur._exr_encoding already parses the same
			# header on the same files, so this adds no new parser to the
			# untrusted-input surface (and runs in the crash-isolated pool
			# subprocess like everything else here).
			import OpenEXR
			exr = OpenEXR.InputFile(validated_filepath)
			try:
				dw = exr.header()['dataWindow']
				dimensions = [dw.max.x - dw.min.x + 1, dw.max.y - dw.min.y + 1]
			finally:
				exr.close()
		else:
			# -ping: header-only inspection — identify must not decode a whole
			# gigapixel raster to answer width×height.
			cmd = ['identify', '-ping', '-format', '%w %h', validated_filepath]
			output = subprocess.check_output(cmd, timeout=IMAGE_TOOL_TIMEOUT).decode('utf-8')
			dimensions = [int(x) for x in output.split()]
		if orientation in [5, 6, 7, 8]:
			dimensions = [dimensions[1], dimensions[0]]
		logger.debug(f'Image dimensions: {dimensions}')
		return dimensions[0], dimensions[1]


	async def create_optimized_sizes(self, source_path: str, unique_id: str, width: int, height: int, photo_id: str = None, client_signature: str = None, anonymization_override: Optional[AnonymizationOverride] = None, quality: Optional[int] = None, fast: bool = False, encoding: Optional[str] = None,
									 output_base: Optional[str] = None,
									 keep_pics_in_worker: bool = False,
									 local_pyramid_path: Optional[str] = None,
									 ) -> tuple[Dict[str, Dict[str, Any]], Optional[Dict[str, Any]]]:
		"""Create optimized versions with anonymization and unique IDs.

		fast: Skip pyramid, 640_llm, EXIF copy, use fast WebP encoding, reduced size set.
		encoding: EXR pixel encoding ('srgb'/'linear') sourced from upload metadata;
			passed to read_image so it need not read the embedded header tag.
		output_base: per-job output root (see process_uploaded_photo).
		keep_pics_in_worker: serve artifacts from this worker's own uploads
			volume instead of shipping them (see _get_size_url).
		local_pyramid_path: an externally rendered <prefix>.dzi OFFERED by the
			client; the worker decides whether to use it (see the pyramid block).
		"""

		sizes_info = {}
		output_base = output_base or self.upload_dir
		_assert_output_base_owned(output_base, photo_id)
		webp_quality_sizes = quality if quality is not None else WEBP_QUALITY_SIZES
		webp_quality_dzi = quality if quality is not None else WEBP_QUALITY_DZI

		logger.info(f"Starting anonymization for {unique_id} (quality: sizes={webp_quality_sizes}, dzi={webp_quality_dzi}, fast={fast})")

		if not anonymization_override:
			# this takes a while to import, so do it here dynamically
			logger.info(f"Importing anonymization module for {source_path}")
			from anonymize import anonymize_image as _  # noqa: F401
			logger.info(f"Successfully imported anonymization module")

		# Pyramid offer, early decision. If the override PROVES no blur will be
		# applied (skip; precomputed with nothing to blur; empty manual rects)
		# and policy accepts the offered pyramid, every size variant can be
		# derived from its levels and the source is never decoded at all — for
		# a gigapixel EXR that is the whole cost. Auto-detect can't be judged
		# before the detector has run, so that case is decided after step 1.
		ext_pyramid = None          # accepted external pyramid metadata dict
		pyr = None                  # PyramidSource as the variant source — only ever an accepted
		                            # external pyramid on the skip-decode path (see the guard below)
		offer_pending = bool(local_pyramid_path)
		if local_pyramid_path:
			blur_free = _override_blur_free(anonymization_override)
			if blur_free is not None:
				offer_pending = False
				if blur_free:
					ext_pyramid = self._external_pyramid(local_pyramid_path, width, height, False,
					                                     keep_pics_in_worker, quality, unique_id)
				else:
					logger.info(f"External pyramid for {unique_id}: declined before decode — the override blurs")
			if ext_pyramid:
				if width >= 2 * self.FULL_VARIANT_WIDTH:
					from pyramid_source import PyramidSource
					pyr = PyramidSource(local_pyramid_path, ext_pyramid)
					logger.info(f"Deriving all size variants of {unique_id} from the external pyramid; source decode skipped")
				else:
					# Accepted for SERVING only. Deriving variants needs every
					# target to have a >=2x pyramid level (pyramid_source
					# for_width), and the largest target is the 'full' variant
					# at min(width, FULL_VARIANT_WIDTH) — below 2x that,
					# for_width clamps to the full-resolution level and 'full'
					# becomes a ~1x re-encode of WebP tiles, seams included.
					# A photo this small is also cheap to decode, so decode it
					# and let the raster win below: the decode-skip is only
					# taken where it is both needed and harmless.
					logger.info(f"External pyramid for {unique_id}: accepted for serving, but "
					            f"{width}px < 2x{self.FULL_VARIANT_WIDTH} leaves no >=2x level for the "
					            f"'full' variant; decoding the source for the size variants")

		# "decode", not "anonymizing": every branch below starts by decoding the
		# source (read_image — minutes of CPU for a gigapixel EXR), and with
		# skip_anonymization that decode is ALL that happens here. The label
		# flips to "anonymizing" only where detection/blur actually run, so a
		# skip-anonymization pano no longer reports anonymizing(NNNs) while it
		# is really just decoding.
		image = None
		processing_state.set_phase("decode")
		# Admission gating (start stagger + RAM) moved to the parent process —
		# app.wait_admission(), one global instance. This in-child rate_limit
		# became per-process after the worker-pool split (3 independent stagger
		# buckets), and its 1500 MB RAM wait livelocked: every slot waiting for
		# RAM that only a running job could free (observed live 2026-07-13).
		# The parent gate admits a job whenever nothing is running, so it can't
		# deadlock. nullcontext keeps the block shape for a minimal diff.
		async with contextlib.nullcontext():

			if not anonymization_override:
				image, detections = await self._anonymize_image(source_path, encoding=encoding)
			else:
				if anonymization_override.detections is not None:
					# Precomputed detections: reuse another run's rects on the
					# same bytes instead of re-running the detector, and
					# persist the dict verbatim (provenance survives — see
					# AnonymizationOverride). Blur decision per object follows
					# the shared consumer convention (detections.py).
					detections = anonymization_override.detections
					objects = detections.get("objects") or []
					to_blur = [o for o in objects if o.get("blurred", should_blur(o))]
					logger.info(f"Applying precomputed detections for {unique_id}: "
								f"blurring {len(to_blur)}/{len(objects)} objects")
					if pyr is None:
						with _timed('decode', unique_id):
							image = read_image(source_path, encoding=encoding)
					if to_blur:
						processing_state.set_phase("anonymizing")
						from blur import apply_blur
						apply_blur(source_path, image, to_blur)
				elif anonymization_override.skip_anonymization:
					logger.info(f"Skipping anonymization for {unique_id} due to override")
					if pyr is None:
						with _timed('decode', unique_id):
							image = read_image(source_path, encoding=encoding)
					detections = {"objects": [], "manual": True}
				else:
					logger.info(f"Applying manual anonymization for {unique_id} with rectangles: {anonymization_override.rectangles}")
					if pyr is None:
						with _timed('decode', unique_id):
							image = read_image(source_path, encoding=encoding)
					detections = {"objects": [], "manual": True}
					for rect in anonymization_override.rectangles:
						x = rect.get('x')
						y = rect.get('y')
						w = rect.get('width')
						h = rect.get('height')
						if None not in (x, y, w, h):
							detections['objects'].append({
								'class_id': None,
								'bbox': {'x1': x, 'y1': y, 'x2': x+w, 'y2': y+h},
								'blur': 500,
								'blurred': True,  # manual override rects are always blurred
							})
					from blur import apply_blur
					apply_blur(source_path, image, detections['objects'])


			# Use actual image dimensions (may differ from EXIF width/height
			# due to auto-rotation during pyvips loading). Without a decoded
			# raster the header dims stand — the accepted pyramid was checked
			# against exactly those.
			if image is not None:
				height, width = image.shape[:2]

			# Pyramid decision, now that anonymization has resolved: an
			# external offer still pending (auto-detect) is judged on the real
			# detections; without an accepted external pyramid the worker
			# renders its OWN (non-fast, image big enough) — dzsave now, ship
			# after the variants. Neither becomes the variant source here: the
			# raster exists on every path through this block and wins below.
			if offer_pending:
				blur_applied = any(o.get('blurred', should_blur(o)) for o in (detections or {}).get('objects', []))
				ext_pyramid = self._external_pyramid(local_pyramid_path, width, height, blur_applied,
				                                     keep_pics_in_worker, quality, unique_id)
				# The source was decoded on this path (the detector needed it),
				# so the raster is the variant source either way; acceptance
				# only decides which pyramid gets published below.
			own_dzi = None  # (dzi_file, tiles_dir, meta) of a pyramid rendered here, shipped after the variants
			if ext_pyramid is None and not fast and max(width, height) >= self.DZI_MIN_DIMENSION:
				processing_state.set_phase("dzi_pyramid")
				own_dzi = self._render_own_pyramid(image, unique_id, photo_id, quality=quality, output_base=output_base)
			# One pixel source for every variant below. The DECODED RASTER WINS
			# whenever we have one: pyramid levels are already WebP-encoded, so
			# deriving from them costs a second lossy generation, and the ">=2x
			# downscale washes the first one out" argument only holds when such
			# a level exists — for 'full' (scale 1 below 8192 px) and for
			# 4096/3072 on mid-size photos it does not, and the level is the
			# full-resolution one, i.e. a same-size re-encode with tile seams.
			# The pyramid is therefore only the source when the source was
			# never decoded at all (an accepted external pyramid — there the
			# second generation is the price of skipping a gigapixel decode,
			# measured at 0.3-0.8 dB in scripts/pano/pyramid_bench.py), and
			# the acceptance block guarded width >= 2*FULL_VARIANT_WIDTH, so
			# every for_width target below does have its >=2x level. (Crop
			# variants may still clamp on short-and-wide strips — see
			# for_center_crop — accepted for what they are used for.)
			from pyramid_source import RasterSource, scale_bboxes
			src = RasterSource(image, source_path, encoding) if image is not None else pyr

			if fast:
				size_variants = ['full', 320, 1200, 2048]
			else:
				size_variants = ['full', 320, 640, 1200, 2048, 3072, 4096]

			processing_state.set_phase("encode_sizes")
			t_sizes = _timed(f"size variants {size_variants} (source: {type(src).__name__})", unique_id)
			for size in size_variants:

				# skip if size is larger than original width
				if isinstance(size, int) and size > width:
					continue

				user_id_part, photo_id_part = unique_id.split('/', 1)
				user_id_part = validate_user_id(user_id_part)
				size_dir = os.path.join(output_base, 'opt', str(size), user_id_part)
				unique_filename = sanitize_filename(f"{photo_id_part}.webp")
				output_file_path = validate_file_path(os.path.join(size_dir, unique_filename), output_base)
				relative_path = os.path.relpath(output_file_path, output_base)
				os.makedirs(pathlib.Path(output_file_path).parent, exist_ok=True)

				size_info = {'path': relative_path}

				if size == 'full':
					scale = 1 if width <= self.FULL_VARIANT_WIDTH else self.FULL_VARIANT_WIDTH / width
				else:
					scale = size / width

				new_width = int(width * scale)
				new_height = int(height * scale)

				logger.info(f"Creating size {size} for {unique_id}: {new_width}x{new_height} at {output_file_path}")
				# From a pyramid: smallest level >= 2x the target, so the
				# INTER_AREA downscale averages >= 4 source pixels per output
				# pixel and washes out that level's WebP encode (see pyramid_source).
				new_image = cv2.resize(src.for_width(new_width), (new_width, new_height), interpolation=cv2.INTER_AREA)
				logger.debug(f"Resized image to {new_width}x{new_height} for size {size}")
				new_image_rgb = cv2.cvtColor(new_image, cv2.COLOR_BGR2RGB)
				logger.debug(f"Converted image to RGB color space for size {size}")
				webp_method = _fast_webp_method_for(new_width, new_height) if fast else NORMAL_WEBP_METHOD
				_save_webp(new_image_rgb, output_file_path, webp_quality_sizes, webp_method)
				if not fast:
					copy_exif_data(source_path, output_file_path)
				logger.info(f"Created size {size} for {unique_id}: {new_width}x{new_height} at {output_file_path}")

				size_info.update({
					'width': new_width,
					'height': new_height,
					'url': await self._get_size_url(output_file_path, relative_path, photo_id, client_signature, keep_pics_in_worker=keep_pics_in_worker)
				})
				sizes_info[size] = size_info
			t_sizes.done()

		# Create cropped thumbnail variants for images wider than the target aspect ratio
		t_crops = _timed("crop variants", unique_id)
		crop_variants = [
			('320_crop', 320, 240),
			('1200_crop', 1200, 630),
			('3840_crop', 3840, 2016),  # large representative crop for image search (sitemap <image:loc>)
		]  # (key, width, height)
		for crop_key, crop_tw, crop_th in crop_variants:
			if crop_th > height:
				continue  # source too short — create_center_crop would upscale
			if height > 0 and width / height > crop_tw / crop_th:
				cropped = create_center_crop(src.for_center_crop(crop_tw, crop_th), crop_tw, crop_th)

				user_id_part, photo_id_part = unique_id.split('/', 1)
				user_id_part = validate_user_id(user_id_part)
				crop_dir = os.path.join(output_base, 'opt', crop_key, user_id_part)
				unique_filename = sanitize_filename(f"{photo_id_part}.webp")
				crop_file_path = validate_file_path(os.path.join(crop_dir, unique_filename), output_base)
				crop_relative_path = os.path.relpath(crop_file_path, output_base)
				os.makedirs(pathlib.Path(crop_file_path).parent, exist_ok=True)

				cropped_rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
				webp_method = _fast_webp_method_for(crop_tw, crop_th) if fast else NORMAL_WEBP_METHOD
				_save_webp(cropped_rgb, crop_file_path, webp_quality_sizes, webp_method)
				if not fast:
					copy_exif_data(source_path, crop_file_path)
				logger.info(f"Created {crop_key} for {unique_id}: {crop_tw}x{crop_th} at {crop_file_path}")

				sizes_info[crop_key] = {
					'path': crop_relative_path,
					'width': crop_tw,
					'height': crop_th,
					'url': await self._get_size_url(crop_file_path, crop_relative_path, photo_id, client_signature, keep_pics_in_worker=keep_pics_in_worker)
				}

		t_crops.done()
		logger.info(f"Created {len(sizes_info)} size variants for {unique_id}")

		if not fast:
			t_llm = _timed("640_llm variant", unique_id)
			# Create 640_llm variant (black fill over detections, no colors/stick figures, for LLM analysis)
			# Use original size if image is smaller than LLM_VARIANT_SIZE
			llm_image = src.fresh_for_width(LLM_VARIANT_SIZE)
			# Black out only the objects that were actually blurred — sub-threshold
			# detections are recorded but stay visible (same policy as apply_blur).
			# Prefer the persisted "blurred" flag; fall back to should_blur for legacy
			# format-#1 records that predate it (see detections.py). Bboxes are
			# full-image coords; a pyramid level needs them scaled to its size.
			apply_blackout(llm_image, scale_bboxes(
				[o for o in detections.get("objects", []) if o.get("blurred", should_blur(o))],
				llm_image.shape[1] / width))
			llm_h, llm_w = llm_image.shape[:2]

			if llm_w <= LLM_VARIANT_SIZE:
				llm_width = llm_w
				llm_height = llm_h
				llm_resized = llm_image
			else:
				llm_scale = LLM_VARIANT_SIZE / llm_w
				llm_width = LLM_VARIANT_SIZE
				llm_height = int(llm_h * llm_scale)
				llm_resized = cv2.resize(llm_image, (llm_width, llm_height), interpolation=cv2.INTER_AREA)

			user_id_part, photo_id_part = unique_id.split('/', 1)
			user_id_part = validate_user_id(user_id_part)
			llm_size_dir = os.path.join(output_base, 'opt', '640_llm', user_id_part)
			llm_filename = sanitize_filename(f"{photo_id_part}.webp")
			llm_output_path = validate_file_path(os.path.join(llm_size_dir, llm_filename), output_base)
			llm_relative_path = os.path.relpath(llm_output_path, output_base)
			os.makedirs(pathlib.Path(llm_output_path).parent, exist_ok=True)

			llm_rgb = cv2.cvtColor(llm_resized, cv2.COLOR_BGR2RGB)
			webp_method = _fast_webp_method_for(llm_width, llm_height) if fast else NORMAL_WEBP_METHOD
			_save_webp(llm_rgb, llm_output_path, webp_quality_sizes, webp_method)
			copy_exif_data(source_path, llm_output_path)
			logger.info(f"Created 640_llm variant for {unique_id}: {llm_width}x{llm_height} at {llm_output_path}")

			llm_url = await self._get_size_url(llm_output_path, llm_relative_path, photo_id, client_signature, keep_pics_in_worker=keep_pics_in_worker)
			sizes_info['640_llm'] = {
				'path': llm_relative_path,
				'width': llm_width,
				'height': llm_height,
				'url': llm_url
			}
			t_llm.done()

		if 'full' in sizes_info:
			# Deep-zoom pyramid. Metadata is stored inline in
			# sizes['full']['pyramid'] so the client can initialise OpenSeadragon
			# without an extra .dzi fetch.
			#
			# An externally rendered pyramid (pano pipeline phase_13) is an
			# OFFER: the upload client attaches one whenever it has one, and the
			# worker decides whether to use it from the other parameters —
			# blur applied, dev-serve vs prod path, prod's strict parameter
			# match (external_pyramid_usable). Declining is not an error: the
			# worker then does what it would have done without the offer, which
			# is its own render, or none in fast mode. `fast` itself stays a
			# pure encode-cost knob: it decides only whether the worker renders
			# its OWN pyramid, never whether an offered one is used.
			#
			# The decision itself was taken above (before the variants, so they
			# could derive from the chosen pyramid); here we only publish it.
			# An accepted external pyramid: dev path (served from this worker)
			# → in place from its archive mount; prod path → TRANSFERRED to the
			# pool tile by tile, exactly like an own pyramid — that transfer is
			# the whole worker cost of a prod pano upload. An own pyramid was
			# rendered already and gets shipped now.
			pyramid = None
			if ext_pyramid is not None:
				processing_state.set_phase("dzi_pyramid")
				if keep_pics_in_worker:
					pyramid = self._external_pyramid_in_place(local_pyramid_path, ext_pyramid)
				else:
					pyramid = await self._ship_pyramid(local_pyramid_path, local_pyramid_path[:-len('.dzi')] + '_files', ext_pyramid,
					                                   unique_id, photo_id, client_signature, keep_pics_in_worker=False)
			elif own_dzi is not None:
				processing_state.set_phase("dzi_pyramid")
				pyramid = await self._ship_pyramid(*own_dzi, unique_id, photo_id, client_signature, keep_pics_in_worker=keep_pics_in_worker)
			if pyramid:
				sizes_info['full']['pyramid'] = pyramid

		return sizes_info, detections



	# Skip DZI pyramid generation for images where both dimensions are below this threshold
	DZI_MIN_DIMENSION = 2048

	# The 'full' size variant is capped at this width. Also the anchor of the
	# external-pyramid variant-derivation guard: deriving variants from a
	# pyramid is only allowed when width >= 2x this, so the largest target
	# still has a >=2x level (see create_optimized_sizes).
	FULL_VARIANT_WIDTH = 8192

	def _external_pyramid(self, dzi_path: str, width: int, height: int, blur_applied: bool,
	                      keep_pics_in_worker: bool, quality: Optional[int], unique_id: str) -> Optional[Dict[str, Any]]:
		"""Validate a client-provided DZI pyramid and, if policy allows, return its
		parsed descriptor (tile_size/overlap/format/width/height/params) — the
		ACCEPTANCE. How it is then published is the caller's call: served in
		place on the dev path (_external_pyramid_in_place), transferred to the
		pool on the prod path (_ship_pyramid).

		The descriptor is XML: parsed with xml.etree, not regex. Whether the
		pyramid may be USED is external_pyramid_usable's call; on "no" we log
		the reason and return None — the offer is declined, the caller carries
		on as if none was made. The one hard failure is a Size that doesn't
		match the processed image: that is not policy but a wrong pyramid for
		this file (a pipeline association bug worth surfacing, not hiding).
		"""
		# defusedxml: same ElementTree API, with entity expansion (billion
		# laughs) and external-entity resolution refused — the descriptor is
		# client-named input even though it lives on an operator archive.
		import defusedxml.ElementTree as ET
		ns = '{http://schemas.microsoft.com/deepzoom/2008}'
		# A descriptor that isn't a well-formed DZI is a DECLINED offer, not a
		# failed photo: the worker can always render its own. (Only a
		# well-formed descriptor whose Size contradicts the photo fails hard
		# below — that one means the wrong pyramid was associated with this
		# file, which is a pipeline bug worth surfacing.)
		try:
			root = ET.parse(dzi_path).getroot()
			size = root.find(f'{ns}Size')
			if size is None:
				raise ValueError("no Size element")
			dzi = {
				'tile_size': int(root.get('TileSize')),
				'overlap': int(root.get('Overlap')),
				'format': root.get('Format'),
				'width': int(size.get('Width')),
				'height': int(size.get('Height')),
				'params': None,
			}
		except Exception as e:
			logger.info(f"External pyramid for {unique_id}: {dzi_path} — declined: "
			            f"unreadable DZI descriptor ({type(e).__name__}: {e})")
			return None
		if (dzi['width'], dzi['height']) != (width, height):
			raise ValueError(
				f"external pyramid {dzi_path} is {dzi['width']}x{dzi['height']} but the photo is "
				f"{width}x{height} — wrong pyramid for this file")
		params_path = dzi_path + '.params.json'
		if os.path.isfile(params_path):
			with open(params_path) as f:
				dzi['params'] = json.load(f)

		required = {
			'tile_size': DZI_TILE_SIZE, 'overlap': DZI_OVERLAP, 'format': DZI_FORMAT,
			'q': quality if quality is not None else WEBP_QUALITY_DZI, 'effort': DZI_WEBP_EFFORT,
		}
		usable, reason = external_pyramid_usable(keep_pics_in_worker, blur_applied, dzi, required)
		if usable and keep_pics_in_worker:
			# Dev path serves in place, which needs a URL for the root the
			# pyramid lives under (LOCAL_PHOTO_URLS). An unmapped root (e.g. the
			# tiff spill) is a decline, not a mid-job RuntimeError.
			from local_photos import url_for, root_name_of
			if url_for(dzi_path) is None:
				usable, reason = False, f"root {root_name_of(dzi_path)!r} has no LOCAL_PHOTO_URLS entry to serve it in place"
		logger.info(f"External pyramid for {unique_id}: {dzi_path} ({dzi['width']}x{dzi['height']}, "
		            f"tile {dzi['tile_size']}, {dzi['format']}, params={dzi['params']}) — "
		            f"{'USING' if usable else 'declined'}: {reason}")
		if not usable:
			return None
		return dzi

	def _external_pyramid_in_place(self, dzi_path: str, dzi: Dict[str, Any]) -> Dict[str, Any]:
		"""Pyramid metadata dict for an accepted external pyramid served IN
		PLACE (dev keep mode only): map the archive root it lives under to the
		URL Caddy serves that root at (LOCAL_PHOTO_URLS, "name=url;name=url" —
		see local_photos). The prod path never comes here — it transfers via
		_ship_pyramid."""
		from local_photos import url_for
		dzi_url = url_for(dzi_path)
		if dzi_url is None:
			raise RuntimeError(f"external pyramid {dzi_path} is usable but no LOCAL_PHOTO_URLS entry serves its root")
		return {
			'type': 'dzi',
			'dzi_url': dzi_url,
			'tiles_url': dzi_url.removesuffix('.dzi') + '_files',
			'tile_size': dzi['tile_size'],
			'overlap': dzi['overlap'],
			'format': dzi['format'],
			'width': dzi['width'],
			'height': dzi['height'],
			'external': True,
		}

	def _render_own_pyramid(self, image: np.ndarray, unique_id: str, photo_id: str = None, quality: Optional[int] = None, output_base: Optional[str] = None) -> Tuple[str, str, Dict[str, Any]]:
		"""dzsave a DZI (Deep Zoom Image) pyramid from an anonymized image into
		the job's work dir. Returns (dzi_file, tiles_dir, meta) — the tiles are
		NOT shipped yet: the caller derives the size variants from this pyramid
		first (see PyramidSource) and ships with _ship_pyramid afterwards.

		Args:
			image: Anonymized image as a numpy BGR array (already sRGB 8-bit).
			output_base: per-job output root (see process_uploaded_photo).
		"""
		try:
			h, w = image.shape[:2]
			user_id_part, photo_id_part = unique_id.split('/', 1)
			user_id_part = validate_user_id(user_id_part)
			safe_photo_id = sanitize_filename(photo_id_part)

			output_base = output_base or self.upload_dir
			_assert_output_base_owned(output_base, photo_id)
			dzi_dir = validate_file_path(os.path.join(output_base, 'opt', 'dzi', user_id_part), output_base)
			os.makedirs(dzi_dir, exist_ok=True)

			# vips dzsave writes <base>.dzi + <base>_files/
			dzi_output_base = os.path.join(dzi_dir, safe_photo_id)
			dzi_file = dzi_output_base + '.dzi'
			tiles_dir = dzi_output_base + '_files'

			tile_size = DZI_TILE_SIZE
			overlap = DZI_OVERLAP

			import pyvips
			# Convert BGR numpy array to pyvips RGB image
			logger.info(f"Generating DZI pyramid for {unique_id} from anonymized image ({w}x{h})")
			rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
			img = pyvips.Image.new_from_memory(rgb.data, w, h, 3, 'uchar')
			webp_quality_dzi = quality if quality is not None else WEBP_QUALITY_DZI
			with _timed(f'dzsave {w}x{h} tile {tile_size} Q{webp_quality_dzi} effort {DZI_WEBP_EFFORT}', unique_id):
				img.dzsave(dzi_output_base, tile_size=tile_size, overlap=overlap, suffix=f'.{DZI_FORMAT}[Q={webp_quality_dzi},effort={DZI_WEBP_EFFORT}]')
			logger.info(f"DZI generated for {unique_id}")
			meta = {'tile_size': tile_size, 'overlap': overlap, 'format': DZI_FORMAT, 'width': w, 'height': h}
			return dzi_file, tiles_dir, meta
		except Exception as e:
			# DZI is required (when the image is large enough to have one): a
			# failure here fails the whole photo so the client retries, rather
			# than silently producing a photo without deep zoom.
			logger.error(f"DZI pyramid generation failed for {unique_id}: {e}", exc_info=True)
			raise

	async def _ship_pyramid(self, dzi_file: str, tiles_dir: str, meta: Dict[str, Any], unique_id: str, photo_id: str = None, client_signature: str = None, keep_pics_in_worker: bool = False) -> Optional[Dict[str, Any]]:
		"""Ship a DZI pyramid (descriptor + every tile, through _get_size_url
		like any other artifact) and return the pyramid metadata dict for inline
		use by OpenSeadragon — it lets the client open the deep-zoom viewer
		without a separate .dzi fetch.

		Works for a pyramid rendered here (_render_own_pyramid, in the work
		dir) AND for an accepted external one living on a read-only archive
		mount: destinations are derived from ``unique_id`` — always
		``opt/dzi/{user}/{photo_id}.dzi`` + ``{photo_id}_files/…`` — not from
		where the source files sit, and in ship mode _get_size_url only READS
		the source (API POST / CDN put). This is the "transfer" half of the
		prod pano path: resize from the pyramid, then transfer the pyramid.
		"""
		try:
			tile_size, overlap, w, h = meta['tile_size'], meta['overlap'], meta['width'], meta['height']
			user_id_part, photo_id_part = unique_id.split('/', 1)
			user_id_part = validate_user_id(user_id_part)
			safe_photo_id = sanitize_filename(photo_id_part)
			rel_dir = os.path.join('opt', 'dzi', user_id_part)
			logger.info(f"Uploading DZI files for {unique_id} from {tiles_dir}")
			t_ship = _timed(f"pyramid ship ({'promote in place' if keep_pics_in_worker else 'transfer to pool'})", unique_id)

			# Upload the .dzi XML descriptor
			dzi_relative = os.path.join(rel_dir, f"{safe_photo_id}.dzi")
			dzi_url = await self._get_size_url(dzi_file, dzi_relative, photo_id, client_signature, keep_pics_in_worker=keep_pics_in_worker)

			# The .dzi URL determines which pool this pyramid lives on. The tile
			# base URL is derived from it by string surgery, so every tile must
			# land on the same pool — i.e. each tile's URL must be pool_base +
			# its relative path. If the API switched its write pool mid-upload
			# this breaks; we fail hard (PoolMigrationError) and the client retries.
			if not dzi_url.endswith(dzi_relative):
				raise PoolMigrationError(f"Unexpected .dzi URL shape for {unique_id}: {dzi_url} does not end with {dzi_relative}")
			pool_base = dzi_url[:len(dzi_url) - len(dzi_relative)]

			# Derive the tiles base URL from the dzi URL
			# OpenSeadragon uses {tiles_url}/{level}/{col}_{row}.{format}
			tiles_url_base = dzi_url.removesuffix('.dzi') + '_files'

			# Upload all tile files
			if os.path.exists(tiles_dir):
				tile_count = 0
				for level_name in sorted(os.listdir(tiles_dir)):
					level_path = os.path.join(tiles_dir, level_name)
					if not os.path.isdir(level_path):
						continue
					for tile_name in sorted(os.listdir(level_path)):
						tile_path = os.path.join(level_path, tile_name)
						if not os.path.isfile(tile_path):
							continue
						tile_relative = os.path.join(rel_dir, f"{safe_photo_id}_files", level_name, tile_name)
						tile_url = await self._get_size_url(tile_path, tile_relative, photo_id, client_signature, keep_pics_in_worker=keep_pics_in_worker)
						if tile_url != pool_base + tile_relative:
							raise PoolMigrationError(f"DZI tile for {unique_id} landed on a different pool than its .dzi: {tile_url} (expected base {pool_base})")
						tile_count += 1
				logger.info(f"Uploaded {tile_count} DZI tiles for {unique_id}")
				t_ship.done(f"({tile_count} tiles)")

			return {
				'type': 'dzi',
				'dzi_url': dzi_url,
				'tiles_url': tiles_url_base,
				'tile_size': tile_size,
				'overlap': overlap,
				'format': 'webp',
				'width': w,
				'height': h,
			}

		except Exception as e:
			# DZI is required (when the image is large enough to have one): a
			# failure here fails the whole photo so the client retries, rather
			# than silently producing a photo without deep zoom.
			logger.error(f"DZI pyramid generation failed for {unique_id}: {e}", exc_info=True)
			raise

	async def _upload_file_to_api(self, file_path: str, relative_path: str, photo_id: str, client_signature: str) -> str:
		"""Upload file to API server storage as a raw stream.

		Sends the file as a raw body with metadata in headers,
		avoiding multipart encoding (which causes sync spool I/O on the API server).

		Returns the URL where the file can be accessed.
		Raises PhotoDeletedException if photo was deleted during processing.
		"""
		api_url = os.getenv("API_URL")
		if not api_url:
			raise RuntimeError("API_URL environment variable is required for file uploads")
		upload_url = f"{api_url}/photos/upload-file"

		headers = {
			'Content-Type': 'application/octet-stream',
			'X-Photo-Id': photo_id,
			'X-Relative-Path': relative_path,
			'X-Client-Signature': client_signature,
		}

		try:
			async with httpx.AsyncClient() as client:
				max_retries = 10
				with open(file_path, 'rb') as f:
					file_data = f.read()
				file_size = len(file_data)
				logger.info(f"Uploading {relative_path} ({file_size} bytes) to API server")
				for attempt in range(max_retries):
					try:
						response = await client.post(upload_url, content=file_data, headers=headers, timeout=360.0)
					except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
						err_detail = f"{type(e).__name__}: {e}" if str(e) else f"{type(e).__name__}: {e.__cause__ or '(no detail)'}"
						if attempt < max_retries - 1:
							delay = 2 ** attempt
							logger.warning(f"Connection error uploading {relative_path} (attempt {attempt+1}/{max_retries}): {err_detail}, retrying in {delay}s")
							await asyncio.sleep(delay)
							continue
						logger.error(f"Connection error uploading {relative_path} after {max_retries} attempts: {err_detail}")
						raise

					if response.status_code == 410:
						logger.info(f"Photo {photo_id} was deleted, aborting file upload for {relative_path}")
						raise PhotoDeletedException(f"Photo {photo_id} was deleted during processing")

					if response.status_code >= 500 and attempt < max_retries - 1:
						delay = 2 ** attempt
						logger.warning(f"Server error {response.status_code} uploading {relative_path} (attempt {attempt+1}/{max_retries}): {response.text}, retrying in {delay}s")
						await asyncio.sleep(delay)
						continue

					response.raise_for_status()
					break

				logger.info(f"Successfully uploaded {relative_path} ({file_size} bytes) to API server")

				# The API decides which storage pool the file lands on and returns
				# its public URL. Fall back to PICS_URL for older API servers that
				# don't return one yet, so the worker and API need not be upgraded
				# in lockstep during a rolling deploy.
				url = response.json().get("url")
				if url:
					return url
				if PICS_URL:
					return PICS_URL + relative_path
				raise RuntimeError(f"API returned no url for {relative_path} and PICS_URL is not configured")

		except PhotoDeletedException:
			raise
		except httpx.HTTPStatusError as e:
			error_string = getattr(e, "response", None) and getattr(e.response, "text", None) or str(e)
			logger.error(f"Failed to upload {relative_path} to API server: {error_string}")
			raise RuntimeError(f"Failed to upload {relative_path} to API server: {error_string}")
		except Exception as e:
			error_string = getattr(e, "message", None) or str(e) or repr(e) or e.__class__.__name__
			logger.error(f"Failed to upload {relative_path} to API server: {error_string}")
			raise RuntimeError(f"Failed to upload {relative_path} to API server: {error_string}")

	async def _get_size_url(self, file_path: str, relative_path: str, photo_id: str = None, client_signature: str = None, keep_pics_in_worker: bool = False) -> str:
		"""Get URL for a size variant - keep locally, CDN upload, or API server upload.

		In the CDN/API modes the shipped copy is the product and the local
		file under opt/ is an intermediate — the caller reclaims it by
		rmtree'ing the whole per-job work dir (see worker_processing / app).
		Without this, every processed photo permanently duplicated its full
		variant set in the worker's uploads volume. keep_pics_in_worker (a
		per-photo upload flag, gated on ALLOW_KEEP_PICS_IN_WORKER in app) is
		the exception — the file is promoted out of the work dir into this
		worker's own uploads volume and served from there at WORKER_PICS_URL.
		"""
		use_cdn = os.getenv("USE_CDN", "false").lower() in ("true", "1", "yes")

		if keep_pics_in_worker:
			# Promote the finished file out of the per-job work dir into the
			# served tree. os.replace is atomic within the volume (work/ and
			# opt/ share it), so a returned URL never points at a half-written
			# file — mirroring the ship modes, where the URL is returned only
			# after the upload completed. WORKER_PICS_URL falls back to
			# PICS_URL for old single-toggle deployments that predate the
			# separate base.
			base = os.getenv("WORKER_PICS_URL") or PICS_URL
			if not base:
				raise RuntimeError("WORKER_PICS_URL (or PICS_URL) not configured for keep_pics_in_worker")
			dest = os.path.join(str(self.upload_dir), relative_path)
			os.makedirs(os.path.dirname(dest), exist_ok=True)
			os.replace(file_path, dest)
			return base + relative_path
		elif use_cdn:
			# Upload to CDN
			if not os.getenv("BUCKET_NAME"):
				raise RuntimeError("USE_CDN is true but BUCKET_NAME is not set")
			cdn_url = cdn_uploader._upload_file(file_path, relative_path)
			if not cdn_url:
				raise RuntimeError(f"Failed to upload {relative_path} to CDN")
			return cdn_url
		elif photo_id and client_signature:
			url = await self._upload_file_to_api(file_path, relative_path, photo_id, client_signature)
			return url
		elif not photo_id:
			logger.error(f"Cannot upload {relative_path}: photo_id is None")
			raise RuntimeError(f"photo_id is required for API upload of {relative_path}")
		elif not client_signature:
			logger.error(f"Cannot upload {relative_path}: client_signature is None")
			raise RuntimeError(f"client_signature is required for API upload of {relative_path}")
		else:
			raise RuntimeError("No upload method configured: either pass keep_pics_in_worker (with ALLOW_KEEP_PICS_IN_WORKER=true), set USE_CDN=true (with BUCKET_NAME), or provide photo_id and client_signature for API upload")


	async def _anonymize_image(self, source_path: str, encoding: Optional[str] = None) -> tuple[Optional[str], dict]:
		"""Anonymize image by blurring people and vehicles.

		encoding: EXR pixel encoding ('srgb'/'linear') from the upload metadata,
		threaded down to read_image (the auto-anonymization path reads the source).

		Returns:
			tuple: (anonymized_path: Optional[str], detections: dict)
		"""
		from anonymize import anonymize_image
		anonymized_path, detections = anonymize_image(source_path, encoding=encoding)
		logger.info(f"Anonymization completed for {source_path}, detections: {detections}")
		return anonymized_path, detections


	async def process_uploaded_photo(
		self,
		file_path: str,
		filename: str,
		user_id: UUID,
		photo_id: Optional[str] = None,
		description: Optional[str] = None,
		is_public: bool = True,
		client_signature: Optional[str] = None,
		anonymization_override: Optional[str] = None,
		metadata: Optional[Dict[str, Any]] = None,
		quality: Optional[int] = None,
		fast: bool = False,
		output_base: Optional[str] = None,
		keep_pics_in_worker: bool = False,
		local_pyramid_path: Optional[str] = None,
	) -> Optional[Dict[str, Any]]:
		"""Process a user-uploaded photo and return processing results.

		anonymization_override: JSON string controlling anonymization behavior:
			- None or "null": auto-detect faces/plates and blur them (default)
			- "[]": skip anonymization entirely
			- "[{...}]": use specific rectangles (future feature)
			- '{"objects": [...], ...}': precomputed detected_objects — blur
			  per the stored blurred flags and persist verbatim (see
			  AnonymizationOverride)
		fast: Skip pyramid, 640_llm, EXIF copy, use fast WebP encoding, reduced size set.
		output_base: This job's output root (its per-job work dir). Defaults to
			self.upload_dir. Must be a parameter, not singleton state: concurrent
			jobs run as threads sharing this PhotoProcessor instance.
		"""

		validate_user_id(str(user_id))
		unique_id = str(user_id) + '/' + str(photo_id)

		# Sanitize filename
		try:
			safe_filename = sanitize_filename(filename)
		except SecurityValidationError as e:
			logger.error(f"Filename sanitization failed for {filename}: {e}")
			raise ValueError(f"Invalid filename: {e}")

		# Canon RAW (CR2): convert to TIFF so downstream PIL/cv2/exiftool see
		# a standard image. Output is 8-bit sRGB (dcraw -T), which is what
		# we want heading into WebP — 16-bit would be quantized away anyway.
		# `-w` uses the camera white balance; we do NOT pass -4 (linear) since
		# viewers then render the pixels dark/flat (see scripts/raw/notes).
		#
		# We write to a .tiff extension (rather than overwriting in place)
		# because ImageMagick's identify picks the reader from the suffix —
		# a TIFF-content file with a .CR2 suffix triggers the CR2/DNG coder
		# and fails. The derived TIFF goes under the job's output_base (its
		# work dir), NOT next to the source: the caller reclaims the work dir
		# by rmtree'ing it, and in no-upload mode the source sits on a
		# read-only mount where a sibling write would fail with EROFS.
		if os.path.splitext(file_path)[1].lower() == '.cr2':
			tiff_stem = sanitize_filename(os.path.splitext(os.path.basename(file_path))[0])
			tiff_path = os.path.join(output_base or self.upload_dir, tiff_stem + '.tiff')
			with open(tiff_path, 'wb') as out:
				dcraw_result = subprocess.run(
					['dcraw', '-w', '-T', '-c', file_path],
					stdout=out, stderr=subprocess.PIPE, timeout=IMAGE_TOOL_TIMEOUT,
				)
			if dcraw_result.returncode != 0 or os.path.getsize(tiff_path) == 0:
				try:
					os.unlink(tiff_path)
				except OSError:
					pass
				err = dcraw_result.stderr.decode('utf-8', errors='replace').strip()[:500]
				raise ValueError(f"dcraw CR2 conversion failed: {err or 'empty output'}")
			# Carry EXIF/GPS/XMP/IPTC (incl. UserComment, DateTimeOriginal, Make,
			# Model, LensModel, FocalLength, GPS*) from the CR2 onto the TIFF.
			# Strip MakerNotes and embedded thumb/preview (they reference raw
			# offsets that won't exist in the TIFF). Force Orientation=1 because
			# dcraw has already physically rotated the pixels.
			exif_result = subprocess.run([
				'exiftool', '-overwrite_original',
				'-TagsFromFile', file_path,
				'-EXIF:all', '-GPS:all', '-XMP:all', '-IPTC:all',
				'-MakerNotes=', '-ThumbnailImage=', '-PreviewImage=',
				'-Orientation=1',
				tiff_path,
			], capture_output=True, text=True, timeout=60)
			if exif_result.returncode != 0:
				logger.warning(f"exiftool EXIF copy CR2->TIFF failed for {safe_filename}: {exif_result.stderr.strip()}")
			file_path = tiff_path
			logger.info(f"Converted CR2 to TIFF for {safe_filename} -> {tiff_path}")

		# Verify file content matches image type
		if not check_file_content(file_path, "image"):
			logger.error(f"File content verification failed for {safe_filename}")
			raise ValueError("Invalid image file content")

		# Extract EXIF data
		processing_state.set_phase("read_exif")
		exif_data = self.extract_exif_data(file_path)
		gps_data = exif_data.get('gps', {})
		debug_info = exif_data.get('debug', {})

		# If metadata is provided (e.g., from browser capture), use it to fill missing data
		if metadata:
			logger.info(f"Metadata provided: {metadata}")
			logger.info(f"GPS data before merge: {gps_data}")

			# Metadata WINS over embedded EXIF when present. The uploader reads
			# the canonical .CR2.geo.xmp sidecar fresh at upload time and sends
			# it here, whereas a file's embedded GPS can be stale (the pipeline
			# no longer re-embeds geo by default — re-upload carries the fresh
			# value via metadata instead of rewriting every file). So overwrite
			# unconditionally when the metadata field is present; fall back to
			# the embedded value only where metadata is silent.
			if metadata.get('latitude') is not None:
				gps_data['latitude'] = metadata['latitude']
			if metadata.get('longitude') is not None:
				gps_data['longitude'] = metadata['longitude']
			if metadata.get('altitude') is not None:
				gps_data['altitude'] = metadata['altitude']
			if metadata.get('bearing') is not None:
				gps_data['bearing'] = metadata['bearing']
			# Pitch has no EXIF home the way bearing does (GPSImgDirection),
			# so metadata is its only source rather than merely its preferred
			# one.
			if metadata.get('pitch') is not None:
				gps_data['pitch'] = metadata['pitch']

			logger.info(f"GPS data after merge: {gps_data}")

			# Use metadata for orientation if not in EXIF
			if metadata.get('orientation_code') and not exif_data['data'].get('Orientation'):
				exif_data['data']['Orientation'] = metadata['orientation_code']

			# Capture time: metadata WINS, same rule as geo above. The uploader
			# sends the canonical instant (the app's shutter clock in ms-ISO
			# UTC, or the pipeline's clock-drift-corrected value — the v2
			# semantics), whereas embedded DateTimeOriginal is second-granular
			# local wall-clock at best (CameraX writes it with no offset, and a
			# fused stack embeds the anchor frame's UNcorrected time). This was
			# fill-if-missing, which silently preferred the worse value
			# whenever a file carried any EXIF at all.
			if metadata.get('captured_at'):
				exif_data.setdefault('data', {})['DateTimeOriginal'] = metadata['captured_at']

			# Browser uploads carry no embedded EXIF, so synthesize the same
			# UserComment provenance JSON that the Android (Rust) EXIF writer
			# produces — landing location_source / bearing_source / alt_location in
			# exif_data['data']['UserComment'] uniformly across both upload paths.
			# ``v`` is the pipeline's metadata-semantics version (v2 == the
			# clock-drift-corrected UTC DateTimeOriginal); panoramas carry no
			# embedded UserComment, so the --metadata blob is their only channel
			# for it. Guarded so a real embedded UserComment (Android, or a webp's
			# geo.xmp-stamped one) is never clobbered.
			if not exif_data.setdefault('data', {}).get('UserComment'):
				synthesized = synthesize_provenance(metadata)
				if synthesized:
					exif_data['data']['UserComment'] = synthesized

			# Structured multi-frame source provenance from the pipeline. The
			# --metadata blob carries the source frames' camera metadata as a whole
			# nested object; its keys depend on the deliverable:
			#   - EXR panos: a representative identity header (Make/Model/LensModel/…),
			#     since the EXR embeds no EXIF, plus 'pano_frames' (array-of-arrays,
			#     one entry per pano position, each the stack of that position's
			#     frames);
			#   - fused-stack singles: just 'stack_frames' (flat list of the bracket's
			#     members) — the flattened TIFF already embeds the anchor frame's
			#     identity, so only the per-frame detail is added.
			# Merge into exif_data['data'] — the SAME place a single's embedded tags
			# land — so a consumer reads camera fields at exif_data.data.* uniformly;
			# pano_frames/stack_frames ride along in that dict for the per-frame
			# detail. Metadata wins over any embedded tag, matching the
			# geo/orientation convention above.
			if metadata.get('exif'):
				exif_data.setdefault('data', {}).update(metadata['exif'])

		orientation = exif_data['data'].get('Orientation')

		# Log detailed EXIF extraction results
		logger.info(f"EXIF extraction for {safe_filename}:")
		logger.info(f"  - has_exif: {debug_info.get('has_exif', False)}")
		logger.info(f"  - has_gps_coords: {debug_info.get('has_gps_coords', False)}")
		logger.info(f"  - has_bearing: {debug_info.get('has_bearing', False)}")
		logger.info(f"  - found_gps_tags: {debug_info.get('found_gps_tags', [])}")
		logger.info(f"  - found_bearing_tags: {debug_info.get('found_bearing_tags', [])}")
		logger.info(f"  - parsing_errors: {debug_info.get('parsing_errors', [])}")
		logger.info(f"  - GPS data: {gps_data}")
		logger.info(f"  - Orientation: {orientation}")

		# Validate required data (from either EXIF or metadata)
		if not gps_data.get('latitude') or gps_data.get('longitude') is None:
			if not debug_info.get('has_exif'):
				error_msg = "No EXIF data found in image file"
			else:
				found_tags = debug_info.get('found_bearing_tags', [])
				if found_tags:
					error_msg = f"GPS coordinates missing (found bearing tags: {', '.join(found_tags)}; need GPSLatitude, GPSLongitude)"
				else:
					error_msg = "GPS coordinates missing from photo (no GPS tags found in EXIF)"
			logger.warning(f"No GPS coordinates in {safe_filename}: {error_msg}")
			raise ValueError(error_msg)

		if gps_data.get('bearing') is None:
			found_tags = debug_info.get('found_gps_tags', [])
			if found_tags:
				error_msg = f"Compass direction missing (found GPS tags: {', '.join(found_tags)}; need GPSImgDirection, GPSTrack, or GPSDestBearing)"
			else:
				error_msg = "Compass bearing missing from photo"
			logger.warning(f"No bearing data in {safe_filename}: {error_msg}")
			raise ValueError(error_msg)

		# Get image dimensions
		width, height = self.get_image_dimensions(file_path, orientation)

		# Validate image dimensions to prevent resource exhaustion
		if not validate_image_dimensions(width, height):
			error_msg = f"Image size too large or invalid ({width}x{height}). Please use a smaller image."
			logger.error(f"Image dimensions validation failed for {safe_filename}: {width}x{height}")
			raise ValueError(error_msg)

		# Parse anonymization override from JSON string to Pydantic model
		override = AnonymizationOverride.from_json_string(anonymization_override)
		# EXR encoding carried out of band in the upload metadata (the
		# .exr.encoding sidecar value); read_image falls back to the embedded
		# header tag when this is absent.
		encoding = metadata.get('encoding') if metadata else None
		sizes_info, detections = await self.create_optimized_sizes(file_path, unique_id, width, height, photo_id, client_signature, override, quality=quality, fast=fast, encoding=encoding, output_base=output_base, keep_pics_in_worker=keep_pics_in_worker, local_pyramid_path=local_pyramid_path)

		# Extract captured_at from EXIF DateTimeOriginal (with corruption fix)
		raw_data = exif_data.get('data', {})
		captured_at_raw = raw_data.get('DateTimeOriginal') or raw_data.get('CreateDate')
		offset_raw = raw_data.get('OffsetTimeOriginal') or raw_data.get('OffsetTimeDigitized') or raw_data.get('OffsetTime')
		captured_at_dt = parse_exif_datetime(captured_at_raw, offset_raw)
		captured_at = captured_at_dt.isoformat() if captured_at_dt else None

		# Return processing results for database creation
		return {
			'filename': safe_filename,
			'exif_data': exif_data,
			'width': width,
			'height': height,
			'latitude': gps_data.get('latitude'),
			'longitude': gps_data.get('longitude'),
			'compass_angle': gps_data.get('bearing'),
			'pitch': gps_data.get('pitch'),
			'altitude': gps_data.get('altitude'),
			'sizes': sizes_info,  # Worker expects 'sizes', not 'sizes_info'
			'detected_objects': detections,
			'description': description,
			'is_public': is_public,
			'user_id': user_id,
			'captured_at': captured_at
		}


def copy_exif_data(source_path, output_path):
	# Copy EXIF data from source to output using exiftool
	# Reset orientation tag to 1 (normal orientation) because image has been loaded and saved anew
	# any other tags we might want to fix up?
	cmd = ['exiftool', '-overwrite_original', '-TagsFromFile', source_path, '-all:all', '-EXIF:Orientation=', output_path]
	logging.debug(f"Preserving EXIF data from {os.path.basename(source_path)} to anonymized version: {shlex.join(cmd)}")
	result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
	if result.returncode == 0:
		logging.info(f"Successfully preserved all EXIF metadata in anonymized image: {os.path.basename(output_path)}")
	else:
		logging.warning(f"Failed to preserve EXIF metadata in {os.path.basename(output_path)}: {result.stderr}")


# Global instance
photo_processor = PhotoProcessor()
