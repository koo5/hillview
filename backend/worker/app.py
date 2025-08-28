"""
FastAPI Worker Service for Photo Processing

This service handles photo processing tasks with JWT authentication.
It exposes the process_uploaded_photo function as a REST API endpoint.
"""

import os
import logging
import sys
import aiofiles
import httpx
from typing import Optional
from uuid import UUID
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# Add parent directories to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from common.jwt import validate_jwt_token
from common.file_utils import (
    validate_and_prepare_photo_file,
    verify_saved_file_content,
    cleanup_file_on_error,
    get_file_size_from_upload
)
from common.security_utils import SecurityValidationError
from photo_processor import photo_processor

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Hillview Photo Processing Worker",
    description="Photo processing service with JWT authentication",
    version="1.0.0"
)

# HTTP Bearer security scheme
security = HTTPBearer()

# Configuration
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(exist_ok=True)
API_URL = os.getenv("API_URL", "http://localhost:8055")

# Request/Response models
class ProcessPhotoResponse(BaseModel):
    success: bool
    message: str
    photo_id: Optional[str] = None
    error: Optional[str] = None

class ProcessedPhotoData(BaseModel):
    photo_id: str
    processing_status: str = "completed"
    width: Optional[int] = None
    height: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    compass_angle: Optional[float] = None
    altitude: Optional[float] = None
    exif_data: Optional[dict] = None
    sizes: Optional[dict] = None
    detected_objects: Optional[dict] = None
    error: Optional[str] = None

# Authentication dependency
async def get_current_user_and_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> tuple[str, str]:
    """
    Validate JWT token and return both user_id and the original token.
    Uses the same JWT validation logic as the API server.
    """
    token = credentials.credentials
    
    token_data = validate_jwt_token(token)
    if not token_data:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token_data["user_id"], token

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "Hillview Photo Processing Worker", "status": "running"}

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "photo-processor"}

@app.post("/upload", response_model=ProcessPhotoResponse)
async def upload_and_process_photo(
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    is_public: bool = Form(True),
    user_and_token: tuple[str, str] = Depends(get_current_user_and_token)
):
    """
    Upload and immediately process a photo, resembling the original API upload flow.
    Saves processed results via API call instead of direct database operations.
    """
    file_path = None
    try:
        current_user_id, original_token = user_and_token
        logger.info(f"Upload request received for user {current_user_id}: {file.filename}")
        
        # Get file size
        file_size = get_file_size_from_upload(file.file)
        
        # Validate and prepare file paths
        safe_filename, secure_filename, file_path = validate_and_prepare_photo_file(
            filename=file.filename,
            file_size=file_size,
            content_type=file.content_type,
            user_id=current_user_id,
            upload_base_dir=str(UPLOAD_DIR)
        )
        
        # Save uploaded file
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        # Verify file content after saving
        if not verify_saved_file_content(str(file_path), "image"):
            cleanup_file_on_error(file_path)
            raise HTTPException(
                status_code=400,
                detail="Invalid image file content"
            )
        
        logger.info(f"File saved successfully: {file_path}")
        
        # Process the photo immediately
        user_uuid = UUID(current_user_id)
        processing_result = await photo_processor.process_uploaded_photo(
            file_path=str(file_path),
            filename=safe_filename,
            user_id=user_uuid,
            description=description,
            is_public=is_public
        )
        
        if not processing_result:
            cleanup_file_on_error(file_path)
            return ProcessPhotoResponse(
                success=False,
                message="Photo processing failed",
                error="Processing returned no result"
            )
        
        logger.info(f"Photo processing completed for {safe_filename}")
        
        # TODO: Call API endpoint to save processed data using ProcessedPhotoData
        # We now have access to the original JWT token
        logger.info(f"Ready to call API endpoint with original token: {original_token[:20]}...")
        # Next step: implement the actual HTTP call to /api/photos/processed
        
        return ProcessPhotoResponse(
            success=True,
            message="Photo uploaded and processed successfully",
            photo_id="temp_id"  # Will be replaced with actual photo_id from API
        )
        
    except SecurityValidationError as e:
        if file_path:
            cleanup_file_on_error(file_path)
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        # Processing validation errors (EXIF, GPS, dimensions, etc.)
        if file_path:
            cleanup_file_on_error(file_path)
        logger.error(f"Validation error processing {file.filename}: {str(e)}")
        return ProcessPhotoResponse(
            success=False,
            message="Photo validation failed",
            error=str(e)
        )
    except Exception as e:
        # Generic processing errors
        if file_path:
            cleanup_file_on_error(file_path)
        logger.error(f"Error processing photo {file.filename}: {str(e)}")
        return ProcessPhotoResponse(
            success=False,
            message="Internal processing error",
            error="Photo processing failed due to internal error"
        )

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("WORKER_PORT", "8056"))
    host = os.getenv("WORKER_HOST", "0.0.0.0")
    
    logger.info(f"Starting Hillview Photo Processing Worker on {host}:{port}")
    uvicorn.run(app, host=host, port=port)