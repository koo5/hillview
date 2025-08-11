"""Photo upload and management routes with security."""
import os
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime
import aiofiles

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from .database import get_db
from .models import Photo, User
from .auth import get_current_active_user
from .security_utils import (
    validate_file_upload, 
    generate_secure_filename,
    validate_file_path,
    check_file_content
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/photos", tags=["photos"])

# Upload directory configuration
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(exist_ok=True)

@router.post("/upload")
async def upload_photo(
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    is_public: bool = Form(True),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload a photo with security validation and immediate database record creation."""
    try:
        # Get file size
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Reset to beginning
        
        # Validate file upload
        safe_filename, ext = validate_file_upload(
            filename=file.filename,
            file_size=file_size,
            content_type=file.content_type
        )
        
        # Generate secure filename with user ID
        secure_filename = generate_secure_filename(safe_filename, str(current_user.id))
        
        # Create user-specific upload directory
        user_upload_dir = UPLOAD_DIR / str(current_user.id)
        user_upload_dir.mkdir(exist_ok=True)
        
        # Save file path
        file_path = user_upload_dir / secure_filename
        
        # Save uploaded file
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        # Verify file content after saving
        if not check_file_content(str(file_path), "image"):
            # Delete the file if content verification fails
            os.remove(file_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid image file content"
            )
        
        # Create database record immediately with pending status
        photo = Photo(
            filename=secure_filename,
            filepath=str(file_path),
            description=description,
            is_public=is_public,
            owner_id=str(current_user.id),
            processing_status="pending",
            uploaded_at=datetime.utcnow()
        )
        
        db.add(photo)
        await db.commit()
        await db.refresh(photo)
        
        logger.info(f"Photo {photo.id} uploaded successfully by user {current_user.id}: {secure_filename}")
        
        # Photo will be processed by the worker polling for pending photos
        logger.info(f"Photo {photo.id} queued for processing")
        
        return {
            "message": "Photo uploaded successfully",
            "photo_id": photo.id,
            "filename": secure_filename,
            "processing_status": "pending"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading photo: {str(e)}")
        # Clean up file if it was saved
        if 'file_path' in locals() and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload photo"
        )

@router.get("/")
async def list_photos(
    skip: int = 0,
    limit: int = 100,
    only_processed: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """List user's photos."""
    try:
        query = select(Photo).where(Photo.owner_id == str(current_user.id))
        
        if only_processed:
            query = query.where(Photo.processing_status == "completed")
        
        result = await db.execute(
            query.offset(skip)
            .limit(limit)
            .order_by(Photo.uploaded_at.desc())
        )
        photos = result.scalars().all()
        
        return [{
            "id": photo.id,
            "filename": photo.filename,
            "description": photo.description,
            "is_public": photo.is_public,
            "latitude": photo.latitude,
            "longitude": photo.longitude,
            "compass_angle": photo.compass_angle,
            "width": photo.width,
            "height": photo.height,
            "uploaded_at": photo.uploaded_at,
            "processing_status": photo.processing_status
        } for photo in photos]
        
    except Exception as e:
        logger.error(f"Error listing photos: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list photos"
        )

@router.get("/{photo_id}")
async def get_photo(
    photo_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get photo details."""
    try:
        result = await db.execute(
            select(Photo).where(
                Photo.id == photo_id,
                Photo.owner_id == str(current_user.id)
            )
        )
        photo = result.scalars().first()
        
        if not photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Photo not found"
            )
        
        return {
            "id": photo.id,
            "filename": photo.filename,
            "filepath": photo.filepath,
            "description": photo.description,
            "is_public": photo.is_public,
            "latitude": photo.latitude,
            "longitude": photo.longitude,
            "compass_angle": photo.compass_angle,
            "altitude": photo.altitude,
            "width": photo.width,
            "height": photo.height,
            "captured_at": photo.captured_at,
            "uploaded_at": photo.uploaded_at,
            "processing_status": photo.processing_status,
            "exif_data": photo.exif_data,
            "detected_objects": photo.detected_objects,
            "sizes": photo.sizes
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting photo {photo_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get photo"
        )

@router.get("/{photo_id}/download")
async def download_photo(
    photo_id: str,
    size: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Download a photo file."""
    try:
        result = await db.execute(
            select(Photo).where(
                Photo.id == photo_id,
                Photo.owner_id == str(current_user.id)
            )
        )
        photo = result.scalars().first()
        
        if not photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Photo not found"
            )
        
        # Determine file path based on requested size
        if size and photo.sizes and size in photo.sizes:
            file_path = os.path.join(UPLOAD_DIR, str(current_user.id), photo.sizes[size].get('path'))
        else:
            file_path = photo.filepath
        
        # Validate file path to prevent traversal
        file_path = validate_file_path(file_path, str(UPLOAD_DIR))
        
        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Photo file not found"
            )
        
        return FileResponse(
            file_path,
            media_type="image/jpeg",
            filename=photo.filename
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading photo {photo_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download photo"
        )

@router.delete("/{photo_id}")
async def delete_photo(
    photo_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a photo and its files."""
    try:
        result = await db.execute(
            select(Photo).where(
                Photo.id == photo_id,
                Photo.owner_id == str(current_user.id)
            )
        )
        photo = result.scalars().first()
        
        if not photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Photo not found"
            )
        
        # Delete physical files
        try:
            # Delete main file
            if photo.filepath and os.path.exists(photo.filepath):
                os.remove(photo.filepath)
            
            # Delete size variants if they exist
            if photo.sizes:
                user_dir = os.path.join(UPLOAD_DIR, str(current_user.id))
                for size_info in photo.sizes.values():
                    if 'path' in size_info:
                        size_path = os.path.join(user_dir, size_info['path'])
                        if os.path.exists(size_path):
                            os.remove(size_path)
        except Exception as e:
            logger.warning(f"Error deleting photo files: {str(e)}")
        
        # Delete database record
        await db.delete(photo)
        await db.commit()
        
        logger.info(f"Photo {photo_id} deleted by user {current_user.id}")
        
        return {"message": "Photo deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting photo {photo_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete photo"
        )