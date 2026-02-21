"""
photo processing service
"""
import os
import pathlib
import json
import logging
import shutil
import subprocess
import shlex
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID
from datetime import datetime, timezone

from blur import read_image

os.environ["OPENCV_IMGCODECS_WEBP_MAX_FILE_SIZE"] = "209715200"  # 200MB
import cv2
from PIL import Image
import exifread
import httpx
from throttle import Throttle


from pydantic import BaseModel

from common.security_utils import sanitize_filename, validate_file_path, check_file_content, validate_image_dimensions, SecurityValidationError, validate_user_id

from common.cdn_uploader import cdn_uploader

logger = logging.getLogger(__name__)


class AnonymizationOverride(BaseModel):
	"""Controls anonymization behavior.

	- None (not provided): auto-detect faces/plates and blur them
	- Empty list []: skip anonymization entirely
	- List of rectangles: blur specific areas (future feature)
	"""
	rectangles: List[Dict[str, int]] = []  # Each dict: {x, y, width, height}

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
				return cls(**data)
			else:
				logger.warning(f"Invalid anonymization_override type: {type(data)}")
				return None
		except json.JSONDecodeError as e:
			logger.warning(f"Invalid anonymization_override JSON: {e}")
			return None

	@property
	def skip_anonymization(self) -> bool:
		"""Returns True if anonymization should be skipped (empty rectangles list)."""
		return len(self.rectangles) == 0


class PhotoDeletedException(Exception):
	"""Raised when a photo was deleted during processing."""
	pass


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


def parse_exif_datetime(value) -> Optional[datetime]:
	"""Parse EXIF datetime value and fix corrupted timestamps.

	Handles the bug where milliseconds were written as seconds, causing
	dates like "+58074:03:14 04:05:17". Detects years > 2100 and fixes
	by dividing the timestamp by 1000.

	Returns UTC datetime (EXIF times are assumed to be UTC for consistency).
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
	]

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
			# Add UTC timezone to the parsed datetime
			return dt.replace(tzinfo=timezone.utc)
		except ValueError:
			continue

	logger.warning(f"Could not parse DateTimeOriginal: {value}")
	return None


PICS_URL = os.environ.get("PICS_URL")
PARALLEL_PROCESSING_START_DELAY = float(os.environ.get("PARALLEL_PROCESSING_START_DELAY", 5))
logger.info(f"PARALLEL_PROCESSING_START_DELAY={PARALLEL_PROCESSING_START_DELAY} seconds")

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
				validated_filepath = validate_file_path(filepath, "/app")
			except SecurityValidationError as e:
				result['debug']['parsing_errors'].append(f"Path validation failed for exiftool: {e}")
				logger.debug(f"Path validation failed for exiftool: {e}")
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
				logger.debug(f"No GPS coordinates found via exiftool.")
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
				logger.debug(f"No bearing data found via exiftool")
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
		"""Get image dimensions using ImageMagick identify (known-good implementation)."""
		try:
			# Validate filepath before passing to external tool
			validated_filepath = validate_file_path(filepath, "/app")
		except SecurityValidationError as e:
			logger.debug(f"Path validation failed for identify: {e}")
			return 0, 0

		cmd = ['identify', '-format', '%w %h', validated_filepath]
		output = subprocess.check_output(cmd, timeout=300).decode('utf-8')
		dimensions = [int(x) for x in output.split()]
		if orientation in [5, 6, 7, 8]:
			dimensions = [dimensions[1], dimensions[0]]
		logger.debug(f'Image dimensions: {dimensions}')
		return dimensions[0], dimensions[1]


	async def create_optimized_sizes(self, source_path: str, unique_id: str, width: int, height: int, photo_id: str = None, client_signature: str = None, anonymization_override: Optional[AnonymizationOverride] = None


									 ) -> tuple[Dict[str, Dict[str, Any]], Optional[Dict[str, Any]]]:
		"""Create optimized versions with anonymization and unique IDs."""

		sizes_info = {}
		output_base = os.environ.get('PICS_DIR', self.upload_dir)

		logger.info(f"Starting anonymization for {unique_id}")

		if not anonymization_override:
			# this takes a while to import, so do it here dynamically
			logger.info(f"Importing anonymization module for {source_path}")
			from anonymize import anonymize_image as _

		async with throttle.rate_limit(PARALLEL_PROCESSING_START_DELAY, 1500):

			if not anonymization_override:
				image, detections = await self._anonymize_image(source_path)
			else:
				if anonymization_override.skip_anonymization:
					logger.info(f"Skipping anonymization for {unique_id} due to override")
					image = read_image(source_path)
					detections = {"objects": [], "manual": True}
				else:
					logger.info(f"Applying manual anonymization for {unique_id} with rectangles: {anonymization_override.rectangles}")
					image = read_image(source_path)
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
								'blur': 500
							})
					from blur import apply_blur
					apply_blur(image, detections['objects'])


			size_variants = ['full', 320, 640, 1024, 2048, 3072, 4096]

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

				scale = 1
				if size != 'full':
					scale = size / width

				new_width = int(width * scale)
				new_height = int(height * scale)

				logger.info(f"Creating size {size} for {unique_id}: {new_width}x{new_height} at {output_file_path}")
				new_image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
				logger.debug(f"Resized image to {new_width}x{new_height} for size {size}")
				new_image_rgb = cv2.cvtColor(new_image, cv2.COLOR_BGR2RGB)
				logger.debug(f"Converted image to RGB color space for size {size}")
				Image.fromarray(new_image_rgb).save(output_file_path, format='WEBP', quality=97, method=6)
				copy_exif_data(source_path, output_file_path)
				logger.info(f"Created size {size} for {unique_id}: {new_width}x{new_height} at {output_file_path}")

				size_info.update({
					'width': new_width,
					'height': new_height,
					'url': await self._get_size_url(output_file_path, relative_path, photo_id, client_signature)
				})
				sizes_info[size] = size_info

			logger.info(f"Created {len(sizes_info)} size variants for {unique_id}")

		return sizes_info, detections



	async def _upload_file_to_api(self, file_path: str, relative_path: str, photo_id: str, client_signature: str) -> str:
		"""Upload file to API server storage.

		Returns the URL where the file can be accessed.
		Raises PhotoDeletedException if photo was deleted during processing.
		"""
		api_url = os.getenv("API_URL")
		if not api_url:
			raise RuntimeError("API_URL environment variable is required for file uploads")
		upload_url = f"{api_url}/photos/upload-file"

		try:
			async with httpx.AsyncClient() as client:
				with open(file_path, 'rb') as f:
					files = {'file': (os.path.basename(relative_path), f, 'image/jpeg')}
					data = {
						'photo_id': photo_id,
						'relative_path': relative_path,
						'client_signature': client_signature
					}

					response = await client.post(upload_url, files=files, data=data, timeout=60.0)

					if response.status_code == 410:
						# Photo was deleted while processing - this is expected
						logger.info(f"Photo {photo_id} was deleted, aborting file upload for {relative_path}")
						raise PhotoDeletedException(f"Photo {photo_id} was deleted during processing")

					response.raise_for_status()

					result = response.json()
					logger.info(f"Successfully uploaded {relative_path} to API server")

					# Return the URL where the file can be accessed
					if PICS_URL:
						return PICS_URL + relative_path
					else:
						raise RuntimeError("PICS_URL not configured for file access")

		except PhotoDeletedException:
			raise
		except httpx.HTTPStatusError as e:
			logger.error(f"Failed to upload {relative_path} to API server: {e}")
			raise RuntimeError(f"Failed to upload {relative_path} to API server: {e}")
		except Exception as e:
			logger.error(f"Failed to upload {relative_path} to API server: {e}")
			raise RuntimeError(f"Failed to upload {relative_path} to API server: {e}")

	async def _get_size_url(self, file_path: str, relative_path: str, photo_id: str = None, client_signature: str = None) -> str:
		"""Get URL for a size variant - CDN upload, API server upload, or local only."""
		keep_pics_in_worker = os.getenv("KEEP_PICS_IN_WORKER", "false").lower() in ("true", "1", "yes")
		use_cdn = os.getenv("USE_CDN", "false").lower() in ("true", "1", "yes")

		if keep_pics_in_worker:
			# Keep files in worker, just return local URL
			if PICS_URL:
				return PICS_URL + relative_path
			else:
				raise RuntimeError("PICS_URL not configured for local file access")
		elif use_cdn:
			# Upload to CDN
			if not os.getenv("BUCKET_NAME"):
				raise RuntimeError("USE_CDN is true but BUCKET_NAME is not set")
			cdn_url = cdn_uploader._upload_file(file_path, relative_path)
			if not cdn_url:
				raise RuntimeError(f"Failed to upload {relative_path} to CDN")
			return cdn_url
		elif photo_id and client_signature:
			return await self._upload_file_to_api(file_path, relative_path, photo_id, client_signature)
		elif not photo_id:
			logger.error(f"Cannot upload {relative_path}: photo_id is None")
			raise RuntimeError(f"photo_id is required for API upload of {relative_path}")
		elif not client_signature:
			logger.error(f"Cannot upload {relative_path}: client_signature is None")
			raise RuntimeError(f"client_signature is required for API upload of {relative_path}")
		else:
			raise RuntimeError("No upload method configured: either set KEEP_PICS_IN_WORKER=true, USE_CDN=true (with BUCKET_NAME), or provide photo_id and client_signature for API upload")


	async def _anonymize_image(self, source_path: str) -> tuple[Optional[str], dict]:
		"""Anonymize image by blurring people and vehicles.

		Returns:
			tuple: (anonymized_path: Optional[str], detections: dict)
		"""
		from anonymize import anonymize_image
		anonymized_path, detections = anonymize_image(source_path)
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
		metadata: Optional[Dict[str, Any]] = None
	) -> Optional[Dict[str, Any]]:
		"""Process a user-uploaded photo and return processing results.

		anonymization_override: JSON string controlling anonymization behavior:
			- None or "null": auto-detect faces/plates and blur them (default)
			- "[]": skip anonymization entirely
			- "[{...}]": use specific rectangles (future feature)
		"""

		validate_user_id(str(user_id))
		unique_id = str(user_id) + '/' + str(photo_id)

		# Sanitize filename
		try:
			safe_filename = sanitize_filename(filename)
		except SecurityValidationError as e:
			logger.error(f"Filename sanitization failed for {filename}: {e}")
			raise ValueError(f"Invalid filename: {e}")

		# Verify file content matches image type
		if not check_file_content(file_path, "image"):
			logger.error(f"File content verification failed for {safe_filename}")
			raise ValueError("Invalid image file content")

		# Extract EXIF data
		exif_data = self.extract_exif_data(file_path)
		gps_data = exif_data.get('gps', {})
		debug_info = exif_data.get('debug', {})

		# If metadata is provided (e.g., from browser capture), use it to fill missing data
		if metadata:
			logger.info(f"Metadata provided: {metadata}")
			logger.info(f"GPS data before merge: {gps_data}")

			# Use metadata to fill missing GPS data (use conditional assignment,
			# not setdefault, because EXIF extraction may set keys to None)
			if metadata.get('latitude') is not None and gps_data.get('latitude') is None:
				gps_data['latitude'] = metadata['latitude']
			if metadata.get('longitude') is not None and gps_data.get('longitude') is None:
				gps_data['longitude'] = metadata['longitude']
			if metadata.get('altitude') is not None and gps_data.get('altitude') is None:
				gps_data['altitude'] = metadata['altitude']
			if metadata.get('bearing') is not None and gps_data.get('bearing') is None:
				gps_data['bearing'] = metadata['bearing']

			logger.info(f"GPS data after merge: {gps_data}")

			# Use metadata for orientation if not in EXIF
			if metadata.get('orientation_code') and not exif_data['data'].get('Orientation'):
				exif_data['data']['Orientation'] = metadata['orientation_code']

			# Use capture time from metadata if not in EXIF
			if metadata.get('captured_at') and not exif_data.get('data', {}).get('DateTimeOriginal'):
				exif_data['data']['DateTimeOriginal'] = metadata['captured_at']

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
			error_msg = "GPS coordinates missing from photo"
			logger.warning(f"No GPS coordinates in {safe_filename}")
			raise ValueError(error_msg)

		if gps_data.get('bearing') is None:
			error_msg = "Compass bearing missing from photo"
			logger.warning(f"No bearing data in {safe_filename}")
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
		sizes_info, detections = await self.create_optimized_sizes(file_path, unique_id, width, height, photo_id, client_signature, override)

		# Extract captured_at from EXIF DateTimeOriginal (with corruption fix)
		raw_data = exif_data.get('data', {})
		captured_at_raw = raw_data.get('DateTimeOriginal') or raw_data.get('CreateDate')
		captured_at_dt = parse_exif_datetime(captured_at_raw)
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
