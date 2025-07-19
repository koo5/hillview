"""
Celery worker for background photo processing tasks.
"""
import os
import logging
from celery import Celery
from uuid import UUID
from typing import Optional

from app.photo_processor import photo_processor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Celery
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery("hillview_worker", broker=redis_url, backend=redis_url)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
)

@celery_app.task(bind=True)
def process_uploaded_photo(
    self, 
    file_path: str, 
    filename: str, 
    user_id: str,
    description: Optional[str] = None,
    is_public: bool = True
):
    """
    Process uploaded photo: extract EXIF data, create thumbnail, store in database.
    """
    try:
        logger.info(f"Processing uploaded photo {filename} for user {user_id}")
        
        # Update task progress
        self.update_state(state="PROGRESS", meta={"status": "Processing photo"})
        
        # Process the photo using shared processor (needs to be awaited)
        import asyncio
        photo = asyncio.run(photo_processor.process_uploaded_photo(
            file_path=file_path,
            filename=filename,
            user_id=UUID(user_id),
            description=description,
            is_public=is_public
        ))
        
        if photo:
            logger.info(f"Successfully processed uploaded photo {filename}")
            return {
                "photo_id": str(photo.id),
                "filename": filename,
                "status": "completed",
                "has_gps": photo.latitude is not None and photo.longitude is not None,
                "has_bearing": photo.bearing is not None
            }
        else:
            logger.error(f"Failed to process uploaded photo {filename}")
            self.update_state(
                state="FAILURE",
                meta={"error": "Failed to process photo", "filename": filename}
            )
            return {"status": "failed", "filename": filename}
        
    except Exception as exc:
        logger.error(f"Error processing uploaded photo {filename}: {str(exc)}")
        self.update_state(
            state="FAILURE",
            meta={"error": str(exc), "filename": filename}
        )
        raise exc


@celery_app.task
def cleanup_temp_files(file_paths: list):
    """
    Clean up temporary files after processing.
    """
    try:
        import os
        cleaned = 0
        for file_path in file_paths:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    cleaned += 1
            except Exception as e:
                logger.warning(f"Could not clean up {file_path}: {e}")
        
        logger.info(f"Cleaned up {cleaned} temporary files")
        return {"cleaned": cleaned, "total": len(file_paths)}
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise

if __name__ == "__main__":
    # Start Celery worker
    celery_app.start()