"""
FastAPI Worker Service for Photo Processing

This service handles photo processing tasks with JWT authentication.
It exposes the process_uploaded_photo function as a REST API endpoint.
"""
import os

import logging
import sys
import psutil
import time
from dotenv import load_dotenv

# Load environment variables from .env file in same directory as script
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
import aiofiles
import httpx
from typing import Optional
from uuid import UUID
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from throttle import Throttle


throttle = Throttle('app')

# Add parent directories to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from jwt_service import validate_upload_authorization_token, sign_processing_result
from common.file_utils import (
	validate_and_prepare_photo_file,
	verify_saved_file_content,
	cleanup_file_on_error,
	get_file_size_from_upload
)
from common.security_utils import (
	SecurityValidationError,
	validate_photo_id,
	validate_user_id,
	sanitize_filename
)
from common.config import get_cors_origins
from photo_processor import photo_processor

# Setup logging
logging.basicConfig(level=logging.DEBUG)
# Quiet noisy HTTP logs
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
	title="Hillview Photo Processing Worker",
	description="Photo processing service with JWT authentication",
	version="1.0.1"
)

# CORS configuration
app.add_middleware(
	CORSMiddleware,
	allow_origins=get_cors_origins(),
	allow_credentials=True,
	allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
	allow_headers=["Content-Type", "Authorization", "Accept"],
)

# HTTP Bearer security scheme
security = HTTPBearer()

# Configuration
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads/"))
UPLOAD_DIR.mkdir(exist_ok=True)
API_URL = os.getenv("API_URL", "http://localhost:8055/api")

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
logger.info(f"Worker identity: {WORKER_IDENTITY}, PID: {os.getpid()}, DEV_MODE: {os.getenv('DEV_MODE')}")


# Request/Response models
class ProcessPhotoResponse(BaseModel):
	success: bool
	message: str
	photo_id: Optional[str] = None
	error: Optional[str] = None
	retry_after_minutes: Optional[int] = None  # None = permanent failure, >0 = retry after N minutes

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
	Always notifies API server of result (success or failure).
	"""
	# Extract upload authorization data
	raw_photo_id = upload_auth["photo_id"]
	raw_user_id = upload_auth["user_id"]
	client_key_id = upload_auth["client_public_key_id"]

	# Sanitize and validate critical parameters for filesystem safety
	try:
		photo_id = validate_photo_id(raw_photo_id)
		user_id = validate_user_id(raw_user_id)
	except SecurityValidationError as e:
		logger.error(f"Invalid upload parameters: {e}")
		raise HTTPException(
			status_code=400,
			detail=f"Invalid upload parameters: {str(e)}"
		)

	# Now safe to use in logging and file paths
	logger.info(f"/upload photo {photo_id}, user {user_id}, key {client_key_id}: {file.filename}")

	file_path = None
	processing_status = "error"
	error_message = None
	retry_after_minutes = None
	processing_result = None
	secure_filename = None


	try:

		async with throttle.rate_limit():

			# Wait for sufficient free RAM before processing
			want_mb = 300
			try:
				await throttle.wait_for_free_ram(want_mb)
			except TimeoutError as te:
				logger.error(f"wait_for_free_ram timeout for photo {photo_id}: {te}")
				raise

			safe_filename = sanitize_filename(file.filename)

			try:

				# Get file size and validate file
				file_size = get_file_size_from_upload(file.file)
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

				# Verify file content
				if not verify_saved_file_content(str(file_path), "image"):
					raise ValueError("Invalid image file content")

				logger.info(f"File saved successfully: {file_path}")

				# Process the photo
				user_uuid = UUID(user_id)


				processing_result = await photo_processor.process_uploaded_photo(
					file_path=str(file_path),
					filename=safe_filename,
					user_id=user_uuid,
					photo_id=photo_id,
					client_signature=client_signature
				)



				if not processing_result:
					raise ValueError("Processing returned no result")

				logger.info(f"Photo processing completed for {safe_filename}")
				processing_status = "completed"

			except TimeoutError as te:
				logger.error(f"TimeoutError (wait_for_free_ram?) for photo {photo_id}: {te}")
				processing_status = "error"
				error_message = f"Insufficient resources to process photo, please retry later"
				retry_after_minutes = 5

			except ValueError as processing_error:
				# Processing errors (EXIF missing, corrupted data, etc.) - permanent failures
				logger.error(f"Photo processing failed for {safe_filename}: {processing_error}")
				processing_status = "error"
				error_message = str(processing_error)
				retry_after_minutes = None  # Permanent failure, no retry

			except (IOError, OSError, PermissionError) as system_error:
				# System/IO errors (disk full, permissions, etc.) - retriable failures
				logger.error(f"System error processing photo {safe_filename}: {system_error}")
				processing_status = "error"
				error_message = f"System error: {system_error}"
				retry_after_minutes = 5  # Retry in 5 minutes

			except Exception as unexpected_error:
				# Unexpected errors - retriable failures with longer delay
				logger.error(f"Unexpected error processing photo {safe_filename}: {unexpected_error}")
				# exc_info = (type(exc), exc, exc.__traceback__)
				# logger.error('Exception occurred', exc_info=exc_info)
				processing_status = "error"
				error_message = f"Unexpected error: {unexpected_error}"
				retry_after_minutes = 10  # Retry in 10 minutes


		# Always notify API server of result
		try:
			processed_data = ProcessedPhotoData(
				photo_id=photo_id,
				processing_status=processing_status,
				client_signature=client_signature,
				processed_by_worker=WORKER_IDENTITY,
				error=error_message
			)

			# Add success data if processing succeeded
			if processing_status == "completed" and processing_result:
				processed_data.width = processing_result.get("width")
				processed_data.height = processing_result.get("height")
				processed_data.latitude = processing_result.get("latitude")
				processed_data.longitude = processing_result.get("longitude")
				processed_data.compass_angle = processing_result.get("compass_angle")
				processed_data.altitude = processing_result.get("altitude")
				processed_data.exif_data = processing_result.get("exif_data")
				processed_data.sizes = processing_result.get("sizes")
				processed_data.detected_objects = processing_result.get("detected_objects")
				processed_data.filename = secure_filename

			# Send to API server
			worker_signature = sign_processing_result(processed_data.dict())
			payload = {
				"processed_data": processed_data.dict(),
				"worker_signature": worker_signature
			}

			logger.info(f"Sending processing result to API server for photo {photo_id}")
			logger.info(f"Payload: {payload}")

			async with httpx.AsyncClient() as client:
				response = await client.post(
					f"{API_URL}/photos/processed",
					json=payload,
					headers={"Content-Type": "application/json"},
					timeout=30.0
				)

				if response.status_code != 200:
					logger.error(f"Failed to notify API for photo {photo_id}: {response.status_code}")
					raise HTTPException(status_code=500, detail="Failed to register result with API server")

				logger.info(f"Successfully notified API server for photo {photo_id}")

		except Exception as e:
			logger.error(f"Error notifying API for photo {photo_id}: {e}")
			raise HTTPException(status_code=500, detail="Failed to register result with API server")

	finally:
		if file_path:
			cleanup_file_on_error(file_path)

	# Return success response
	return ProcessPhotoResponse(
		success=processing_status == "completed",
		message="Photo processed successfully" if processing_status == "completed" else "Photo processing failed",
		photo_id=photo_id,
		error=error_message if processing_status in ["failed", "error"] else None,
		retry_after_minutes=retry_after_minutes
	)


