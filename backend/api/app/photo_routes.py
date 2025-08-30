"""Photo upload and management routes with security."""
import os
import logging
import base64
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import aiofiles
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from pydantic import BaseModel

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
from common.file_utils import (
    validate_and_prepare_photo_file,
    verify_saved_file_content,
    cleanup_file_on_error,
    get_file_size_from_upload
)
from common.security_utils import SecurityValidationError
from .jwt_service import validate_token
from .rate_limiter import rate_limit_photo_upload, rate_limit_photo_operations

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/photos", tags=["photos"])

# Upload directory configuration
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(exist_ok=True)

# Request models for processed photo data
class ProcessedPhotoData(BaseModel):
    photo_id: str
    processing_status: str = "completed"
    width: Optional[int] = None
    height: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    compass_angle: Optional[float] = None
    altitude: Optional[float] = None
    exif_data: Optional[Dict[str, Any]] = None
    sizes: Optional[Dict[str, Any]] = None
    detected_objects: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    client_signature: Optional[str] = None  # Base64-encoded ECDSA signature from client
    processed_by_worker: Optional[str] = None  # Worker identity for audit trail
    filename: Optional[str] = None  # Secure filename after processing
    filepath: Optional[str] = None  # Final file path after processing

# @router.post("/upload")
# async def upload_photo(
#     request: Request,
#     file: UploadFile = File(...),
#     description: Optional[str] = Form(None),
#     is_public: bool = Form(True),
#     current_user: User = Depends(get_current_active_user),
#     db: AsyncSession = Depends(get_db)
# ):
#     """Upload a photo with security validation and immediate database record creation."""
#     # Apply photo upload rate limiting
#     await rate_limit_photo_upload(request, current_user.id)
#
#     logger.error(f"DEBUG: Upload request received for user {current_user.id}: {file.filename}")
#     try:
#         # Get file size
#         file_size = get_file_size_from_upload(file.file)
#
#         # Validate and prepare file paths
#         safe_filename, secure_filename, file_path = validate_and_prepare_photo_file(
#             filename=file.filename,
#             file_size=file_size,
#             content_type=file.content_type,
#             user_id=str(current_user.id),
#             upload_base_dir=str(UPLOAD_DIR)
#         )
#
#         # Save uploaded file
#         async with aiofiles.open(file_path, 'wb') as f:
#             content = await file.read()
#             await f.write(content)
#
#         # Verify file content after saving
#         if not verify_saved_file_content(str(file_path), "image"):
#             # Delete the file if content verification fails
#             cleanup_file_on_error(file_path)
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Invalid image file content"
#             )
#
#         # Check if photo with same original_filename already exists for this user
#         original_filename = safe_filename
#         existing_result = await db.execute(
#             select(Photo).where(
#                 Photo.owner_id == str(current_user.id),
#                 Photo.original_filename == original_filename
#             )
#         )
#         existing_photo = existing_result.scalars().first()
#
#         if existing_photo:
#             logger.info(f"Photo with original filename '{original_filename}' already exists for user {current_user.id}. Skipping upload.")
#             # Remove the newly uploaded file since we're skipping
#             cleanup_file_on_error(file_path)
#             return {
#                 "message": "Photo with this filename already exists - skipped",
#                 "photo_id": existing_photo.id,
#                 "filename": existing_photo.filename,
#                 "original_filename": existing_photo.original_filename,
#                 "processing_status": existing_photo.processing_status,
#                 "skipped": True
#             }
#
#         # Create database record immediately with pending status
#         logger.error(f"DEBUG: Creating photo record: secure_filename={secure_filename}, original_filename={original_filename}")
#         photo = Photo(
#             filename=secure_filename,  # Secure filename for storage
#             original_filename=original_filename,  # Sanitized original filename for display
#             filepath=str(file_path),
#             description=description,
#             is_public=is_public,
#             owner_id=str(current_user.id),
#             processing_status="pending",
#             uploaded_at=datetime.utcnow()
#         )
#
#         db.add(photo)
#         await db.commit()
#         await db.refresh(photo)
#
#         logger.info(f"Photo {photo.id} uploaded successfully by user {current_user.id}: {secure_filename}")
#
#         # Photo will be processed by the worker polling for pending photos
#         logger.info(f"Photo {photo.id} queued for processing")
#
#         return {
#             "message": "Photo uploaded successfully",
#             "photo_id": photo.id,
#             "filename": secure_filename,
#             "processing_status": "pending"
#         }
#
#     except SecurityValidationError as e:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail=str(e)
#         )
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error uploading photo: {str(e)}", exc_info=True)
#         # Clean up file if it was saved
#         if 'file_path' in locals():
#             cleanup_file_on_error(file_path)
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to upload photo"
#         )

@router.post("/processed")
async def save_processed_photo(
    processed_data: ProcessedPhotoData,
    db: AsyncSession = Depends(get_db)
):
    """Save processed photo data from worker service with client signature verification."""
    try:
        photo_id = processed_data.photo_id
        logger.info(f"Saving processed photo data for {photo_id}")
        
        # Get the photo record (includes client signature info)
        result = await db.execute(
            select(Photo).where(Photo.id == photo_id)
        )
        photo = result.scalars().first()
        
        if not photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Photo not found"
            )
        
        # Verify that photo is in authorized status (not already processed)
        if photo.processing_status not in ["authorized", "processing"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Photo not in valid state for processing: {photo.processing_status}"
            )
        
        if not processed_data.client_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Client signature is required for secure uploads"
            )
        
        # Get client's public key for signature verification
        from common.models import UserPublicKey
        key_result = await db.execute(
            select(UserPublicKey).where(
                UserPublicKey.user_id == photo.owner_id,
                UserPublicKey.key_id == photo.client_public_key_id,
                UserPublicKey.is_active == True
            )
        )
        client_public_key = key_result.scalars().first()
        
        if not client_public_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Client public key not found or inactive"
            )
        
        # Verify client signature
        if not verify_client_signature(
            signature_base64=processed_data.client_signature,
            public_key_pem=client_public_key.public_key_pem,
            photo_id=photo_id,
            filename=photo.original_filename,
            timestamp=int(photo.upload_authorized_at.timestamp()) if photo.upload_authorized_at else None
        ):
            logger.error(f"Client signature verification failed for photo {photo_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Client signature verification failed"
            )
        
        logger.info(f"Client signature verified for photo {photo_id}")
        
        # Update photo with processed data, store signature, and track worker identity
        photo.processing_status = processed_data.processing_status
        photo.width = processed_data.width
        photo.height = processed_data.height
        # Update filename and filepath after successful processing
        if processed_data.filename:
            photo.filename = processed_data.filename
        if processed_data.filepath:
            photo.filepath = processed_data.filepath
        # Overwrite client-supplied geolocation data from authorization if EXIF/processing provides better data
        if processed_data.latitude is not None:
            photo.latitude = processed_data.latitude
        if processed_data.longitude is not None:
            photo.longitude = processed_data.longitude
        if processed_data.compass_angle is not None:
            photo.compass_angle = processed_data.compass_angle
        if processed_data.altitude is not None:
            photo.altitude = processed_data.altitude
        photo.exif_data = processed_data.exif_data
        photo.sizes = processed_data.sizes
        photo.detected_objects = processed_data.detected_objects
        photo.error = processed_data.error
        photo.client_signature = processed_data.client_signature  # Store signature for audit trail
        photo.processed_by_worker = processed_data.processed_by_worker  # Track which worker processed this
        photo.processed_at = datetime.now(timezone.utc)  # When processing was completed
        
        await db.commit()
        await db.refresh(photo)
        
        logger.info(f"Photo {photo_id} processing data saved successfully with verified client signature")
        
        return {
            "message": "Processed photo data saved successfully",
            "photo_id": photo.id,
            "processing_status": photo.processing_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving processed photo data for {processed_data.photo_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save processed photo data"
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

def verify_client_signature(signature_base64: str, public_key_pem: str, photo_id: str, filename: str, timestamp: int) -> bool:
    """
    Verify ECDSA client signature using the client's public key.
    
    SIGNATURE VERIFICATION SCHEME:
    =============================
    
    This function is the critical security checkpoint that prevents compromised workers 
    from impersonating users. Here's how the three-phase upload process works:
    
    Phase 1 - Upload Authorization (Client → API Server):
    - Client calls /api/photos/authorize-upload with file metadata
    - API server creates pending photo record with status="authorized" 
    - API server returns upload_jwt signed with API server's private key
    - upload_jwt contains: photo_id, user_id, client_public_key_id
    
    Phase 2 - Signed Upload (Client → Worker):
    - Client signs upload payload: {photo_id, filename, timestamp} with their ECDSA private key
    - Client sends: upload_jwt + file + client_signature to worker
    - Worker verifies upload_jwt using API server's public key (validates authorization)
    - Worker processes file but does NOT verify client signature (zero-trust worker)
    - Worker sends processed results + client_signature back to API server
    
    Phase 3 - Result Storage (Worker → API Server) ← WE ARE HERE
    - API server receives processed results + client_signature from worker
    - API server loads client's public key from database (client_public_key_id from photo record)
    - API server recreates the exact message that client signed: {photo_id, filename, timestamp}
    - API server verifies client_signature using client's public key
    - Only saves results if signature is valid - this prevents worker impersonation!
    
    WHY THIS WORKS:
    ===============
    - Worker cannot forge client signatures (doesn't have client's private key)
    - Worker cannot modify upload metadata (signature verification would fail)  
    - Even if worker is completely compromised, it cannot impersonate users
    - Provides cryptographic proof that the client authorized this specific upload
    - Signature is stored in database for audit trail and non-repudiation
    
    SIGNATURE FORMAT:
    =================
    Message signed by client: {"photo_id":"uuid","filename":"file.jpg","timestamp":1234567890}
    Signature algorithm: ECDSA P-256 with SHA-256
    Signature encoding: Base64
    """
    try:
        # Load the client's public key
        public_key = serialization.load_pem_public_key(public_key_pem.encode())
        
        # Recreate the exact message that the client signed
        # This must match the format used by ClientCryptoManager.signUploadData()
        message_data = {
            "photo_id": photo_id,
            "filename": filename,
            "timestamp": timestamp
        }
        message = json.dumps(message_data, separators=(',', ':'))  # Compact JSON, no spaces
        
        # Decode the base64 signature
        signature_bytes = base64.b64decode(signature_base64)
        
        # Verify the ECDSA signature
        public_key.verify(
            signature_bytes,
            message.encode('utf-8'),
            ec.ECDSA(hashes.SHA256())
        )
        
        logger.debug(f"Client signature verified for photo {photo_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error verifying client signature: {e}")
        return False