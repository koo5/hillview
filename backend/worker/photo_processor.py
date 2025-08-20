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
        print(f"Processing EXIF data from {filepath}")
        
        # First try exifread
        try:
            with open(filepath, 'rb') as f:
                tags = exifread.process_file(f, details=True, debug=False)

            if len(tags) > 0:
                print("EXIF tags found:", len(tags), "tags")

                # Extract basic EXIF data
                exif_dict = {}
                for tag in tags.keys():
                    if tag not in ('JPEGThumbnail', 'TIFFThumbnail', 'Filename', 'EXIF MakerNote'):
                        exif_dict[tag] = str(tags[tag])

                gps_data = {}
                bearing = None
                latitude = tags.get('GPS GPSLatitude')
                longitude = tags.get('GPS GPSLongitude')
                
                if latitude and longitude:
                    # Check bearing data (any one of the possible keys)
                    bearing_keys = ['GPS GPSImgDirection', 'GPS GPSTrack', 'GPS GPSDestBearing']
                    for key in bearing_keys:
                        if key in tags:
                            bearing = tags.get(key)
                            break

                    if bearing:
                        altitude = tags.get('GPS GPSAltitude')
                        print(f"Found GPS data via exifread")
                        
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
                        
                        return {'exif': exif_dict, 'gps': gps_data}
        except Exception as e:
            print(f"exifread failed: {e}")

        # Fallback to exiftool
        try:
            # Validate filepath before passing to external tool
            try:
                validated_filepath = validate_file_path(filepath, "/app")
            except SecurityValidationError as e:
                print(f"Path validation failed for exiftool: {e}")
                return {'exif': {}, 'gps': {}}
            
            # Use -n flag to get raw numeric values instead of formatted strings
            cmd = ['exiftool', '-json', '-n', '-GPS*', validated_filepath]
            print(f"Trying exiftool fallback: {shlex.join(cmd)}")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                print(f"Error running exiftool")
                return {'exif': {}, 'gps': {}}
                
            data = json.loads(result.stdout)[0]
            
            # Check for required GPS data
            latitude = data.get('GPSLatitude')
            longitude = data.get('GPSLongitude')
            lat_ref = data.get('GPSLatitudeRef')
            lon_ref = data.get('GPSLongitudeRef')
            
            if latitude is None or longitude is None:
                print(f"No GPS data found.")
                return {'exif': {}, 'gps': {}}
            
            # Apply sign based on reference
            if lat_ref == 'S':
                latitude = -abs(latitude)
            if lon_ref == 'W':
                longitude = -abs(longitude)
            
            # Check bearing data
            bearing = data.get('GPSImgDirection') or data.get('GPSTrack') or data.get('GPSDestBearing')
            
            if not bearing:
                print(f"No bearing data found in {filepath}")
                return {'exif': {}, 'gps': {}}
                
            altitude = data.get('GPSAltitude')
            
            print(f"Found GPS data via exiftool")
            gps_data = {
                'latitude': latitude,
                'longitude': longitude,
                'bearing': bearing
            }
            if altitude:
                gps_data['altitude'] = altitude
                
            return {'exif': {}, 'gps': gps_data}
            
        except Exception as e:
            print(f"Error reading EXIF data from {filepath}: {e}")
            return {'exif': {}, 'gps': {}}
    
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
            print(f"Path validation failed for identify: {e}")
            return 0, 0
        
        cmd = ['identify', '-format', '%w %h', validated_filepath]
        try:
            output = subprocess.check_output(cmd, timeout=30).decode('utf-8')
            dimensions = [int(x) for x in output.split()]
            print('Image dimensions:', dimensions)
            return dimensions[0], dimensions[1]
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"Error getting image size for {filepath}: {e}")
            return 0, 0
    
    def detect_objects(self, filepath: str) -> List[Dict[str, Any]]:
        """
        Detect objects in the image using computer vision.
        Placeholder for future implementation.
        """
        try:
            # Check if YOLO model exists
            model_path = os.path.join("/app", "yolov5su.pt")
            if not os.path.exists(model_path):
                return []
            
            # Placeholder for object detection implementation
            # In production, you would load and run your model here
            detected_objects = []
            
            return detected_objects
            
        except Exception as e:
            logger.warning(f"Error detecting objects in {filepath}: {str(e)}")
            return []
    
    def create_optimized_sizes(self, source_path: str, unique_id: str, original_filename: str, width: int, height: int) -> Dict[str, Dict[str, Any]]:
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
                    sizes_info[size] = {
                        'width': width,
                        'height': height,
                        'path': relative_path
                    }
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
                        
                        sizes_info[size] = {
                            'width': new_width,
                            'height': new_height,
                            'path': size_relative_path
                        }
                        
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
        try:
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
                
        except Exception as e:
            logger.error(f"Error during anonymization of {source_path}: {str(e)}")
            return None
    
    async def process_uploaded_photo(
        self, 
        file_path: str, 
        filename: str, 
        user_id: UUID,
        description: Optional[str] = None,
        is_public: bool = True
    ) -> Optional[Photo]:
        """Process a user-uploaded photo and store it in the database."""
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
            
            # Get image dimensions
            width, height = self.get_image_dimensions(file_path)
            
            # Validate image dimensions to prevent resource exhaustion
            if not validate_image_dimensions(width, height):
                logger.error(f"Image dimensions validation failed for {safe_filename}: {width}x{height}")
                raise ValueError("Image dimensions exceed safety limits")
            
            # Detect objects (optional)
            detected_objects = self.detect_objects(file_path)
            
            # Generate unique ID for this photo
            unique_id = str(uuid.uuid4())
            
            # Create sizes information matching the original importer structure
            sizes_info = {}
            if width and height:
                sizes_info = self.create_optimized_sizes(file_path, unique_id, filename, width, height)
            
            # Create database record
            async with SessionLocal() as db:
                gps = exif_data.get('gps', {})
                
                photo = Photo(
                    filename=safe_filename,
                    filepath=file_path,
                    description=description,
                    is_public=is_public,
                    owner_id=user_id,
                    latitude=gps.get('latitude'),
                    longitude=gps.get('longitude'),
                    compass_angle=gps.get('bearing'),  # Use compass_angle field
                    altitude=gps.get('altitude'),
                    width=width,
                    height=height,
                    exif_data=exif_data.get('exif', {}),
                    detected_objects=detected_objects,
                    sizes=sizes_info,
                    processing_status="completed"
                )
                
                db.add(photo)
                await db.commit()
                await db.refresh(photo)
                
                logger.info(f"Successfully processed uploaded photo {photo.id}")
                return photo
                
        except Exception as e:
            logger.error(f"Error processing uploaded photo {filename}: {str(e)}")
            return None
    

# Global instance
photo_processor = PhotoProcessor()