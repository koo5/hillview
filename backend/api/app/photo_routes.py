"""Photo upload and management routes with security."""

"""
-       SIGNATURE VERIFICATION SCHEME:
-       =============================
-
-       This function is the critical security checkpoint that prevents compromised workers
-       from impersonating users. Here's how the three-phase upload process works:
-
-       Phase 1 - Upload Authorization (Client → API Server):
-       - Client calls /api/photos/authorize-upload with file metadata
-       - API server creates pending photo record with status="authorized"
-       - API server returns upload_jwt signed with API server's private key
-       - upload_jwt contains: photo_id, user_id, client_public_key_id
-
-       Phase 2 - Signed Upload (Client → Worker):
-       - Client signs upload payload: {photo_id, filename, timestamp} with their ECDSA private key
-       - Client sends: upload_jwt + file + client_signature to worker
-       - Worker verifies upload_jwt using API server's public key (validates authorization)
-       - Worker processes file but does NOT verify client signature (zero-trust worker)
-       - Worker sends processed results + client_signature back to API server
-
-       Phase 3 - Result Storage (Worker → API Server) ← WE ARE HERE
-       - API server receives processed results + client_signature from worker
-       - API server loads client's public key from database (client_public_key_id from photo record)
-       - API server recreates the exact message that client signed: {photo_id, filename, timestamp}
-       - API server verifies client_signature using client's public key
-       - Only saves results if signature is valid - this prevents worker impersonation!
-
-       WHY THIS WORKS:
-       ===============
-       - Worker cannot forge client signatures (doesn't have client's private key)
-       - Worker cannot modify upload metadata (signature verification would fail)
-       - Even if worker is completely compromised, it cannot impersonate users
-       - Provides cryptographic proof that the client authorized this specific upload
-       - Signature is stored in database for audit trail and non-repudiation
"""

import os
import sys
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
from geoalchemy2.functions import ST_Point, ST_X, ST_Y

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))

from push_notifications import send_activity_broadcast_notification
from common.database import get_db
from common.models import Photo, User, PhotoRating, PhotoRatingType
from auth import get_current_active_user
from common.file_utils import (
	validate_and_prepare_photo_file,
	verify_saved_file_content,
	cleanup_file_on_error,
	get_file_size_from_upload
)
from common.security_utils import verify_ecdsa_signature
from jwt_service import validate_token
from rate_limiter import rate_limit_photo_upload, rate_limit_photo_operations
from photos import delete_photo_files, determine_storage_type, StorageType

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


logger = logging.getLogger(__name__)
logger.debug("DEBUG")
logger.info("INFO")
logger.warning("WARNING")

router = APIRouter(prefix="/api/photos", tags=["photos"])

# Upload directory configuration
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(exist_ok=True)

from sqlalchemy import func, and_

async def get_ratings_for_photos(db: AsyncSession, photo_ids: list, user_id: str) -> dict:
	"""Get ratings data for a list of photo IDs.

	Returns dict mapping photo_id to {user_rating, rating_counts}
	"""
	if not photo_ids:
		return {}

	# Get all ratings for these photos
	result = await db.execute(
		select(
			PhotoRating.photo_id,
			PhotoRating.rating,
			PhotoRating.user_id
		).where(
			and_(
				PhotoRating.photo_source == 'hillview',
				PhotoRating.photo_id.in_([str(pid) for pid in photo_ids])
			)
		)
	)

	# Build rating counts and user ratings
	ratings_data = {}
	for photo_id, rating, rating_user_id in result.fetchall():
		if photo_id not in ratings_data:
			ratings_data[photo_id] = {
				'user_rating': None,
				'rating_counts': {'thumbs_up': 0, 'thumbs_down': 0}
			}

		# Increment count
		rating_key = rating.value.lower()
		ratings_data[photo_id]['rating_counts'][rating_key] += 1

		# Check if this is the current user's rating
		if str(rating_user_id) == str(user_id):
			ratings_data[photo_id]['user_rating'] = rating_key

	return ratings_data

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
	if not verify_ecdsa_signature(
		signature_base64=processed_data.client_signature,
		public_key_pem=client_public_key.public_key_pem,
		message_data=[
			photo.original_filename,
			photo_id,
			int(photo.upload_authorized_at.timestamp())
		]
	):
		logger.error(f"Client signature verification failed for photo {photo_id}")
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Client signature verification failed"
		)

	logger.info(f"Client signature verified for photo {photo_id}")

	# Update photo with processed data, store signature, and track worker identity

	if processed_data.processing_status not in ("completed", "error"):
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Invalid processing status"
		)

	# Validate bearing/compass_angle is in valid range [0, 360]
	if processed_data.compass_angle is not None:
		if processed_data.compass_angle < 0 or processed_data.compass_angle > 360:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=f"Invalid bearing value: {processed_data.compass_angle}. Must be between 0 and 360 degrees."
			)

	photo.processing_status = processed_data.processing_status
	photo.width = processed_data.width
	photo.height = processed_data.height
	# Update filename after successful processing
	if processed_data.filename:
		photo.filename = processed_data.filename
	# Overwrite client-supplied geolocation data from authorization if EXIF/processing provides better data
	if processed_data.latitude is not None and processed_data.longitude is not None:
		# Create PostGIS geometry from lat/lng
		photo.geometry = ST_Point(processed_data.longitude, processed_data.latitude, 4326)
	elif processed_data.latitude is not None or processed_data.longitude is not None:
		# If only one coordinate is provided, set geometry to None (incomplete data)
		photo.geometry = None
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

	# Send activity broadcast notification - wrapped in try/except so notification
	# errors don't fail the photo upload
	try:
		await send_activity_broadcast_notification(db, photo.owner_id)
	except Exception as e:
		logger.warning(f"Failed to send activity broadcast notification for photo {photo_id}: {e}")
		# Don't re-raise - photo upload succeeded, notification is non-critical

	return {
		"message": "Processed photo data saved successfully",
		"photo_id": photo.id
	}


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
		logger.info(f"Processing file upload from worker for photo {photo_id}, path: {relative_path}")

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

		if not verify_ecdsa_signature(
			signature_base64=client_signature,
			public_key_pem=client_public_key.public_key_pem,
			message_data=[
			photo.original_filename,
			photo_id,
			int(photo.upload_authorized_at.timestamp())
			]
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

		r = {
			"message": "File uploaded successfully",
			"photo_id": photo_id,
			"relative_path": relative_path,
			"file_path": str(file_path),
			"file_size": file_size
		}

		logger.info(f"Processed file uploaded for photo {photo_id} to {file_path} ({file_size} bytes)")
		return r



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

		base_query = select(
		Photo,
		ST_X(Photo.geometry).label('longitude'),
		ST_Y(Photo.geometry).label('latitude')
	).where(Photo.owner_id == str(current_user.id))

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
		photo_records = result.all()

		# Check if there are more photos
		has_more = len(photo_records) > limit
		if has_more:
			photo_records = photo_records[:-1]  # Remove the extra photo

		# Generate next cursor
		next_cursor = None
		if has_more and photo_records:
			next_cursor = photo_records[-1][0].uploaded_at.isoformat()

		# Fetch ratings for all photos in one query
		photo_ids = [photo.id for photo, _, _ in photo_records]
		ratings_data = await get_ratings_for_photos(db, photo_ids, current_user.id)

		photos_data = []
		for photo, longitude, latitude in photo_records:
			photo_rating = ratings_data.get(photo.id, {
				'user_rating': None,
				'rating_counts': {'thumbs_up': 0, 'thumbs_down': 0}
			})
			photos_data.append({
				"id": photo.id,
				"filename": photo.filename,
				"original_filename": photo.original_filename,
				"description": photo.description,
				"is_public": photo.is_public,
				"latitude": latitude,
				"longitude": longitude,
				"bearing": photo.compass_angle,
				"width": photo.width,
				"height": photo.height,
				"uploaded_at": photo.uploaded_at,
				"captured_at": photo.captured_at,
				"processing_status": photo.processing_status,
				"error": photo.error,
				"sizes": photo.sizes,
				"owner_id": photo.owner_id,
				"owner_username": current_user.username,
				"user_rating": photo_rating['user_rating'],
				"rating_counts": photo_rating['rating_counts']
			})

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
			select(
				Photo,
				ST_X(Photo.geometry).label('longitude'),
				ST_Y(Photo.geometry).label('latitude')
			).where(
				Photo.id == photo_id,
				Photo.owner_id == str(current_user.id)
			)
		)
		photo_record = result.first()

		if not photo_record:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Photo not found"
			)

		photo, longitude, latitude = photo_record

		# Get rating data for this photo
		ratings_data = await get_ratings_for_photos(db, [photo.id], current_user.id)
		photo_rating = ratings_data.get(photo.id, {
			'user_rating': None,
			'rating_counts': {'thumbs_up': 0, 'thumbs_down': 0}
		})

		return {
			"id": photo.id,
			"filename": photo.filename,
			"original_filename": photo.original_filename,
			"description": photo.description,
			"is_public": photo.is_public,
			"latitude": latitude,
			"longitude": longitude,
			"bearing": photo.compass_angle,
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
			"owner_username": current_user.username,  # Since this is the current user's photo
			"user_rating": photo_rating['user_rating'],
			"rating_counts": photo_rating['rating_counts']
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


@router.get("/share/{photo_uid}")
async def get_photo_share_metadata(
	request: Request,
	photo_uid: str,
	db: AsyncSession = Depends(get_db)
):
	"""Get photo metadata for social sharing (no authentication required for SEO/social sharing)."""
	try:
		# Parse photo UID format: {source}-{id}
		parts = photo_uid.split('-', 1)
		if len(parts) != 2:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Invalid photo UID format"
			)

		source, photo_id = parts

		if source == "hillview":
			# Query Hillview photos from the database
			result = await db.execute(
				select(
					Photo.id,
					Photo.original_filename,
					Photo.captured_at,
					Photo.sizes,
					Photo.description,
					ST_X(Photo.geometry).label('longitude'),
					ST_Y(Photo.geometry).label('latitude')
				).where(Photo.id == photo_id)
			)

			photo_data = result.first()
			if not photo_data:
				raise HTTPException(
					status_code=status.HTTP_404_NOT_FOUND,
					detail="Photo not found"
				)

			# Extract image URL from sizes JSON
			photo_url = None
			thumbnail_url = None
			width = None
			height = None

			if photo_data.sizes:
				# Try to find a good resolution for OpenGraph (prefer 1024 or 800)
				for size_key in	 ['full']:
					if size_key in photo_data.sizes:
						size_data = photo_data.sizes[size_key]
						photo_url = size_data.get('url')
						width = size_data.get('width')
						height = size_data.get('height')
						break

				# Try to find thumbnail (prefer smaller sizes)
				for size_key in ['400', '320']:
					if size_key in photo_data.sizes:
						thumbnail_url = photo_data.sizes[size_key].get('url')
						break

			return {
				"id": photo_data.id,
				"source": "hillview",
				"description": photo_data.description, #f"Photo taken at {photo_data.latitude:.6f}, {photo_data.longitude:.6f}",
				"image_url": photo_url,
				"thumbnail_url": thumbnail_url,
				"width": width,
				"height": height,
				"captured_at": photo_data.captured_at.isoformat() if hasattr(photo_data, 'captured_at') and photo_data.captured_at else None,
				"latitude": photo_data.latitude,
				"longitude": photo_data.longitude
			}

		elif source == "mapillary":
			# For Mapillary photos, we'd need to implement lookup from cached data
			# For now, return basic info
			raise HTTPException(
				status_code=status.HTTP_501_NOT_IMPLEMENTED,
				detail="Mapillary photo metadata not yet implemented"
			)
		else:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=f"Unknown photo source: {source}"
			)

	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"Error getting photo metadata for sharing: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to get photo metadata"
		)
