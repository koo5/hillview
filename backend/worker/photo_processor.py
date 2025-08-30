"""
photo processing service
"""
import os
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
import cv2
import numpy as np
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.database import SessionLocal
from common.models import Photo, User
from common.security_utils import sanitize_filename, validate_file_path, check_file_content, validate_image_dimensions, SecurityValidationError
from anonymize import anonymize_image

logger = logging.getLogger(__name__)

PICS_URL = os.environ.get("PICS_URL")

class PhotoProcessor:
    """Unified photo processing service for both imports and uploads."""

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
        try:
            with open(filepath, 'rb') as f:
                tags = exifread.process_file(f, details=True, debug=False)

            if len(tags) > 0:
                result['debug']['has_exif'] = True
                logger.info(f"EXIF tags found: {len(tags)} tags")
                logger.info(f"All EXIF tags: {[str(tag) for tag in tags.keys()]}")

                # Extract basic EXIF data
                exif_dict = {}
                for tag in tags.keys():
                    if tag not in ('JPEGThumbnail', 'TIFFThumbnail', 'Filename', 'EXIF MakerNote'):
                        exif_dict[tag] = str(tags[tag])
                result['exif'] = exif_dict

                gps_data = {}
                bearing = None
                latitude = tags.get('GPS GPSLatitude')
                longitude = tags.get('GPS GPSLongitude')

                # Track what GPS tags we found
                if latitude:
                    result['debug']['found_gps_tags'].append('GPS GPSLatitude')
                if longitude:
                    result['debug']['found_gps_tags'].append('GPS GPSLongitude')

                # Check bearing data (any one of the possible keys) - independent of coordinates
                bearing_keys = ['GPS GPSImgDirection', 'GPS GPSTrack', 'GPS GPSDestBearing']
                for key in bearing_keys:
                    if key in tags:
                        bearing = tags.get(key)
                        result['debug']['found_bearing_tags'].append(key)
                        result['debug']['has_bearing'] = True
                        break

                if latitude and longitude:
                    result['debug']['has_gps_coords'] = True

                    if bearing:

                        try:
                            altitude = tags.get('GPS GPSAltitude')
                            logger.info(f"Found GPS data via exifread")

                            # Convert coordinates to decimal degrees
                            lat = self._convert_to_degrees(latitude)
                            lon = self._convert_to_degrees(longitude)

                            # Apply hemisphere corrections
                            lat_ref = tags.get('GPS GPSLatitudeRef')
                            lon_ref = tags.get('GPS GPSLongitudeRef')
                            if lat_ref and str(lat_ref).upper().startswith('S'):
                                lat = -lat
                            if lon_ref and str(lon_ref).upper().startswith('W'):
                                lon = -lon

                            gps_data['latitude'] = lat
                            gps_data['longitude'] = lon
                            gps_data['bearing'] = float(str(bearing).split('/')[0]) if '/' in str(bearing) else float(str(bearing))
                            if altitude:
                                gps_data['altitude'] = float(str(altitude).split('/')[0]) if '/' in str(altitude) else float(str(altitude))

                            result['gps'] = gps_data
                            return result
                        except Exception as e:
                            result['debug']['parsing_errors'].append(f"GPS parsing failed: {e}")
                            logger.debug(f"GPS parsing failed: {e}")
        except Exception as e:
            result['debug']['parsing_errors'].append(f"exifread failed: {e}")
            logger.debug(f"exifread failed: {e}")

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


    def create_optimized_sizes(self, source_path: str, unique_id: str, original_filename: str, width: int, height: int, include_urls: bool = False) -> Dict[str, Dict[str, Any]]:
        """Create optimized versions with anonymization and unique IDs."""
        sizes_info = {}
        anonymized_path = None

        # Create output directory structure
        output_base = self.upload_dir

        try:
            # First anonymize the image
            anonymized_path = self._anonymize_image(source_path, unique_id)
            input_file_path = anonymized_path if anonymized_path else source_path

            # Standard sizes from original importer
            size_variants = ['full', 50, 320, 640, 1024, 1600, 2048, 2560, 3072]

            # Get file extension from original filename
            file_ext = os.path.splitext(original_filename)[1].lower()

            for size in size_variants:
                if size == 'full':
                    # Full size - copy the (anonymized) file with unique ID
                    unique_filename = f"{unique_id}{file_ext}"
                    full_output_path = os.path.join(output_base, unique_filename)
                    shutil.copy2(input_file_path, full_output_path)

                    relative_path = os.path.relpath(full_output_path, output_base)
                    size_info = {
                        'width': width,
                        'height': height,
                        'path': relative_path
                    }
                    if include_urls and PICS_URL:
                        size_info['url'] = PICS_URL + relative_path
                    sizes_info[size] = size_info
                else:
                    # Skip if size is larger than original width
                    if isinstance(size, int) and size > width:
                        break

                    # Create size-specific directory: opt/320/, opt/640/, etc.
                    size_dir = os.path.join(output_base, 'opt', str(size))
                    os.makedirs(size_dir, exist_ok=True)

                    # Output file path for this size using unique ID - sanitize first
                    try:
                        unique_filename = sanitize_filename(f"{unique_id}{file_ext}")
                        output_file_path = validate_file_path(os.path.join(size_dir, unique_filename), output_base)
                    except SecurityValidationError as e:
                        logger.error(f"Security validation failed for {unique_id}: {e}")
                        continue
                    size_relative_path = os.path.join('opt', str(size), unique_filename)

                    # Copy and resize the image (use anonymized version)
                    shutil.copy2(input_file_path, output_file_path)

                    # Resize using ImageMagick mogrify (matching original)
                    # Use absolute path and validate inputs
                    cmd = ['mogrify', '-resize', str(int(size)), output_file_path]
                    result = subprocess.run(cmd, capture_output=True, timeout=30)

                    if result.returncode == 0:
                        # Get new dimensions after resize
                        new_width, new_height = self.get_image_dimensions(output_file_path)

                        size_info = {
                            'width': new_width,
                            'height': new_height,
                            'path': size_relative_path
                        }
                        if include_urls and PICS_URL:
                            size_info['url'] = PICS_URL + size_relative_path
                        sizes_info[size] = size_info

                        # Optimize with jpegoptim (matching original)
                        cmd = ['jpegoptim', '--all-progressive', '--overwrite', output_file_path]
                        subprocess.run(cmd, capture_output=True, timeout=30)

                        logger.info(f"Created size {size} for {unique_id}: {new_width}x{new_height}")
                    else:
                        logger.warning(f"Failed to resize image to size {size}")
                        # Clean up failed file
                        try:
                            os.remove(output_file_path)
                        except Exception:
                            pass

            logger.info(f"Created {len(sizes_info)} size variants for {unique_id}")

            # Clean up temporary anonymized file
            if anonymized_path and os.path.exists(anonymized_path):
                temp_dir = os.path.dirname(anonymized_path)
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info(f"Cleaned up temporary anonymization files")

            return sizes_info

        except Exception as e:
            logger.error(f"Error creating optimized sizes for {unique_id}: {str(e)}")
            # Fallback to just the full size
            relative_path = os.path.relpath(source_path, output_base)
            return {
                'full': {
                    'width': width,
                    'height': height,
                    'path': relative_path
                }
            }
        finally:
            # Always clean up temporary anonymized file
            if anonymized_path and os.path.exists(anonymized_path):
                temp_dir = os.path.dirname(anonymized_path)
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _anonymize_image(self, source_path: str, unique_id: str) -> Optional[str]:
        """Anonymize image by blurring people and vehicles."""

		# Create temporary directory for anonymization
		temp_dir = tempfile.mkdtemp(prefix='hillview_anon_')
		source_dir = os.path.dirname(source_path)
		filename = os.path.basename(source_path)

		# Use anonymize_image function from the original script
		if anonymize_image(source_dir, temp_dir, filename):
			anonymized_path = os.path.join(temp_dir, filename)
			logger.info(f"Successfully anonymized {filename}")
			return anonymized_path
		else:
			logger.warning(f"Anonymization failed for {filename}, using original")
			# Clean up temp directory
			shutil.rmtree(temp_dir, ignore_errors=True)
			return None


    async def process_uploaded_photo(
        self,
        file_path: str,
        filename: str,
        user_id: UUID,
        photo_id: Optional[str] = None,
        description: Optional[str] = None,
        is_public: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Process a user-uploaded photo and return processing results."""
        try:
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

            # Generate unique ID for this photo
            unique_id = str(uuid.uuid4())

            # Create sizes information matching the original importer structure
            sizes_info = {}
            if width and height:
                sizes_info = self.create_optimized_sizes(file_path, unique_id, filename, width, height)

            # Return processing results for database creation
            return {
                'filename': safe_filename,
                'filepath': file_path,
                'exif_data': exif_data,
                'width': width,
                'height': height,
                'sizes_info': sizes_info,
                'detected_objects': detected_objects,
                'description': description,
                'is_public': is_public,
                'user_id': user_id
            }

        except ValueError as e:
            # Re-raise ValueError for specific validation errors (EXIF, GPS, dimensions)
            logger.error(f"Validation error processing {filename}: {str(e)}")
            raise e
        except Exception as e:
            # Generic processing errors
            error_msg = "Photo processing failed. The image may be corrupted or in an unsupported format."
            logger.error(f"Error processing uploaded photo {filename}: {str(e)}")
            raise ValueError(error_msg)


# Global instance
photo_processor = PhotoProcessor()
