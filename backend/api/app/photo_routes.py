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
from auth import get_current_active_user
from common.file_utils import (
	validate_and_prepare_photo_file,
	verify_saved_file_content,
	cleanup_file_on_error,
	get_file_size_from_upload
)
from common.security_utils import SecurityValidationError
from jwt_service import validate_token
from rate_limiter import rate_limit_photo_upload, rate_limit_photo_operations
from photos import delete_photo_files, determine_storage_type, StorageType

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

class WorkerProcessedPhotoRequest(BaseModel):
	"""Request model for processed photo data from worker with signature."""
	processed_data: ProcessedPhotoData
	worker_signature: str


@router.post("/processed")
async def save_processed_photo(
	request: WorkerProcessedPhotoRequest,
	db: AsyncSession = Depends(get_db)
):
	"""Save processed photo data from worker service with client signature verification."""
	try:
		processed_data = request.processed_data
		worker_signature = request.worker_signature
		photo_id = processed_data.photo_id

		# TODO: Verify worker signature for security
		logger.info(f"Received processed photo data from worker for {photo_id} (signature: {worker_signature[:20]}...)")
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
		if photo.processing_status != "authorized":
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

		logger.info(f"Verifying client signature for photo {photo_id} using public key ID {client_public_key.key_id}")

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
		# Update filename after successful processing
		if processed_data.filename:
			photo.filename = processed_data.filename
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


@router.post("/upload-file")
async def upload_processed_file(
	photo_id: str = Form(...),
	relative_path: str = Form(...),  # Path relative to pics folder where file should be saved
	client_signature: str = Form(...),
	file: UploadFile = File(...),
	db: AsyncSession = Depends(get_db)
):
	"""Upload processed photo file from worker service to API server storage."""

	# Check if CDN is enabled - if so, reject this request
	use_cdn = os.getenv("USE_CDN", "false").lower() in ("true", "1", "yes")
	if use_cdn:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="File uploads not supported when USE_CDN is enabled"
		)

	try:
		logger.info(f"Received file upload from worker for photo {photo_id}, path: {relative_path}")

		# Get photo from database
		result = await db.execute(select(Photo).where(Photo.id == photo_id))
		photo = result.scalar_one_or_none()
		if not photo:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Photo not found"
			)

		# Verify that photo is in authorized status
		if photo.processing_status != "authorized":
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=f"Photo not in valid state for file upload: {photo.processing_status}"
			)

		if not client_signature:
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

		# Verify client signature (same as save_processed_photo)
		# verify_client_signature is defined in this file
		if not verify_client_signature(
			signature_base64=client_signature,
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

		# Validate and sanitize the relative path
		if not relative_path or '..' in relative_path or relative_path.startswith('/'):
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Invalid relative path"
			)

		# Construct full file path within PICS_DIR
		pics_dir = Path(os.getenv("PICS_DIR", "/app/pics"))
		pics_dir.mkdir(parents=True, exist_ok=True)

		file_path = pics_dir / relative_path

		# Ensure the file path is within pics directory (security check)
		try:
			file_path.resolve().relative_to(pics_dir.resolve())
		except ValueError:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Path must be within pics directory"
			)

		# Ensure parent directory exists
		file_path.parent.mkdir(parents=True, exist_ok=True)

		# Save the file
		file_size = get_file_size_from_upload(file.file)
		async with aiofiles.open(file_path, 'wb') as f:
			content = await file.read()
			await f.write(content)

		logger.info(f"Successfully uploaded file for photo {photo_id} to {file_path}")

		return {
			"message": "File uploaded successfully",
			"photo_id": photo_id,
			"relative_path": relative_path,
			"file_path": str(file_path),
			"file_size": file_size
		}

	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"Error uploading file for photo {photo_id}: {str(e)}")
		# Cleanup file if it was partially written
		if 'file_path' in locals() and file_path.exists():
			try:
				file_path.unlink()
			except Exception:
				pass
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to upload file"
		)


@router.get("/")
async def list_photos(
	request: Request,
	cursor: Optional[str] = None,
	limit: int = 20,
	only_processed: bool = False,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""List user's photos with cursor-based pagination."""
	# Apply photo operations rate limiting
	await rate_limit_photo_operations(request, current_user.id)

	try:
		# Validate limit
		if limit > 100:
			limit = 100
		elif limit < 1:
			limit = 1

		base_query = select(Photo).where(Photo.owner_id == str(current_user.id))

		if only_processed:
			base_query = base_query.where(Photo.processing_status == "completed")

		# Get counts by processing status (separate query for performance)
		from sqlalchemy import func
		counts_result = await db.execute(
			select(Photo.processing_status, func.count(Photo.id))
			.where(Photo.owner_id == str(current_user.id))
			.group_by(Photo.processing_status)
		)
		counts_by_status = dict(counts_result.fetchall())

		# Calculate totals
		total_count = sum(counts_by_status.values())
		completed_count = counts_by_status.get("completed", 0)
		failed_count = counts_by_status.get("failed", 0)
		authorized_count = counts_by_status.get("authorized", 0)

		# Apply cursor-based pagination to main query
		query = base_query
		if cursor:
			try:
				from datetime import datetime, timezone
				# Handle both Z and +00:00 timezone formats, and fix URL decoding issues
				cursor_fixed = cursor
				if cursor.endswith('Z'):
					cursor_fixed = cursor.replace('Z', '+00:00')
				elif ' 00:00' in cursor:
					# Fix URL decoding that converts + to space
					cursor_fixed = cursor.replace(' 00:00', '+00:00')

				cursor_timestamp = datetime.fromisoformat(cursor_fixed)
				query = query.where(Photo.uploaded_at < cursor_timestamp)
			except (ValueError, TypeError) as e:
				logger.warning(f"Invalid cursor format: {cursor}, error: {e}")
				raise HTTPException(
					status_code=status.HTTP_400_BAD_REQUEST,
					detail=f"Invalid cursor format: {cursor}. Expected ISO 8601 timestamp. Error: {e}"
				)

		result = await db.execute(
			query.limit(limit + 1)  # Get one extra to check if there are more
			.order_by(Photo.uploaded_at.desc())
		)
		photos = result.scalars().all()

		# Check if there are more photos
		has_more = len(photos) > limit
		if has_more:
			photos = photos[:-1]  # Remove the extra photo

		# Generate next cursor
		next_cursor = None
		if has_more and photos:
			next_cursor = photos[-1].uploaded_at.isoformat()

		photos_data = [{
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
			"captured_at": photo.captured_at,
			"processing_status": photo.processing_status,
			"error": photo.error,
			"sizes": photo.sizes,
			"owner_id": photo.owner_id,
			"owner_username": current_user.username
		} for photo in photos]

		return {
			"photos": photos_data,
			"pagination": {
				"next_cursor": next_cursor,
				"has_more": has_more,
				"limit": limit
			},
			"counts": {
				"total": total_count,
				"completed": completed_count,
				"failed": failed_count,
				"authorized": authorized_count  # Upload authorized but not yet processed
			}
		}

	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"Error listing photos: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to list photos"
		)

@router.get("/count")
async def get_photo_count(
	request: Request,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""Get user's photo counts by processing status."""
	# Apply photo operations rate limiting
	await rate_limit_photo_operations(request, current_user.id)

	try:
		# Get counts by processing status
		from sqlalchemy import func
		counts_result = await db.execute(
			select(Photo.processing_status, func.count(Photo.id))
			.where(Photo.owner_id == str(current_user.id))
			.group_by(Photo.processing_status)
		)
		counts_by_status = dict(counts_result.fetchall())

		# Calculate totals
		total_count = sum(counts_by_status.values())
		completed_count = counts_by_status.get("completed", 0)
		failed_count = counts_by_status.get("failed", 0)
		authorized_count = counts_by_status.get("authorized", 0)

		return {
			"counts": {
				"total": total_count,
				"completed": completed_count,
				"failed": failed_count,
				"authorized": authorized_count,
				"by_status": counts_by_status
			}
		}

	except Exception as e:
		logger.error(f"Error getting photo counts for user {current_user.id}: {e}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to get photo counts"
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

		# Delete physical files using shared utility
		file_deletion_success = await delete_photo_files(photo)
		if not file_deletion_success:
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail="Failed to delete photo files"
			)

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

def verify_client_signature(signature_base64: str, public_key_pem: str, photo_id: str, filename: str, timestamp: str) -> bool:
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
		# logger.debug(f"Loading client public key for photo {photo_id}, public key pem: {public_key_pem}")
		public_key = serialization.load_pem_public_key(public_key_pem.encode())
		# logger.debug(f"Client public key loaded successfully: {public_key}")

		# Debug public key details
		try:
			public_key_info = public_key.public_numbers()
			# logger.debug(f"Public key curve: {public_key_info.curve.name}")
			# logger.debug(f"Public key x: {public_key_info.x}")
			# logger.debug(f"Public key y: {public_key_info.y}")
		except Exception as key_info_error:
			# logger.debug(f"Could not extract public key info: {key_info_error}")
			pass

		# Recreate the exact message that the client signed
		# This must match the format used by ClientCryptoManager.signUploadData()
		message_data = {
			"photo_id": photo_id,
			"filename": filename,
			"timestamp": timestamp
		}
		message = json.dumps(message_data, separators=(',', ':'), ensure_ascii=False)  # Compact JSON, no spaces, preserve Unicode

		# logger.debug(f"Verifying signature for photo {photo_id}")
		# logger.debug(f"Message to verify: {message}")
		# logger.debug(f"Timestamp used: {timestamp}")
		# logger.debug(f"Signature (base64): {signature_base64}")

		# Decode the base64 signature
		signature_bytes = base64.b64decode(signature_base64)

		# Auto-detect signature format and convert if needed
		# Web Crypto API produces 64-byte IEEE P1363 format (r||s)
		# Android/Java produces variable-length ASN.1 DER format
		if len(signature_bytes) == 64:
			# logger.debug(f"Detected P1363 signature format (64 bytes) - converting to DER")
			# Convert P1363 to DER format
			r = int.from_bytes(signature_bytes[:32], byteorder='big')
			s = int.from_bytes(signature_bytes[32:], byteorder='big')
			# logger.debug(f"P1363 components: r={r}, s={s}")

			try:
				from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
				signature_bytes = encode_dss_signature(r, s)
				# logger.debug(f"DER signature bytes length: {len(signature_bytes)}")
				# logger.debug(f"DER signature hex: {signature_bytes.hex()}")
			except Exception as der_error:
				logger.error(f"DER encoding failed: {type(der_error).__name__}: {der_error}")
				return False
		else:
			# logger.debug(f"Detected DER signature format ({len(signature_bytes)} bytes) - using as-is")
			pass

		# Verify the ECDSA signature
		# logger.debug(f"About to verify signature using cryptography library")
		# logger.debug(f"Message bytes length: {len(message.encode('utf-8'))}")
		# logger.debug(f"Signature bytes length after conversion: {len(signature_bytes)}")

		# Test: Create a self-signature to verify our public key works
		try:
			# logger.debug("Testing public key with self-verification...")
			test_message = b"test message for key verification"
			# We can't self-sign with public key, but we can check key validity
			# logger.debug("Public key appears valid for verification operations")
			pass
		except Exception as key_test_error:
			logger.error(f"Public key test failed: {key_test_error}")

		try:
			public_key.verify(
				signature_bytes,
				message.encode('utf-8'),
				ec.ECDSA(hashes.SHA256())
			)
			# logger.debug(f"Client signature verified for photo {photo_id}")
			return True
		except Exception as verify_error:
			logger.error(f"Cryptography library verification failed: {type(verify_error).__name__}: {verify_error}")

			# Additional debugging: try to understand why verification failed
			# logger.debug("Additional verification debugging:")
			# logger.debug(f"Message (raw string): '{message}'")
			# logger.debug(f"Message (UTF-8 bytes): {message.encode('utf-8')}")
			# logger.debug(f"Message (UTF-8 hex): {message.encode('utf-8').hex()}")
			# logger.debug(f"DER signature length: {len(signature_bytes)} bytes")

			# Check if there might be Unicode normalization issues
			import unicodedata
			normalized_message = unicodedata.normalize('NFC', message)
			if normalized_message != message:
				# logger.debug(f"Unicode normalization difference detected!")
				# logger.debug(f"Normalized message: '{normalized_message}'")
				# logger.debug(f"Normalized UTF-8 hex: {normalized_message.encode('utf-8').hex()}")
				pass
			else:
				# logger.debug("No Unicode normalization issues detected")
				pass

			return False

	except Exception as e:
		logger.error(f"Error in signature verification setup:")
		logger.error(f"{type(e).__name__}: {e}")
		return False
