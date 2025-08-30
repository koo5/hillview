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

from jwt_service import validate_upload_authorization_token, sign_processing_result
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

def get_worker_identity() -> str:
    """
    Generate a unique worker identity for audit trail.
    
    This creates a semi-permanent identifier for this worker instance that can be used
    to track which worker processed which photos for debugging and audit purposes.
    
    The identity includes:
    - Worker hostname/container ID 
    - Process start time
    - Short hash for uniqueness
    
    Example: "worker-container-abc123_20241201-143022_x9k2m"
    """
    import socket
    import hashlib
    from datetime import datetime
    
    # Get hostname/container identifier
    hostname = socket.gethostname()
    
    # Get process start time (approximation)
    start_time = datetime.now().strftime("%Y%m%d-%H%M%S")
    
    # Create a short hash for uniqueness
    unique_string = f"{hostname}-{start_time}-{os.getpid()}"
    hash_suffix = hashlib.md5(unique_string.encode()).hexdigest()[:5]
    
    return f"{hostname}_{start_time}_{hash_suffix}"

# Generate worker identity once at startup
WORKER_IDENTITY = get_worker_identity()
logger.info(f"Worker identity: {WORKER_IDENTITY}")

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
    client_signature: Optional[str] = None  # Base64-encoded ECDSA signature from client
    processed_by_worker: Optional[str] = None  # Worker identity for audit trail
    filename: Optional[str] = None  # Secure filename after processing
    filepath: Optional[str] = None  # Final file path after processing

# Authentication dependency for upload authorization  
async def get_upload_authorization(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Validate upload authorization JWT token.
    Returns upload metadata including photo_id, user_id, client_public_key_id.
    """
    token = credentials.credentials
    
    token_data = validate_upload_authorization_token(token)
    if not token_data:
        raise HTTPException(
            status_code=401,
            detail="Invalid upload authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token_data

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
    client_signature: str = Form(...),
    upload_auth: dict = Depends(get_upload_authorization)
):
    """
    Upload and immediately process a photo using secure upload authorization.
    Verifies upload JWT authorization and processes file with client signature.
    """
    file_path = None
    try:
        # Extract upload authorization data
        photo_id = upload_auth["photo_id"]
        user_id = upload_auth["user_id"]
        client_public_key_id = upload_auth["client_public_key_id"]
        
        logger.info(f"Secure upload request for photo {photo_id}, user {user_id}: {file.filename}")
        
        # Get file size
        file_size = get_file_size_from_upload(file.file)
        
        # Validate and prepare file paths
        safe_filename, secure_filename, file_path = validate_and_prepare_photo_file(
            filename=file.filename,
            file_size=file_size,
            content_type=file.content_type,
            user_id=user_id,
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
        user_uuid = UUID(user_id)
        processing_result = await photo_processor.process_uploaded_photo(
            file_path=str(file_path),
            filename=safe_filename,
            user_id=user_uuid,
            photo_id=photo_id  # Use photo_id from authorization
        )
        
        if not processing_result:
            cleanup_file_on_error(file_path)
            return ProcessPhotoResponse(
                success=False,
                message="Photo processing failed",
                error="Processing returned no result"
            )
        
        logger.info(f"Photo processing completed for {safe_filename}")
        
        # Call API endpoint to save processed data with client signature and worker identity
        processed_data = ProcessedPhotoData(
            photo_id=photo_id,
            processing_status="completed",
            width=processing_result.get("width"),
            height=processing_result.get("height"),
            latitude=processing_result.get("latitude"),
            longitude=processing_result.get("longitude"),
            compass_angle=processing_result.get("compass_angle"),
            altitude=processing_result.get("altitude"),
            exif_data=processing_result.get("exif_data"),
            sizes=processing_result.get("sizes"),
            detected_objects=processing_result.get("detected_objects"),
            client_signature=client_signature,  # Include client signature for verification
            processed_by_worker=WORKER_IDENTITY,  # Track which worker processed this photo
            filename=secure_filename,  # Update secure filename after processing
            filepath=str(file_path)  # Store the final file path
        )
        
        # Sign the processed data with worker's private key
        try:
            worker_signature = sign_processing_result(processed_data.dict())
            logger.info(f"Signed processing result for photo {photo_id}")
        except Exception as e:
            logger.error(f"Failed to sign processing result for photo {photo_id}: {e}")
            return ProcessPhotoResponse(
                success=False,
                message="Failed to sign processing result",
                photo_id=photo_id,
                error=f"Signing error: {str(e)}"
            )
        
        # Make HTTP call to API server to save processed data with worker signature
        try:
            payload = {
                "processed_data": processed_data.dict(),
                "worker_signature": worker_signature
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{API_URL}/api/photos/processed",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    logger.info(f"Successfully saved processed data for photo {photo_id}")
                else:
                    logger.error(f"Failed to save processed data for photo {photo_id}: {response.status_code} - {response.text}")
                    return ProcessPhotoResponse(
                        success=False,
                        message="Photo processing completed but failed to save results",
                        photo_id=photo_id,
                        error=f"API call failed: {response.status_code}"
                    )
                    
        except Exception as e:
            logger.error(f"Error calling API to save processed data for photo {photo_id}: {e}")
            return ProcessPhotoResponse(
                success=False,
                message="Photo processing completed but failed to save results",
                photo_id=photo_id,
                error=f"API call error: {str(e)}"
            )
        
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