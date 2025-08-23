#!/usr/bin/env python3
"""
Independent photo processing service
Scans database for unprocessed photos and processes them
"""
import os
import sys
import time
import logging
import asyncio
import json
import shutil
import subprocess
import shlex
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

import exifread
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Add common directory to path
sys.path.append('/app/common')

from common.database import SessionLocal
from common.models import Photo

# Import processing functions from photo_processor.py
from photo_processor import photo_processor
from anonymize import anonymize_image

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PICS_URL = os.environ.get("PICS_URL")

class PhotoProcessorService:
    """Independent photo processing service."""
    
    def __init__(self, upload_dir: str = "/app/uploads"):
        self.upload_dir = upload_dir
        self.scan_interval = int(os.getenv("SCAN_INTERVAL_SECONDS", "1"))
        
    async def scan_and_process(self):
        """Scan for unprocessed photos and process them."""
        try:
            async with SessionLocal() as db:
                stmt = select(Photo).where(Photo.processing_status == "pending")
                result = await db.execute(stmt)
                pending_photos = result.scalars().all()
                
                logger.info(f"Found {len(pending_photos)} photos to process")
                
                for photo in pending_photos:
                    await self.process_photo(db, photo)
                    
        except Exception as e:
            logger.error(f"Error during scan and process: {str(e)}")
    
    async def process_photo(self, db: AsyncSession, photo: Photo):
        """Process a single photo."""
        try:
            logger.info(f"Processing photo {photo.id}: {photo.filename}")
            
            # Update status to processing
            photo.processing_status = "processing"
            await db.commit()
            
            # Check if file exists
            if not os.path.exists(photo.filepath):
                logger.error(f"File not found: {photo.filepath}")
                photo.processing_status = "error"
                await db.commit()
                return
            
            # Extract EXIF data
            exif_data = photo_processor.extract_exif_data(photo.filepath)
            gps_data = exif_data.get('gps', {})
            debug_info = exif_data.get('debug', {})
            
            logger.info(f"EXIF extraction for {photo.filename}:")
            logger.info(f"  - has_exif: {debug_info.get('has_exif', False)}")
            logger.info(f"  - has_gps_coords: {debug_info.get('has_gps_coords', False)}")
            logger.info(f"  - has_bearing: {debug_info.get('has_bearing', False)}")
            logger.info(f"  - found_gps_tags: {debug_info.get('found_gps_tags', [])}")
            logger.info(f"  - found_bearing_tags: {debug_info.get('found_bearing_tags', [])}")
            logger.info(f"  - parsing_errors: {debug_info.get('parsing_errors', [])}")
            logger.info(f"  - GPS data: {gps_data}")
            
            # Create detailed error messages based on what was found
            if not debug_info.get('has_exif', False):
                error_msg = "No EXIF data found in image file. Photo may be processed/edited or from an app that strips metadata."
                logger.warning(f"No EXIF data found in {photo.filename}")
                photo.processing_status = "error"
                photo.error = error_msg
                await db.commit()
                return
            elif not debug_info.get('has_gps_coords', False) and not debug_info.get('has_bearing', False):
                found_tags = debug_info.get('found_gps_tags', [])
                error_msg = f"No GPS data found in photo. Found EXIF tags: {', '.join(found_tags) if found_tags else 'none'}"
                logger.warning(f"No GPS data found in {photo.filename}")
                photo.processing_status = "error"
                photo.error = error_msg
                await db.commit()
                return
            elif not debug_info.get('has_gps_coords', False):
                found_gps_tags = debug_info.get('found_gps_tags', [])
                found_bearing_tags = debug_info.get('found_bearing_tags', [])
                all_found_tags = found_gps_tags + found_bearing_tags
                error_msg = f"GPS coordinates missing. Found tags: {', '.join(all_found_tags) if all_found_tags else 'none'}, needed: GPSLatitude, GPSLongitude"
                logger.warning(f"No GPS coordinates in {photo.filename}")
                photo.processing_status = "error"
                photo.error = error_msg
                await db.commit()
                return
            elif not debug_info.get('has_bearing', False):
                found_bearing_tags = debug_info.get('found_bearing_tags', [])
                found_gps_tags = debug_info.get('found_gps_tags', [])
                error_msg = f"Compass direction missing. Found: {', '.join(found_gps_tags + found_bearing_tags)}, needed: GPSImgDirection, GPSTrack, or GPSDestBearing"
                logger.warning(f"No bearing data in {photo.filename}")
                photo.processing_status = "error"
                photo.error = error_msg
                await db.commit()
                return
            
            # Get image dimensions
            width, height = photo_processor.get_image_dimensions(photo.filepath)
            
            # Validate image dimensions to prevent resource exhaustion
            from common.security_utils import validate_image_dimensions
            if not validate_image_dimensions(width, height):
                error_msg = f"Image size too large or invalid ({width}x{height}). Please use a smaller image."
                logger.error(f"Image dimensions validation failed for {photo.filename}: {width}x{height}")
                photo.processing_status = "error"
                photo.error = error_msg
                await db.commit()
                return
            
            # Generate unique ID for processed files
            unique_id = str(uuid.uuid4())
            
            # Create optimized sizes
            sizes_info = await self.create_optimized_sizes(
                photo.filepath, photo.filename, unique_id, width, height
            )
            
            # Update photo with processed data
            photo.latitude = gps_data.get('latitude')
            photo.longitude = gps_data.get('longitude')
            photo.compass_angle = gps_data.get('bearing')
            photo.altitude = gps_data.get('altitude')
            photo.width = width
            photo.height = height
            photo.sizes = sizes_info
            photo.processing_status = "completed"
            photo.error = None  # Clear any previous error
            
            await db.commit()
            logger.info(f"Successfully processed photo {photo.id}")
            
        except Exception as e:
            error_msg = "Photo processing failed. The image may be corrupted or in an unsupported format."
            logger.error(f"Error processing photo {photo.id}: {str(e)}")
            photo.processing_status = "error"
            photo.error = error_msg
            await db.commit()
    
    
    async def create_optimized_sizes(
        self, source_path: str, filename: str, unique_id: str, width: int, height: int
    ) -> Dict[str, Dict[str, Any]]:
        """Create optimized sizes using the same logic as import.py."""
        sizes_info = {}
        
        try:
            # Create anonymized version first
            temp_dir = tempfile.mkdtemp(prefix='hillview_process_')
            anon_file_path = os.path.join(temp_dir, filename)
            
            # Anonymize image
            input_dir = os.path.dirname(source_path)
            if anonymize_image(input_dir, temp_dir, filename):
                input_file_path = anon_file_path
                logger.info(f"Successfully anonymized {filename}")
            else:
                input_file_path = source_path
                logger.warning(f"Anonymization failed for {filename}, using original")
            
            # Create output directory structure
            file_ext = os.path.splitext(filename)[1].lower()
            
            # Process different sizes (same as import.py)
            for size in ['full', 50, 320, 640, 1024, 1600, 2048, 2560, 3072]:
                if size == 'full':
                    # Full size - copy with unique ID
                    unique_filename = f"{unique_id}{file_ext}"
                    full_output_path = os.path.join(self.upload_dir, unique_filename)
                    shutil.copy2(input_file_path, full_output_path)
                    
                    relative_path = os.path.relpath(full_output_path, self.upload_dir)
                    sizes_info[size] = {
                        'width': width,
                        'height': height,
                        'path': relative_path,
						'url': PICS_URL + relative_path
                    }
                else:
                    # Skip if size is larger than original width
                    if isinstance(size, int) and size > width:
                        break
                    
                    # Create size-specific directory: opt/320/, opt/640/, etc.
                    size_dir = os.path.join(self.upload_dir, 'opt', str(size))
                    os.makedirs(size_dir, exist_ok=True)
                    
                    # Output file path for this size using unique ID
                    unique_filename = f"{unique_id}{file_ext}"
                    # Validate path to prevent directory traversal
                    try:
                        from common.security_utils import validate_file_path, sanitize_filename
                        safe_filename = sanitize_filename(unique_filename)
                        output_file_path = validate_file_path(os.path.join(size_dir, safe_filename), self.upload_dir)
                    except Exception as e:
                        logger.error(f"Path validation failed for {unique_filename}: {e}")
                        continue
                    size_relative_path = os.path.join('opt', str(size), safe_filename)
                    
                    # Copy and resize the image
                    shutil.copy2(input_file_path, output_file_path)
                    
                    # Resize using ImageMagick mogrify
                    cmd = ['mogrify', '-resize', str(int(size)), output_file_path]
                    result = subprocess.run(cmd, capture_output=True, timeout=30)
                    
                    if result.returncode == 0:
                        # Get new dimensions after resize using the same method as photo_processor
                        new_width, new_height = self._get_image_dimensions(output_file_path)
                        
                        sizes_info[size] = {
                            'width': new_width,
                            'height': new_height,
                            'path': size_relative_path
                        }
                        
                        # Optimize with jpegoptim
                        cmd = ['jpegoptim', '--all-progressive', '--overwrite', output_file_path]
                        subprocess.run(cmd, capture_output=True, timeout=30)
                        
                        logger.info(f"Created size {size} for {unique_id}: {new_width}x{new_height}")
                    else:
                        logger.warning(f"Failed to resize {filename} to size {size}")
            
            # Clean up temporary files
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            logger.info(f"Created {len(sizes_info)} size variants for {unique_id}")
            return sizes_info
            
        except Exception as e:
            logger.error(f"Error creating optimized sizes: {str(e)}")
            # Clean up on error
            if 'temp_dir' in locals():
                shutil.rmtree(temp_dir, ignore_errors=True)
            return {}
    
    def _get_image_dimensions(self, filepath: str) -> tuple[int, int]:
        """Get image dimensions using ImageMagick identify with security validation."""
        try:
            from common.security_utils import validate_file_path
            # Validate filepath before passing to external tool
            validated_filepath = validate_file_path(filepath, "/app")
        except Exception as e:
            logger.error(f"Path validation failed for identify: {e}")
            return 0, 0
        
        cmd = ['identify', '-format', '%w %h', validated_filepath]
        try:
            output = subprocess.check_output(cmd, timeout=30).decode('utf-8')
            dimensions = [int(x) for x in output.split()]
            return dimensions[0], dimensions[1]
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Error getting image size for {filepath}: {e}")
            return 0, 0
    
    async def run_forever(self):
        """Main service loop."""
        logger.info(f"Starting photo processor service (scan interval: {self.scan_interval}s)")
        
        while True:
            try:
                await self.scan_and_process()
                logger.info(f"Scan completed, sleeping for {self.scan_interval} seconds")
                await asyncio.sleep(self.scan_interval)
                
            except KeyboardInterrupt:
                logger.info("Received shutdown signal, stopping service")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {str(e)}")
                await asyncio.sleep(self.scan_interval)

if __name__ == "__main__":
    service = PhotoProcessorService()
    asyncio.run(service.run_forever())