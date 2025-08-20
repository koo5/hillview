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
        self.scan_interval = int(os.getenv("SCAN_INTERVAL_SECONDS", "10"))
        
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
            
            if not photo_processor.has_required_gps_data(exif_data):
                logger.warning(f"No GPS/bearing data found in {photo.filename}")
                photo.processing_status = "error"
                await db.commit()
                return
            
            # Get image dimensions
            width, height = photo_processor.get_image_dimensions(photo.filepath)
            
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
            
            await db.commit()
            logger.info(f"Successfully processed photo {photo.id}")
            
        except Exception as e:
            logger.error(f"Error processing photo {photo.id}: {str(e)}")
            photo.processing_status = "error"
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
                    output_file_path = os.path.join(size_dir, unique_filename)
                    size_relative_path = os.path.join('opt', str(size), unique_filename)
                    
                    # Copy and resize the image
                    shutil.copy2(input_file_path, output_file_path)
                    
                    # Resize using ImageMagick mogrify
                    cmd = ['mogrify', '-resize', str(int(size)), output_file_path]
                    result = subprocess.run(cmd, capture_output=True, timeout=30)
                    
                    if result.returncode == 0:
                        # Get new dimensions after resize
                        new_width, new_height = imgsize(output_file_path)
                        
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