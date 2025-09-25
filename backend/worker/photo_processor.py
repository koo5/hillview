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
from datetime import datetime

import exifread
import httpx
from throttle import Throttle


from common.security_utils import sanitize_filename, validate_file_path, check_file_content, validate_image_dimensions, SecurityValidationError

from common.cdn_uploader import cdn_uploader

logger = logging.getLogger(__name__)

PICS_URL = os.environ.get("PICS_URL")

throttle = Throttle('photo_processor')

class PhotoProcessor:
	"""Unified photo processing service for uploads."""


	SUPPORTED_EXTENSIONS = ['.jpg', '.jpeg', '.tiff', '.png', '.heic', '.heif']


	def __init__(self, upload_dir: str = "/app/uploads"):
		self.upload_dir = upload_dir


	def is_supported_image(self, filename: str) -> bool:
		"""Check if file is a supported image format."""
		return any(filename.lower().endswith(ext) for ext in self.SUPPORTED_EXTENSIONS)


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
			cmd = ['exiftool', '-json', '-n', '-GPS*', validated_filepath]
			logger.debug(f"Trying exiftool fallback: {shlex.join(cmd)}")

			proc_result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

			if proc_result.returncode != 0:
				result['debug']['parsing_errors'].append("exiftool command failed")
				logger.debug(f"Error running exiftool: {proc_result.stderr}")
				return result

			data = json.loads(proc_result.stdout)[0]

			# Check for required GPS data
			latitude = data.get('GPSLatitude')
			longitude = data.get('GPSLongitude')
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
				result['debug']['has_exif'] = True  # Mark as having EXIF data when GPS found via exiftool

				# Apply sign based on reference
				if lat_ref == 'S':
					latitude = -abs(latitude)
				if lon_ref == 'W':
					longitude = -abs(longitude)

			# Check bearing data
			bearing_fields = ['GPSImgDirection', 'GPSTrack', 'GPSDestBearing']
			bearing = None
			for field in bearing_fields:
				if data.get(field) is not None:
					bearing = data.get(field)
					result['debug']['found_bearing_tags'].append(field)
					break

			if not bearing:
				result['debug']['has_bearing'] = False
				logger.debug(f"No bearing data found via exiftool")
			else:
				result['debug']['has_bearing'] = True

			altitude = data.get('GPSAltitude')

			logger.debug(f"Found complete GPS data via exiftool")
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


	def get_image_dimensions(self, filepath: str) -> Tuple[int, int]:
		"""Get image dimensions using ImageMagick identify (known-good implementation)."""
		try:
			# Validate filepath before passing to external tool
			validated_filepath = validate_file_path(filepath, "/app")
		except SecurityValidationError as e:
			logger.debug(f"Path validation failed for identify: {e}")
			return 0, 0

		cmd = ['identify', '-format', '%w %h', validated_filepath]
		try:
			output = subprocess.check_output(cmd, timeout=30).decode('utf-8')
			dimensions = [int(x) for x in output.split()]
			logger.debug(f'Image dimensions: {dimensions}')
			return dimensions[0], dimensions[1]
		except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
			logger.debug(f"Error getting image size for {filepath}: {e}")
			return 0, 0


	async def create_optimized_sizes(self, source_path: str, unique_id: str, original_filename: str, width: int, height: int, photo_id: str = None, client_signature: str = None) -> tuple[Dict[str, Dict[str, Any]], Optional[Dict[str, Any]]]:
		"""Create optimized versions with anonymization and unique IDs."""
		sizes_info = {}
		anonymized_path = None

		# Create output directory structure
		output_base = os.environ.get('PICS_DIR', self.upload_dir)

		try:
			logger.info(f"Starting anonymization for {unique_id}")

			anonymized_path, detections = await self._anonymize_image(source_path)
			input_file_path = anonymized_path if anonymized_path else source_path
			logger.info(f"Using {'anonymized' if anonymized_path else 'original'} image for resizing: {input_file_path}")

			# Standard sizes from original importer
			size_variants = ['full', 320, 640, 1024, 2048, 3072]

			# Get file extension from original filename
			file_ext = os.path.splitext(original_filename)[1].lower()

			for size in size_variants:

				# Skip if size is larger than original width
				if isinstance(size, int) and size > width:
					break

				# Extract user_id and photo_id from unique_id (format: "user_id/photo_id")
				user_id_part, photo_id_part = unique_id.split('/', 1)

				# Create directory structure: opt/size/user_id/
				size_dir = os.path.join(output_base, 'opt', str(size), user_id_part)
				unique_filename = sanitize_filename(f"{photo_id_part}{file_ext}")
				output_file_path = validate_file_path(os.path.join(size_dir, unique_filename), output_base)
				relative_path = os.path.relpath(output_file_path, output_base)

				os.makedirs(pathlib.Path(output_file_path).parent, exist_ok=True)

				# Copy and resize the image
				shutil.copy2(input_file_path, output_file_path)

				size_info = {
					'path': relative_path,

				}

				if size == 'full':

					size_info.update({
						'width': width,
						'height': height,
						'url': await self._get_size_url(output_file_path, relative_path, photo_id, client_signature)
					})
					sizes_info[size] = size_info
				else:

					# Resize using ImageMagick mogrify (matching original)
					# Use absolute path and validate inputs
					cmd = ['mogrify', '-resize', str(int(size)), output_file_path]
					logger.debug(f"Resizing image with command: {shlex.join(cmd)}")
					subprocess.run(cmd, capture_output=True, timeout=30, check=True)
					new_width, new_height = self.get_image_dimensions(output_file_path)

					logger.debug(f"Optimizing JPEG with jpegoptim: {output_file_path}")
					cmd = ['jpegoptim', '--all-progressive', '--overwrite', output_file_path]
					subprocess.run(cmd, capture_output=True, timeout=130, check=True)

					logger.info(f"Created size {size} for {unique_id}: {new_width}x{new_height} at {output_file_path}");

					size_info.update({
						'width': new_width,
						'height': new_height,
						'url': await self._get_size_url(output_file_path, relative_path, photo_id, client_signature)
					})
					sizes_info[size] = size_info

			logger.info(f"Created {len(sizes_info)} size variants for {unique_id}")

		finally:
			# Clean up temporary anonymized file
			if anonymized_path and os.path.exists(anonymized_path):
				os.remove(anonymized_path)
				logger.info(f"Cleaned up temporary anonymization file.")

		return sizes_info, detections


	async def _upload_file_to_api(self, file_path: str, relative_path: str, photo_id: str, client_signature: str) -> str:
		"""Upload file to API server storage."""
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

					response = await client.post(upload_url, files=files, data=data)
					response.raise_for_status()

					result = response.json()
					logger.info(f"Successfully uploaded {relative_path} to API server")

					# Return the URL where the file can be accessed
					if PICS_URL:
						return PICS_URL + relative_path
					else:
						raise RuntimeError("PICS_URL not configured for file access")

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

		async with throttle.rate_limit():
			await throttle.wait_for_free_ram(400)

			#os.makedirs(temp_dir, exist_ok=True)
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
		client_signature: Optional[str] = None
	) -> Optional[Dict[str, Any]]:
		"""Process a user-uploaded photo and return processing results."""

		unique_id = str(user_id) + '/' + str(photo_id);

		# Initialize variables that might be used in exception handling
		detections = None

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

		# Log detailed EXIF extraction results
		logger.info(f"EXIF extraction for {safe_filename}:")
		logger.info(f"  - has_exif: {debug_info.get('has_exif', False)}")
		logger.info(f"  - has_gps_coords: {debug_info.get('has_gps_coords', False)}")
		logger.info(f"  - has_bearing: {debug_info.get('has_bearing', False)}")
		logger.info(f"  - found_gps_tags: {debug_info.get('found_gps_tags', [])}")
		logger.info(f"  - found_bearing_tags: {debug_info.get('found_bearing_tags', [])}")
		logger.info(f"  - parsing_errors: {debug_info.get('parsing_errors', [])}")
		logger.info(f"  - GPS data: {gps_data}")

		# Create detailed error messages based on what was found (same logic as service)
		if not debug_info.get('has_exif', False):
			error_msg = "No EXIF data found in image file. Photo may be processed/edited or from an app that strips metadata."
			logger.warning(f"No EXIF data found in {safe_filename}")
			raise ValueError(error_msg)
		elif not debug_info.get('has_gps_coords', False) and not debug_info.get('has_bearing', False):
			found_tags = debug_info.get('found_gps_tags', [])
			error_msg = f"No GPS data found in photo. Found EXIF tags: {', '.join(found_tags) if found_tags else 'none'}"
			logger.warning(f"No GPS data found in {safe_filename}")
			raise ValueError(error_msg)
		elif not debug_info.get('has_gps_coords', False):
			found_gps_tags = debug_info.get('found_gps_tags', [])
			found_bearing_tags = debug_info.get('found_bearing_tags', [])
			all_found_tags = found_gps_tags + found_bearing_tags
			error_msg = f"GPS coordinates missing. Found tags: {', '.join(all_found_tags) if all_found_tags else 'none'}, needed: GPSLatitude, GPSLongitude"
			logger.warning(f"No GPS coordinates in {safe_filename}")
			raise ValueError(error_msg)
		elif not debug_info.get('has_bearing', False):
			found_bearing_tags = debug_info.get('found_bearing_tags', [])
			found_gps_tags = debug_info.get('found_gps_tags', [])
			error_msg = f"Compass direction missing. Found: {', '.join(found_gps_tags + found_bearing_tags)}, needed: GPSImgDirection, GPSTrack, or GPSDestBearing"
			logger.warning(f"No bearing data in {safe_filename}")
			raise ValueError(error_msg)

		# Get image dimensions
		width, height = self.get_image_dimensions(file_path)

		# Validate image dimensions to prevent resource exhaustion
		if not validate_image_dimensions(width, height):
			error_msg = f"Image size too large or invalid ({width}x{height}). Please use a smaller image."
			logger.error(f"Image dimensions validation failed for {safe_filename}: {width}x{height}")
			raise ValueError(error_msg)

		# Create sizes information matching the original importer structure
		sizes_info = {}
		if width and height:
			sizes_info, detections = await self.create_optimized_sizes(file_path, unique_id, filename, width, height, photo_id, client_signature)

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
			'user_id': user_id
		}


# Global instance
photo_processor = PhotoProcessor()
