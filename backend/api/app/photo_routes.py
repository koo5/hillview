"""Photo upload and management routes with security."""
import os
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime
import aiofiles

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import Photo, User
from .auth import get_current_active_user
from .security_utils import (
    validate_file_upload, 
    generate_secure_filename,
    validate_file_path,
    check_file_content
)
from .rate_limiter import rate_limit_photo_upload, rate_limit_photo_operations

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/photos", tags=["photos"])

# Upload directory configuration
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(exist_ok=True)

@router.post("/upload")
async def upload_photo(
    request: Request,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    is_public: bool = Form(True),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload a photo with security validation and immediate database record creation."""
    # Apply photo upload rate limiting
    await rate_limit_photo_upload(request, current_user.id)
    
    logger.error(f"DEBUG: Upload request received for user {current_user.id}: {file.filename}")
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
        
        # Check if photo with same original_filename already exists for this user
        original_filename = file.filename or "unknown.jpg"
        existing_result = await db.execute(
            select(Photo).where(
                Photo.owner_id == str(current_user.id),
                Photo.original_filename == original_filename
            )
        )
        existing_photo = existing_result.scalars().first()
        
        if existing_photo:
            logger.info(f"Photo with original filename '{original_filename}' already exists for user {current_user.id}. Skipping upload.")
            # Remove the newly uploaded file since we're skipping
            os.remove(file_path)
            return {
                "message": "Photo with this filename already exists - skipped",
                "photo_id": existing_photo.id,
                "filename": existing_photo.filename,
                "original_filename": existing_photo.original_filename,
                "processing_status": existing_photo.processing_status,
                "skipped": True
            }
        
        # Create database record immediately with pending status
        logger.error(f"DEBUG: Creating photo record: secure_filename={secure_filename}, original_filename={original_filename}")
        photo = Photo(
            filename=secure_filename,  # Secure filename for storage
            original_filename=original_filename,  # Original filename for display
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
        logger.error(f"Error uploading photo: {str(e)}", exc_info=True)
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
    request: Request,
    skip: int = 0,
    limit: int = 100,
    only_processed: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """List user's photos."""
    # Apply photo operations rate limiting
    await rate_limit_photo_operations(request, current_user.id)
    
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
            "original_filename": photo.original_filename,
            "description": photo.description,
            "is_public": photo.is_public,
            "latitude": photo.latitude,
            "longitude": photo.longitude,
            "compass_angle": photo.compass_angle,
            "width": photo.width,
            "height": photo.height,
            "uploaded_at": photo.uploaded_at,
            "processing_status": photo.processing_status,
            "error": photo.error,
            "owner_id": photo.owner_id,
            "owner_username": current_user.username  # Since these are the current user's photos
        } for photo in photos]
        
    except Exception as e:
        logger.error(f"Error listing photos: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list photos"
        )

@router.get("/{photo_id}")
async def get_photo(
    request: Request,
    photo_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get photo details."""
    # Apply photo operations rate limiting
    await rate_limit_photo_operations(request, current_user.id)
    
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
            "original_filename": photo.original_filename,
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
            "error": photo.error,
            "exif_data": photo.exif_data,
            "detected_objects": photo.detected_objects,
            "sizes": photo.sizes,
            "owner_id": photo.owner_id,
            "owner_username": current_user.username  # Since this is the current user's photo
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
    request: Request,
    photo_id: str,
    size: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Download a photo file."""
    # Apply photo operations rate limiting
    await rate_limit_photo_operations(request, current_user.id)
    
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
    request: Request,
    photo_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a photo and its files."""
    # Apply photo operations rate limiting
    await rate_limit_photo_operations(request, current_user.id)
    
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