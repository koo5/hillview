"""
FastAPI Worker Service for Photo Processing

This service handles photo processing tasks with JWT authentication.
It exposes the process_uploaded_photo function as a REST API endpoint.
"""
import os
import asyncio
import threading
import logging
import sys
import time

import requests
from dotenv import load_dotenv
import socket
import hashlib

# Load environment variables from .env file in same directory as script
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
import aiofiles
import httpx
import math
import numpy as np

from typing import Optional, Any
from uuid import UUID
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Dict
from starlette.concurrency import run_in_threadpool
from throttle import Throttle

throttle = Throttle('app')

# Add parent directories to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from jwt_service import validate_upload_authorization_token, sign_processing_result
from photo_processor import PhotoDeletedException

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
#from photo_processor import photo_processor

# Setup logging
logging.basicConfig(level=logging.DEBUG)
# Quiet noisy HTTP logs
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

# Import and setup task context logging
from logging_context import setup_task_logging, task_context, current_photo_id, current_task_id
setup_task_logging()


def validate_json_payload(obj: Any, path: str = "") -> None:
	"""Validate that an object can be safely serialized to JSON.

	Raises ValueError with detailed path if any problematic values are found:
	- NaN or infinity floats
	- numpy types that haven't been converted
	- Other non-JSON-serializable types
	"""
	if obj is None or isinstance(obj, (bool, str)):
		return
	if isinstance(obj, int):
		return
	if isinstance(obj, float):
		if math.isnan(obj):
			raise ValueError(f"NaN float at {path or 'root'}")
		if math.isinf(obj):
			raise ValueError(f"Infinity float at {path or 'root'}")
		return
	if isinstance(obj, dict):
		for k, v in obj.items():
			validate_json_payload(v, f"{path}.{k}" if path else k)
		return
	if isinstance(obj, (list, tuple)):
		for i, item in enumerate(obj):
			validate_json_payload(item, f"{path}[{i}]")
		return
	# Check for numpy types
	if isinstance(obj, (np.integer, np.floating)):
		raise ValueError(f"Unconverted numpy type {type(obj).__name__} at {path or 'root'}")
	if isinstance(obj, np.ndarray):
		raise ValueError(f"Unconverted numpy array at {path or 'root'}")
	# Unknown type
	raise ValueError(f"Non-JSON-serializable type {type(obj).__name__} at {path or 'root'}")


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
FLY_MACHINE_ID = os.environ.get("FLY_MACHINE_ID", None)


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
	# Get hostname/container identifier
	hostname = socket.gethostname()

	# Get process start time (approximation)
	start_time = datetime.now().strftime("%Y%m%d-%H%M%S")

	# Create a short hash for uniqueness (not used for security, just identifier generation)
	unique_string = f"{hostname}-{start_time}-{os.getpid()}"
	hash_suffix = hashlib.md5(unique_string.encode(), usedforsecurity=False).hexdigest()[:5]

	return f"{hostname}_{start_time}_{hash_suffix}"

# Generate worker identity once at startup
WORKER_IDENTITY = get_worker_identity()
logger.info(f"Worker identity: {WORKER_IDENTITY}, PID: {os.getpid()}, DEV_MODE: {os.getenv('DEV_MODE')}, FLY_MACHINE_ID: {FLY_MACHINE_ID}")

# Semaphore to limit concurrent photo processing
PARALLEL_PROCESSING_CONCURRENCY = int(os.getenv("PARALLEL_PROCESSING_CONCURRENCY", "3"))
logger.info(f"PARALLEL_PROCESSING_CONCURRENCY: {PARALLEL_PROCESSING_CONCURRENCY}")
processing_semaphore = asyncio.Semaphore(PARALLEL_PROCESSING_CONCURRENCY)


def run_photo_processing_sync(file_path: str, filename: str, user_id: UUID, photo_id: str, client_signature: str, ctx_photo_id: str = None, ctx_task_id: str = None, anonymization_override: str = None, metadata: Dict[str, Any] = None, quality: int = None, fast: bool = False):
	"""
	Sync wrapper to run async photo processing in a dedicated event loop.
	This runs in a thread pool to avoid blocking the main event loop.

	ctx_photo_id and ctx_task_id are used to restore logging context in the new thread.
	anonymization_override: JSON string - null=auto, "[]"=none, "[{...}]"=specific rectangles
	quality: WebP quality (1-100). None=use default (97).
	fast: Skip pyramid, 640_llm, EXIF copy, use fast WebP encoding, reduced size set.
	"""
	# Restore logging context in this thread
	with task_context(photo_id=ctx_photo_id, task_id=ctx_task_id):
		loop = asyncio.new_event_loop()
		try:
			from photo_processor import photo_processor
			return loop.run_until_complete(
				photo_processor.process_uploaded_photo(
					file_path=file_path,
					filename=filename,
					user_id=user_id,
					photo_id=photo_id,
					client_signature=client_signature,
					anonymization_override=anonymization_override,
					metadata=metadata,
					quality=quality,
					fast=fast
				)
			)
		finally:
			loop.close()


@app.on_event("startup")
async def startup_event():
	"""Start background task ping loop on app startup."""
	start_background_loop()


pending_background_tasks_mutex = threading.Lock()
pending_background_tasks = set()
task_id_counter = 1


def background_loop():
	consecutive_failures = 0
	while True:
		l = None
		task0 = None
		with pending_background_tasks_mutex:
			l = len(pending_background_tasks)
			if l > 0:
				task0 = list(pending_background_tasks)[0]
		if l > 0:
			logger.info(f"Pending background tasks: {l}")
			try:
				resp = requests.post(
					f"{API_URL}/worker_pending_background_tasks_ping",
					json={
						"worker_identity": WORKER_IDENTITY,
						"fly_machine_id": FLY_MACHINE_ID,
						"pending_tasks": l,
						"task0_id": task0
					},
					timeout=60
				)
				if resp.status_code == 200:
					consecutive_failures = 0
					time.sleep(10)
				else:
					consecutive_failures += 1
					delay = min(2 ** consecutive_failures, 30)
					logger.warning(f"Ping returned {resp.status_code}, backing off {delay}s")
					time.sleep(delay)
			except requests.Timeout:
				consecutive_failures += 1
				time.sleep(min(2 ** consecutive_failures, 30))
			except Exception as e:
				consecutive_failures += 1
				delay = min(2 ** consecutive_failures, 30)
				logger.warning(f"Failed to ping API with pending tasks: {e}, backing off {delay}s")
				time.sleep(delay)
		else:
			consecutive_failures = 0
			time.sleep(10)


# Start background loop in a daemon thread
def start_background_loop():
	thread = threading.Thread(target=background_loop, daemon=True)
	thread.start()
	logger.info("Background task ping loop started")


# Request/Response models
class BrowserMetadata(BaseModel):
	"""Metadata provided when EXIF can't be written (e.g., browser capture)"""
	latitude: Optional[float] = None
	longitude: Optional[float] = None
	altitude: Optional[float] = None
	bearing: Optional[float] = None
	captured_at: Optional[str] = None  # ISO datetime
	orientation_code: Optional[int] = None  # EXIF orientation (1, 3, 6, 8)
	location_source: Optional[str] = None  # 'gps' or 'map'
	bearing_source: Optional[str] = None
	accuracy: Optional[float] = None

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
	captured_at: Optional[str] = None  # ISO datetime when photo was taken (from EXIF DateTimeOriginal)

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

@app.post("/await")
async def await_handler(task_id: str, request: Request):
	"""Wait for a background task to complete, sending periodic heartbeats to keep connection alive.
	Closes after 15s with {"status": "timeout"} to force fresh TCP connections from the caller."""

	async def heartbeat_generator():
		deadline = time.time() + 15
		while time.time() < deadline:
			if await request.is_disconnected():
				logger.info(f"Client {str(request.client)} disconnected while awaiting task {task_id}")
				return
			with pending_background_tasks_mutex:
				if task_id not in pending_background_tasks:
					yield b'{"status": "completed"}\n'
					return
			try:
				logger.debug(f"Awaiting task {task_id}, sending heartbeat to client {str(request.client)}")
			except Exception as e:
				logger.debug(f"Awaiting task {task_id}, sending heartbeat (client info unavailable: {e})")
			yield b'.\n'  # Heartbeat
			await asyncio.sleep(5)
		yield b'{"status": "timeout"}\n'

	return StreamingResponse(heartbeat_generator(), media_type="application/x-ndjson")




@app.get("/appcheck")
async def appcheck():
	"""Health check endpoint."""
	return {"status": "healthy", "service": "photo-processor"}
@app.get("/servicecheck")
async def servicecheck():
	"""Health check endpoint."""
	return {"status": "healthy", "service": "photo-processor"}


def validate_upload_parameters(upload_auth: dict, file) -> (str, str):

	# Extract upload authorization data
	raw_photo_id = upload_auth["photo_id"]
	raw_user_id = upload_auth["user_id"]
	client_key_id = upload_auth["client_public_key_id"]

	# Sanitize and validate critical parameters for filesystem and logging safety
	try:
		photo_id = validate_photo_id(raw_photo_id)
		user_id = validate_user_id(raw_user_id)
	except SecurityValidationError as e:
		logger.error(f"Invalid upload parameters: {e}")
		raise HTTPException(
			status_code=400,
			detail=f"Invalid upload parameters: {str(e)}"
		)

	logger.info(f"receive photo {photo_id}, user {user_id}, key {client_key_id}: {file.filename} ...")
	return photo_id, user_id


@app.post("/upload", response_model=ProcessPhotoResponse)
async def upload_sync(
	file: UploadFile = File(...),
	client_signature: str = Form(...),
	anonymization_override: Optional[str] = Form(None),  # JSON: null=auto, "[]"=none, "[{...}]"=specific
	metadata: Optional[str] = Form(None),  # JSON: metadata when EXIF can't be written (e.g., browser capture)
	quality: Optional[int] = Form(None),  # WebP quality (1-100). None=use default (97).
	fast: Optional[bool] = Form(None),  # Skip pyramid, 640_llm, EXIF copy, use fast WebP encoding
	upload_auth: dict = Depends(get_upload_authorization)
):
	photo_id, user_id = validate_upload_parameters(upload_auth, file)
	return await upload(file, client_signature, photo_id, user_id, anonymization_override=anonymization_override, metadata=metadata, quality=quality, fast=bool(fast))


@app.post("/upload_async")
async def upload_async(
	file: UploadFile = File(...),
	client_signature: str = Form(...),
	anonymization_override: Optional[str] = Form(None),  # JSON: null=auto, "[]"=none, "[{...}]"=specific
	metadata: Optional[str] = Form(None),  # JSON: metadata when EXIF can't be written (e.g., browser capture)
	quality: Optional[int] = Form(None),  # WebP quality (1-100). None=use default (97).
	fast: Optional[bool] = Form(None),  # Skip pyramid, 640_llm, EXIF copy, use fast WebP encoding
	upload_auth: dict = Depends(get_upload_authorization),
	background_tasks: BackgroundTasks = None
):
	global task_id_counter
	photo_id, user_id = validate_upload_parameters(upload_auth, file)
	with pending_background_tasks_mutex:
		task_id = f"{task_id_counter}_{time.time()}"
		task_id_counter += 1
		pending_background_tasks.add(task_id)
	background_tasks.add_task(upload, file, client_signature, photo_id, user_id, task_id, anonymization_override, metadata, quality, bool(fast))

	return {'success': True}


async def upload(file: UploadFile, client_signature: str, photo_id: str, user_id: str, task_id = None, anonymization_override: Optional[str] = None, metadata: Optional[str] = None, quality: Optional[int] = None, fast: bool = False):

	with task_context(photo_id=photo_id, task_id=task_id):
		return await _upload_inner(file, client_signature, photo_id, user_id, task_id, anonymization_override, metadata, quality, fast)


async def _upload_inner(file: UploadFile, client_signature: str, photo_id: str, user_id: str, task_id = None, anonymization_override: Optional[str] = None, metadata: Optional[str] = None, quality: Optional[int] = None, fast: bool = False):

	try:
		file_path, processing_status, error_message, retry_after_minutes, processing_result, secure_filename = await process(file, client_signature, photo_id, user_id, anonymization_override, metadata, quality, fast)

		# Handle deleted photos early - no need to notify API
		if processing_status == "deleted":
			logger.info(f"Photo {photo_id} was deleted during processing, returning success")
			return ProcessPhotoResponse(
				success=True,
				photo_id=photo_id,
				message="Photo was deleted during processing"
			)

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
				processed_data.captured_at = processing_result.get("captured_at")

			# Send to API server
			worker_signature = sign_processing_result(processed_data.dict())
			payload = {
				"processed_data": processed_data.dict(),
				"worker_signature": worker_signature
			}

			# Validate payload before sending - fail fast if there are problematic values
			try:
				validate_json_payload(payload)
			except ValueError as e:
				logger.error(f"Payload validation failed for photo {photo_id}: {e}")
				logger.error(f"Problematic payload: {payload}")
				raise

			logger.info(f"Sending processing result to API server for photo {photo_id}")
			logger.info(f"Payload: {payload}")

			max_retries = 5
			async with httpx.AsyncClient() as client:
				for attempt in range(max_retries):
					try:
						response = await client.post(
							f"{API_URL}/photos/processed",
							json=payload,
							headers={"Content-Type": "application/json"},
							timeout=220.0
						)
					except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
						if attempt < max_retries - 1:
							delay = 2 ** attempt
							logger.warning(f"Connection error sending result for photo {photo_id} (attempt {attempt+1}/{max_retries}): {e}, retrying in {delay}s")
							await asyncio.sleep(delay)
							continue
						logger.error(f"Connection error sending result for photo {photo_id} after {max_retries} attempts: {e}")
						raise

					if response.status_code == 410:
						logger.info(f"Photo {photo_id} was deleted during processing, skipping result submission")
						return ProcessPhotoResponse(
							success=True,
							photo_id=photo_id,
							message="Photo was deleted during processing"
						)

					if response.status_code >= 500 and attempt < max_retries - 1:
						delay = 2 ** attempt
						logger.warning(f"Server error {response.status_code} for photo {photo_id} (attempt {attempt+1}/{max_retries}): {response.text}, retrying in {delay}s")
						await asyncio.sleep(delay)
						continue

					if response.status_code != 200:
						logger.error(f"API rejected processing result for photo {photo_id}: {response.status_code} - {response.text}")
					response.raise_for_status()
					logger.info(f"Successfully notified API server for photo {photo_id}")
					break

		except Exception as e:
			import traceback
			logger.error(f"Error notifying API for photo {photo_id}: {type(e).__name__}: {e}")
			logger.error(f"Traceback: {traceback.format_exc()}")
			raise HTTPException(status_code=500, detail="Failed to register result with API server")

	finally:
		if file_path:
			cleanup_file_on_error(file_path)
		if task_id is not None:
			with pending_background_tasks_mutex:
				pending_background_tasks.discard(task_id)


	# Return success response
	return ProcessPhotoResponse(
		success=processing_status == "completed",
		message="Photo processed successfully" if processing_status == "completed" else "Photo processing failed",
		photo_id=photo_id,
		error=error_message if processing_status in ["failed", "error"] else None,
		retry_after_minutes=retry_after_minutes
	)


async def process(file: UploadFile, client_signature: str, photo_id: str, user_id: str, anonymization_override: Optional[str] = None, metadata: Optional[str] = None, quality: Optional[int] = None, fast: bool = False):

	file_path = None
	error_message = None
	retry_after_minutes = None
	processing_result = None
	secure_filename = None

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

		# Process the photo with concurrency limit
		user_uuid = UUID(user_id)

		async with processing_semaphore:
			await throttle.wait_for_free_ram(500)

			# Run processing in thread to avoid blocking the event loop
			# Capture current context to pass to the thread
			ctx_photo_id = current_photo_id.get()
			ctx_task_id = current_task_id.get()

			# Parse metadata JSON string if provided (e.g., from browser capture)
			parsed_metadata = None
			if metadata:
				parsed_metadata = BrowserMetadata.model_validate_json(metadata).model_dump(exclude_none=True)

			processing_result = await run_in_threadpool(
				run_photo_processing_sync,
				str(file_path),
				safe_filename,
				user_uuid,
				photo_id,
				client_signature,
				ctx_photo_id,
				ctx_task_id,
				anonymization_override,
				parsed_metadata,
				quality,
				fast
			)

		if not processing_result:
			raise ValueError("Processing returned no result")

		logger.info(f"Photo processing completed for {safe_filename}")
		processing_status = "completed"

	except TimeoutError as te:
		logger.error(f"TimeoutError (wait_for_free_ram?) for photo {photo_id}: {te}")
		processing_status = "error"
		error_message = "Insufficient resources to process photo, please retry later"
		retry_after_minutes = 15

	except ValueError as processing_error:
		# Processing errors (EXIF missing, corrupted data, etc.) - permanent failures
		logger.error(f"Photo processing failed for {safe_filename}: {processing_error}")
		processing_status = "error"
		error_message = str(processing_error)
		retry_after_minutes = None  # Permanent failure, no retry

	except PhotoDeletedException as e:
		# Photo was deleted during processing - this is expected, not an error
		logger.info(f"Photo deleted during processing: {e}")
		processing_status = "deleted"
		error_message = None
		retry_after_minutes = None

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

	return file_path, processing_status, error_message, retry_after_minutes, processing_result, secure_filename
