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
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone

import aiofiles
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from geoalchemy2.functions import ST_Point, ST_X, ST_Y

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))

from push_notifications import send_activity_broadcast_notification, create_notification_for_user
from common.database import get_db
from common.models import Photo, User, PhotoRating, UserPublicKey, PhotoAnnotation, PhotoModerationAudit, UserRole
from common.config import get_write_pool
from common.utc import format_utc
from auth import get_current_active_user, get_current_user_optional_with_query
from hidden_content_filters import apply_hidden_content_filters
from hillview_routes import legal_rights_to_license
from common.file_utils import (
	get_file_size_from_upload
)
from common.security_utils import verify_ecdsa_signature
from rate_limiter import rate_limit_photo_operations, get_client_ip
from photos import delete_photo_files

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

from sqlalchemy import func, and_, or_

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
	retry_after_minutes: Optional[int] = None  # Retry hint for a failed processing: None = permanent, >0 = retry after N minutes
	client_signature: Optional[str] = None  # Base64-encoded ECDSA signature from client
	processed_by_worker: Optional[str] = None  # Worker identity for audit trail
	filename: Optional[str] = None  # Secure filename after processing
	captured_at: Optional[str] = None  # ISO datetime when photo was taken (from EXIF DateTimeOriginal)

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

	if photo.deleted:
		raise HTTPException(
			status_code=status.HTTP_410_GONE,
			detail="Photo was deleted"
		)

	# Verify that photo is in authorized status (not already processed)
	if photo.processing_status != "authorized":
		# If already processed (e.g. a retry after the first request succeeded but
		# the response was lost), return success instead of 400 to make this idempotent.
		if photo.processing_status in ("completed", "error"):
			logger.info(f"Photo {photo_id} already processed (status={photo.processing_status}), returning success for idempotent retry")
			return {"message": "Photo already processed", "photo_id": photo_id}
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
	photo.retry_after_minutes = processed_data.retry_after_minutes  # async clients read this from the status/list/get endpoints
	photo.client_signature = processed_data.client_signature  # Store signature for audit trail
	photo.processed_by_worker = processed_data.processed_by_worker  # Track which worker processed this
	photo.processed_at = datetime.now(timezone.utc)  # When processing was completed
	# Update captured_at from EXIF if worker extracted it
	# Store as naive datetime (assumed UTC) since column is TIMESTAMP WITHOUT TIME ZONE
	if processed_data.captured_at:
		dt = datetime.fromisoformat(processed_data.captured_at.replace('Z', '+00:00'))
		# Convert to UTC if it has timezone, then strip timezone for storage
		if dt.tzinfo is not None:
			dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
		photo.captured_at = dt

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
	request: Request,
	db: AsyncSession = Depends(get_db)
):
	"""Upload processed photo file from worker service to API server storage.

	Metadata is passed via headers to avoid multipart parsing (which blocks the async event loop):
	- X-Photo-Id: photo ID
	- X-Relative-Path: path relative to pics folder
	- X-Client-Signature: ECDSA signature for verification
	"""

	# Read metadata from headers
	photo_id = request.headers.get("X-Photo-Id")
	relative_path = request.headers.get("X-Relative-Path")
	client_signature = request.headers.get("X-Client-Signature")

	if not photo_id or not relative_path or not client_signature:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Missing required headers: X-Photo-Id, X-Relative-Path, X-Client-Signature"
		)

	# Check if CDN is enabled - if so, reject this request
	use_cdn = os.getenv("USE_CDN", "false").lower() in ("true", "1", "yes")
	if use_cdn:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="File uploads not supported when USE_CDN is enabled"
		)

	# --- Phase 1: Validate with DB, then release the session ---
	# All DB work happens here so the connection is freed before the slow file streaming.
	content_length = request.headers.get("Content-Length", "unknown")
	logger.info(f"Processing file upload from worker for photo {photo_id}, path: {relative_path}, size: {content_length} bytes")

	# Get photo from database
	result = await db.execute(select(Photo).where(Photo.id == photo_id))
	photo = result.scalar_one_or_none()
	if not photo:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Photo not found"
		)

	if photo.deleted:
		raise HTTPException(
			status_code=status.HTTP_410_GONE,
			detail="Photo was deleted"
		)

	# Verify that photo is in authorized status
	if photo.processing_status != "authorized":
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Photo not in valid state for file upload: {photo.processing_status}"
		)

	# Get client's public key for signature verification
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

	# Release DB session before the slow file streaming
	await db.close()

	# --- Phase 2: Stream file to disk (no DB connection held) ---
	try:
		# Validate and sanitize the relative path
		if not relative_path or '..' in relative_path or relative_path.startswith('/'):
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Invalid relative path"
			)

		# Construct full file path within the write pool's directory

		write_pool = get_write_pool()
		pics_dir = Path(write_pool["path"])
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

		# Stream body directly to file — avoids multipart spool blocking the event loop
		file_size = 0
		async with aiofiles.open(file_path, 'wb') as f:
			async for chunk in request.stream():
				await f.write(chunk)
				file_size += len(chunk)

		r = {
			"message": "File uploaded successfully",
			"photo_id": photo_id,
			"relative_path": relative_path,
			"file_path": str(file_path),
			"file_size": file_size,
			"url": write_pool["url"] + relative_path
		}

		logger.info(f"Processed file uploaded for photo {photo_id} to {file_path} ({file_size} bytes)")
		return r

	except HTTPException:
		raise
	except Exception as e:
		import traceback
		logger.error(f"Error uploading file for photo {photo_id}: {type(e).__name__}: {e}")
		logger.error(f"Traceback: {traceback.format_exc()}")
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
	include_detections: bool = False,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""List user's photos with cursor-based pagination.

	include_detections: also return each photo's ``detected_objects``
	(anonymization detections). Opt-in — the blobs can be KBs per photo and
	the normal gallery listing doesn't need them. Used by
	``debug_utils.py dump-photos`` to export detections for reuse on another
	server (the pics pipeline's dev-check → prod flow).
	"""
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
	).where(Photo.owner_id == str(current_user.id), Photo.deleted == False)

		if only_processed:
			base_query = base_query.where(Photo.processing_status == "completed")

		# Get counts by processing status (separate query for performance)
		counts_result = await db.execute(
			select(Photo.processing_status, func.count(Photo.id))
			.where(Photo.owner_id == str(current_user.id), Photo.deleted == False)
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
			next_cursor = format_utc(photo_records[-1][0].uploaded_at)

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
				"title": photo.title,
				"description": photo.description,
				"is_public": photo.is_public,
				"latitude": latitude,
				"longitude": longitude,
				"bearing": photo.compass_angle,
				"width": photo.width,
				"height": photo.height,
				"uploaded_at": format_utc(photo.uploaded_at),
				"captured_at": format_utc(photo.captured_at),
				"processing_status": photo.processing_status,
				"error": photo.error,
				"retry_after_minutes": photo.retry_after_minutes,
				"sizes": photo.sizes,
				"owner_id": photo.owner_id,
				"owner_username": current_user.username,
				"user_rating": photo_rating['user_rating'],
				"rating_counts": photo_rating['rating_counts'],
				**({"detected_objects": photo.detected_objects} if include_detections else {})
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
		counts_result = await db.execute(
			select(Photo.processing_status, func.count(Photo.id))
			.where(Photo.owner_id == str(current_user.id), Photo.deleted == False)
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

class PhotoStatusRequest(BaseModel):
	"""Request model for batch photo status query."""
	photo_ids: list[str]

@router.post("/status")
async def get_photos_status(
	request: Request,
	status_request: PhotoStatusRequest,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""Get processing status for a list of photo IDs."""
	await rate_limit_photo_operations(request, current_user.id)

	try:
		if not status_request.photo_ids:
			return {"photos": []}

		result = await db.execute(
			select(Photo.id, Photo.processing_status, Photo.error, Photo.retry_after_minutes, Photo.deleted)
			.where(
				Photo.owner_id == str(current_user.id),
				Photo.id.in_(status_request.photo_ids)
			)
		)
		photos = result.fetchall()

		return {
			"photos": [
				{
					"id": photo.id,
					"processing_status": photo.processing_status,
					"error": photo.error,
					"retry_after_minutes": photo.retry_after_minutes,
					"deleted": photo.deleted
				}
				for photo in photos
			]
		}

	except Exception as e:
		logger.error(f"Error getting photo statuses for user {current_user.id}: {e}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to get photo statuses"
		)

@router.get("/sitemap-ids")
async def get_sitemap_photo_ids(
	offset: int = 0,
	limit: int = 50000,
	db: AsyncSession = Depends(get_db),
):
	"""Public, completed photo identifiers for the XML sitemap (no auth — SEO).

	Returns ``{"total", "photos": [{uid, lastmod, img}, ...]}`` for public,
	non-deleted, completed hillview photos, newest first. ``img`` is the
	preferred rendition URL for the sitemap's ``<image:image>`` entry (may be
	null). Paginated so the frontend sitemap can be a sitemap-index of
	fixed-size child pages and never hit the 50k-URLs-per-file limit.
	``limit=0`` yields just the total (cheap count) for the index to compute
	its page count.

	CURATED: only photos with something worth indexing are listed — featured,
	or carrying a title/description/keywords, or with at least one annotation.
	Bulk title-less uploads are left out so they don't dilute crawl budget /
	site quality; they join automatically once they gain any such signal. They
	stay indexable if found by other means (no noindex).

	NOTE: declared before ``/{photo_id}`` so FastAPI doesn't route this literal
	path into the photo-detail handler.
	"""
	interesting = or_(
		Photo.featured == True,
		and_(Photo.title.isnot(None), Photo.title != ""),
		and_(Photo.description.isnot(None), Photo.description != ""),
		func.array_length(Photo.keywords, 1) > 0,
		select(PhotoAnnotation.id).where(PhotoAnnotation.photo_id == Photo.id).exists(),
	)
	conds = [
		Photo.is_public == True,
		Photo.deleted == False,
		Photo.processing_status == "completed",
		interesting,
	]
	total = await db.scalar(select(func.count()).select_from(Photo).where(*conds))
	rows = (await db.execute(
		select(Photo.id, Photo.uploaded_at, Photo.sizes)
		.where(*conds)
		.order_by(Photo.uploaded_at.desc())
		.offset(offset)
		.limit(limit)
	)).all()

	# Rendition preference for <image:image> entries: the big image-search crop
	# when the worker produced one (wide sources), else the largest flat size.
	img_pref = ('3840_crop', 'full', '4096', '3072', '2048', '1200_crop')

	def sitemap_img(sizes) -> Optional[str]:
		if not isinstance(sizes, dict):
			return None
		for key in img_pref:
			url = (sizes.get(key) or {}).get('url')
			if url:
				return url
		return None

	return {
		"total": total or 0,
		"photos": [
			{"uid": f"hillview-{pid}", "lastmod": format_utc(ts) if ts else None, "img": sitemap_img(sizes)}
			for pid, ts, sizes in rows
		],
	}


@router.get("/moderation-audit")
async def list_moderation_audit(
	request: Request,
	limit: int = 50,
	offset: int = 0,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""List moderation-audit entries (admin/moderator only), newest first.

	Records the moderation actions taken by admins/moderators on photos they did
	not own (currently: deletions). See ``PhotoModerationAudit`` and the DELETE
	handler below.

	NOTE: declared before ``/{photo_id}`` so FastAPI doesn't route this literal
	path into the photo-detail handler.
	"""
	if current_user.role not in (UserRole.ADMIN, UserRole.MODERATOR):
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Admin or moderator access required"
		)

	await rate_limit_photo_operations(request, current_user.id)

	limit = max(1, min(limit, 200))
	offset = max(0, offset)

	result = await db.execute(
		select(PhotoModerationAudit)
		.order_by(PhotoModerationAudit.created_at.desc())
		.limit(limit)
		.offset(offset)
	)
	rows = result.scalars().all()

	return {
		"entries": [
			{
				"id": r.id,
				"action": r.action,
				"actor_user_id": r.actor_user_id,
				"actor_username": r.actor_username,
				"actor_role": r.actor_role,
				"photo_source": r.photo_source,
				"photo_id": r.photo_id,
				"photo_owner_id": r.photo_owner_id,
				"photo_owner_username": r.photo_owner_username,
				"reason": r.reason,
				"extra_data": r.extra_data,
				"created_at": format_utc(r.created_at),
			}
			for r in rows
		]
	}


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
				Photo.owner_id == str(current_user.id),
				Photo.deleted == False
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
			"title": photo.title,
			"description": photo.description,
			"is_public": photo.is_public,
			"latitude": latitude,
			"longitude": longitude,
			"bearing": photo.compass_angle,
			"altitude": photo.altitude,
			"width": photo.width,
			"height": photo.height,
			"captured_at": format_utc(photo.captured_at),
			"uploaded_at": format_utc(photo.uploaded_at),
			"processing_status": photo.processing_status,
			"error": photo.error,
			"retry_after_minutes": photo.retry_after_minutes,
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


@router.get("/{photo_id}/detections")
async def get_photo_detections(
	photo_id: str,
	current_user: Optional[User] = Depends(get_current_user_optional_with_query),
	db: AsyncSession = Depends(get_db)
):
	"""Return the anonymization detections (detected_objects) for a photo.

	Accessible for public photos and for the owner's own photos. Used by the
	frontend debug overlay to visualize what the object detector found.
	"""
	result = await db.execute(
		select(Photo.detected_objects, Photo.is_public, Photo.owner_id, Photo.width, Photo.height).where(
			Photo.id == photo_id,
			Photo.deleted == False
		)
	)
	row = result.first()

	if not row:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Photo not found"
		)

	detected_objects, is_public, owner_id, width, height = row
	is_owner = current_user is not None and owner_id == str(current_user.id)
	if not is_public and not is_owner:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Photo not found"
		)

	return {
		"photo_id": photo_id,
		"detected_objects": detected_objects,
		"width": width,
		"height": height
	}


@router.delete("/{photo_id}")
async def delete_photo(
	request: Request,
	photo_id: str,
	reason: Optional[str] = None,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""Delete a photo's files and mark it as deleted.

	Owners may delete their own photos. Admins and moderators may delete any
	photo; when they delete a photo they do not own, a moderation-audit record is
	written (see ``PhotoModerationAudit``). The optional ``reason`` query param is
	recorded on that audit entry.
	"""
	# Apply photo operations rate limiting
	await rate_limit_photo_operations(request, current_user.id)

	try:
		# Look up by id only — ownership is enforced below so admins/moderators
		# can act on photos they don't own.
		result = await db.execute(
			select(Photo).where(
				Photo.id == photo_id,
				Photo.deleted == False
			)
		)
		photo = result.scalars().first()

		if not photo:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Photo not found"
			)

		is_owner = photo.owner_id == str(current_user.id)
		is_moderator = current_user.role in (UserRole.ADMIN, UserRole.MODERATOR)

		if not is_owner and not is_moderator:
			# Don't reveal the existence of photos the caller can't act on.
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

		# Soft delete - mark as deleted, keep the row
		photo.deleted = True

		# When an admin/moderator deletes a photo they don't own, record a
		# moderation-audit entry. Added to the session so it commits atomically
		# with the soft delete below. The owner is notified (with the reason)
		# after commit.
		notify_owner_id = photo.owner_id if not is_owner else None
		if not is_owner:
			owner_username = await db.scalar(
				select(User.username).where(User.id == photo.owner_id)
			)
			db.add(PhotoModerationAudit(
				action="delete",
				actor_user_id=str(current_user.id),
				actor_username=current_user.username,
				actor_role=current_user.role.value if current_user.role else None,
				photo_source="hillview",
				photo_id=photo.id,
				photo_owner_id=photo.owner_id,
				photo_owner_username=owner_username,
				reason=reason,
				ip_address=get_client_ip(request),
				user_agent=request.headers.get("user-agent"),
				extra_data={
					"original_filename": photo.original_filename,
					"title": photo.title,
				},
			))
			logger.warning(
				f"Moderation: {current_user.role.value} {current_user.username} "
				f"({current_user.id}) deleted photo {photo.id} owned by "
				f"{photo.owner_id} ({owner_username})"
			)

		await db.commit()

		# Explain the removal to the owner when a moderator deleted their photo
		# (best-effort; the delete is already durable). The photo is gone, so no
		# deep link — this is purely informational, carrying the reason if given.
		if notify_owner_id:
			body = reason.strip() if reason and reason.strip() else "A moderator removed one of your photos."
			try:
				await create_notification_for_user(db, notify_owner_id, {
					'type': 'photo_removed',
					'title': 'Your photo was removed by a moderator',
					'body': body,
					'route': None,
				})
			except Exception as e:
				logger.warning(f"photo-removal notify failed for {notify_owner_id}: {e}")

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


def _pick_og_image(sizes: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
	"""Pick the og:image variant for share/SEO cards.

	Prefers the 1.91:1 social-card crop the worker makes for wide-enough images;
	otherwise the largest real (non-crop, non-llm) variant up to 1280px wide —
	the og:image sweet spot without serving a multi-MB original.

	Data-driven rather than a fixed key list: the worker's size set drifts across
	versions (the table still holds legacy 1024/640/1600/50 keys), so a hardcoded
	preference list silently rots. Mirrors the frontend pickOgImage.
	"""
	if not sizes:
		return None
	crop = sizes.get('1200_crop')
	if isinstance(crop, dict) and crop.get('url'):
		return crop
	raw = [
		v for k, v in sizes.items()
		if isinstance(v, dict) and isinstance(v.get('width'), int)
		and 'crop' not in k and 'llm' not in k
	]
	if not raw:
		return None
	capped = [v for v in raw if v['width'] <= 1280]
	pool = capped if capped else raw
	return max(pool, key=lambda v: v['width'])


@router.get("/share/{photo_uid}")
async def get_photo_share_metadata(
	request: Request,
	photo_uid: str,
	db: AsyncSession = Depends(get_db)
):
	"""Get photo metadata for social sharing (no authentication required for SEO/social sharing).

	DEPRECATED: superseded by GET /photos/public/{photo_uid}, which returns a
	richer superset (title, keywords, sizes, owner, ratings) filtered the same way
	(deleted == False; hidden-content filtering is a no-op for anonymous callers).
	The frontend's OpenGraph paths — both the /photo/[uid] detail route and the map
	homepage's ?photo= share cards — now consume /public via the shared
	photoDisplay helpers, so nothing in the app calls this endpoint anymore; only
	tests/integration/test_photo_sharing.py still exercises it. Retire this
	endpoint (and its test) once no external consumer depends on it.
	"""
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
					Photo.title,
					Photo.description,
					ST_X(Photo.geometry).label('longitude'),
					ST_Y(Photo.geometry).label('latitude')
				).where(Photo.id == photo_id, Photo.deleted == False)
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
				og = _pick_og_image(photo_data.sizes)
				if og:
					photo_url = og.get('url')
					width = og.get('width')
					height = og.get('height')

				# Try to find thumbnail (prefer smaller sizes)
				for size_key in ['400', '320', '640']:
					if size_key in photo_data.sizes:
						thumbnail_url = photo_data.sizes[size_key].get('url')
						break

			return {
				"id": photo_data.id,
				"source": "hillview",
				"title": photo_data.title,
				"description": photo_data.description, #f"Photo taken at {photo_data.latitude:.6f}, {photo_data.longitude:.6f}",
				"image_url": photo_url,
				"thumbnail_url": thumbnail_url,
				"width": width,
				"height": height,
				"captured_at": format_utc(photo_data.captured_at) if hasattr(photo_data, 'captured_at') else None,
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


def _curate_exif(exif_data: Optional[dict]) -> Optional[dict]:
	"""Extract a small, display-friendly subset of camera/lens EXIF from the raw
	exiftool dump stored in ``Photo.exif_data`` (worker writes the full tag set
	under ``exif_data['data']`` via ``exiftool -json -n``).

	Only camera settings are exposed (focal length, aperture, ISO, shutter,
	exposure compensation, camera make/model, lens). Positional data
	(GPS/altitude/bearing) is deliberately omitted here — it is already served
	via the response's top-level latitude/longitude/bearing/altitude, and the raw
	dump can carry more precise/sensitive location than we want to publish.

	Returns ``None`` when there is no usable camera EXIF.
	"""
	if not isinstance(exif_data, dict):
		return None
	data = exif_data.get('data')
	if not isinstance(data, dict):
		return None

	def num(key):
		v = data.get(key)
		return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

	def text(key):
		v = data.get(key)
		if v is None:
			return None
		s = str(v).strip()
		return s or None

	curated = {
		'focal_length': num('FocalLength'),
		'focal_length_35mm': num('FocalLengthIn35mmFormat'),
		'f_number': num('FNumber'),
		'iso': num('ISO'),
		'exposure_time': num('ExposureTime'),
		'exposure_compensation': num('ExposureCompensation'),
		'make': text('Make'),
		'model': text('Model'),
		'lens': text('LensModel') or text('LensID') or text('LensInfo'),
	}
	# Drop absent tags; collapse to None when nothing useful survived.
	curated = {k: v for k, v in curated.items() if v is not None}
	return curated or None


@router.get("/public/{photo_uid}")
async def get_public_photo(
	request: Request,
	photo_uid: str,
	current_user: Optional[User] = Depends(get_current_user_optional_with_query),
	db: AsyncSession = Depends(get_db)
):
	"""Get full photo details by composite UID ({source}-{id}) for the detail page.

	Publicly accessible. If the caller is authenticated, the response includes
	their user_rating and an is_own_photo flag. Respects hidden content filters.
	"""
	# Parse composite UID: split on first '-' only (IDs may contain dashes)
	parts = photo_uid.split('-', 1)
	if len(parts) != 2:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Invalid photo UID format"
		)

	source, photo_id = parts

	if source != "hillview":
		raise HTTPException(
			status_code=status.HTTP_501_NOT_IMPLEMENTED,
			detail=f"Public photo details for source '{source}' not yet implemented"
		)

	try:
		query = select(
			Photo,
			ST_X(Photo.geometry).label('longitude'),
			ST_Y(Photo.geometry).label('latitude')
		).where(Photo.id == photo_id, Photo.deleted == False)

		# Apply hidden content filters so users don't see photos they've hidden
		query = apply_hidden_content_filters(
			query,
			current_user.id if current_user else None,
			'hillview'
		)

		result = await db.execute(query)
		photo_record = result.first()

		if not photo_record:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Photo not found"
			)

		photo, longitude, latitude = photo_record

		# Look up owner username
		owner_username = None
		if photo.owner_id:
			owner_result = await db.execute(
				select(User.username).where(User.id == photo.owner_id)
			)
			owner_username = owner_result.scalar_one_or_none()

		# Get rating data (uses current_user.id if present, else returns counts only)
		ratings_data = await get_ratings_for_photos(
			db, [photo.id], current_user.id if current_user else None
		)
		photo_rating = ratings_data.get(photo.id, {
			'user_rating': None,
			'rating_counts': {'thumbs_up': 0, 'thumbs_down': 0}
		})

		is_own_photo = bool(current_user and str(current_user.id) == str(photo.owner_id))

		return {
			"id": photo.id,
			"uid": f"hillview-{photo.id}",
			"source": "hillview",
			"filename": photo.filename,
			"original_filename": photo.original_filename,
			"title": photo.title,
			"description": photo.description,
			"keywords": photo.keywords,
			"place_name": photo.place_name,
			"license": legal_rights_to_license(photo.legal_rights),
			"is_public": photo.is_public,
			"latitude": latitude,
			"longitude": longitude,
			"bearing": photo.compass_angle,
			"altitude": photo.altitude,
			"width": photo.width,
			"height": photo.height,
			"exif": _curate_exif(photo.exif_data),
			"captured_at": format_utc(photo.captured_at),
			"uploaded_at": format_utc(photo.uploaded_at),
			"processing_status": photo.processing_status,
			"sizes": photo.sizes,
			"owner_id": photo.owner_id,
			"owner_username": owner_username,
			"user_rating": photo_rating['user_rating'],
			"rating_counts": photo_rating['rating_counts'],
			"is_own_photo": is_own_photo
		}

	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"Error getting public photo {photo_uid}: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to get photo"
		)
