"""
Photo processing worker that polls for unprocessed photos.
"""
import asyncio
import os
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal
from app.models import Photo
from app.photo_processor import photo_processor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Worker configuration
POLL_INTERVAL = int(os.getenv("WORKER_POLL_INTERVAL", "10"))  # seconds
BATCH_SIZE = int(os.getenv("WORKER_BATCH_SIZE", "5"))  # photos per batch
STALE_TIMEOUT = int(os.getenv("WORKER_STALE_TIMEOUT", "300"))  # seconds (5 minutes)

async def get_pending_photos(db: AsyncSession, batch_size: int = BATCH_SIZE):
    """Get pending photos for processing."""
    try:
        # Find photos that are pending or have been processing for too long (stale)
        stale_time = datetime.utcnow() - timedelta(seconds=STALE_TIMEOUT)
        
        result = await db.execute(
            select(Photo)
            .where(
                (Photo.processing_status == "pending") |
                ((Photo.processing_status == "processing") & (Photo.uploaded_at < stale_time))
            )
            .limit(batch_size)
            .order_by(Photo.uploaded_at.asc())  # Process oldest first
        )
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error fetching pending photos: {str(e)}")
        return []

async def mark_photo_processing(db: AsyncSession, photo_id: str):
    """Mark a photo as being processed."""
    try:
        await db.execute(
            update(Photo)
            .where(Photo.id == photo_id)
            .values(processing_status="processing")
        )
        await db.commit()
    except Exception as e:
        logger.error(f"Error marking photo {photo_id} as processing: {str(e)}")
        await db.rollback()

async def mark_photo_completed(db: AsyncSession, photo_id: str, success: bool = True):
    """Mark a photo as completed or failed."""
    try:
        status = "completed" if success else "failed"
        await db.execute(
            update(Photo)
            .where(Photo.id == photo_id)
            .values(processing_status=status)
        )
        await db.commit()
    except Exception as e:
        logger.error(f"Error marking photo {photo_id} as {status}: {str(e)}")
        await db.rollback()

async def process_photo(photo: Photo):
    """Process a single photo."""
    try:
        logger.info(f"Processing photo {photo.id}: {photo.filename}")
        
        # Extract EXIF data
        exif_data = photo_processor.extract_exif_data(photo.filepath)
        gps = exif_data.get('gps', {})
        
        # Get image dimensions
        width, height = photo_processor.get_image_dimensions(photo.filepath)
        
        # Create optimized sizes
        sizes_info = {}
        if width and height:
            sizes_info = photo_processor.create_optimized_sizes(
                photo.filepath, 
                photo.id, 
                photo.filename, 
                width, 
                height
            )
        
        # Detect objects (optional)
        detected_objects = None
        try:
            detected_objects = photo_processor.detect_objects(photo.filepath)
        except Exception as e:
            logger.warning(f"Object detection failed for photo {photo.id}: {str(e)}")
        
        # Update photo record with processed data
        async with SessionLocal() as db:
            await db.execute(
                update(Photo)
                .where(Photo.id == photo.id)
                .values(
                    latitude=gps.get('latitude'),
                    longitude=gps.get('longitude'),
                    compass_angle=gps.get('bearing'),
                    altitude=gps.get('altitude'),
                    width=width,
                    height=height,
                    captured_at=exif_data.get('datetime'),
                    exif_data=exif_data.get('exif', {}),
                    detected_objects=detected_objects,
                    sizes=sizes_info,
                    processing_status="completed"
                )
            )
            await db.commit()
            
        logger.info(f"Successfully processed photo {photo.id}")
        return True
        
    except Exception as e:
        logger.error(f"Error processing photo {photo.id}: {str(e)}")
        return False

async def process_batch(photos: list):
    """Process a batch of photos."""
    for photo in photos:
        async with SessionLocal() as db:
            # Mark as processing
            await mark_photo_processing(db, photo.id)
        
        # Process the photo
        success = await process_photo(photo)
        
        # Mark as completed or failed
        async with SessionLocal() as db:
            await mark_photo_completed(db, photo.id, success)

async def worker_loop():
    """Main worker loop that polls for unprocessed photos."""
    logger.info(f"Starting photo processing worker (poll interval: {POLL_INTERVAL}s, batch size: {BATCH_SIZE})")
    
    while True:
        try:
            async with SessionLocal() as db:
                # Get pending photos
                photos = await get_pending_photos(db, BATCH_SIZE)
                
                if photos:
                    logger.info(f"Found {len(photos)} photos to process")
                    await process_batch(photos)
                else:
                    logger.debug("No pending photos found")
            
            # Wait before next poll
            await asyncio.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info("Worker interrupted by user")
            break
        except Exception as e:
            logger.error(f"Error in worker loop: {str(e)}")
            # Wait a bit longer on error to avoid rapid retries
            await asyncio.sleep(POLL_INTERVAL * 2)

def main():
    """Entry point for the worker."""
    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        logger.info("Worker shutdown requested")
    except Exception as e:
        logger.error(f"Worker crashed: {str(e)}")
        raise

if __name__ == "__main__":
    main()