import json
import os
import sys
import logging
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Query, HTTPException, status, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from geoalchemy2.functions import ST_MakeEnvelope, ST_Within, ST_X, ST_Y

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import Photo, User
from common.utc import format_utc
from hidden_content_filters import apply_hidden_content_filters
from auth import get_current_user_optional_with_query, get_current_user_optional
from rate_limiter import rate_limit_public_read, general_rate_limiter

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

router = APIRouter(prefix="/api/hillview", tags=["hillview"])


def convert_photo_to_response(photo, username: str, longitude: float, latitude: float) -> Dict[str, Any]:
	"""Convert a Photo object to the response format"""
	photo_data = {
		'id': photo.id,
		'geometry': {
			'coordinates': [longitude, latitude]
		},
		'bearing': photo.compass_angle or 0,
		'computed_altitude': photo.altitude or 0,
		'captured_at': format_utc(photo.captured_at),
		'is_pano': False,
		'filename': photo.filename,
		'sizes': {},
		'creator': {
			'username': username,
			'id': photo.owner_id
		}
	}

	# Add sizes if available
	for k, v in (photo.sizes or {}).items():
		photo_data['sizes'][k] = {
			'url': v.get('url'),
			'width': v.get('width'),
			'height': v.get('height')
		}

	# Add file hash if available for deduplication
	if photo.file_md5:
		photo_data['file_md5'] = photo.file_md5

	return photo_data


async def query_photos_in_bounds(
	db: AsyncSession,
	bbox,
	current_user_id: Optional[str],
	exclude_ids: Optional[List[str]] = None,
	limit: Optional[int] = None
) -> List[Dict[str, Any]]:
	"""Query photos within bounds, with optional exclusions and limit"""
	query = select(
		Photo,
		User.username,
		ST_X(Photo.geometry).label('longitude'),
		ST_Y(Photo.geometry).label('latitude')
	).join(User, Photo.owner_id == User.id).where(
		Photo.geometry.isnot(None),
		ST_Within(Photo.geometry, bbox),
		Photo.is_public == True
	).order_by(Photo.captured_at.desc())

	# Exclude specific photo IDs if provided
	if exclude_ids:
		query = query.where(Photo.id.notin_(exclude_ids))

	# Apply limit if specified
	if limit:
		query = query.limit(limit)

	# Apply hidden content filtering
	query = apply_hidden_content_filters(
		query,
		current_user_id,
		'hillview'
	)

	result = await db.execute(query)
	records = result.all()

	# Convert to response format
	photos = []
	for photo, username, longitude, latitude in records:
		photos.append(convert_photo_to_response(photo, username, longitude, latitude))

	return photos


async def query_picked_photos(
	db: AsyncSession,
	bbox,
	picked_ids: List[str],
	current_user_id: Optional[str]
) -> List[Dict[str, Any]]:
	"""Query specific picked photos that are within bounds"""
	if not picked_ids:
		return []

	query = select(
		Photo,
		User.username,
		ST_X(Photo.geometry).label('longitude'),
		ST_Y(Photo.geometry).label('latitude')
	).join(User, Photo.owner_id == User.id).where(
		Photo.geometry.isnot(None),
		Photo.id.in_(picked_ids),
		ST_Within(Photo.geometry, bbox),
		Photo.is_public == True
	)

	# Apply hidden content filtering
	query = apply_hidden_content_filters(
		query,
		current_user_id,
		'hillview'
	)

	result = await db.execute(query)
	records = result.all()

	# Convert to response format
	photos = []
	for photo, username, longitude, latitude in records:
		photos.append(convert_photo_to_response(photo, username, longitude, latitude))

	return photos


@router.get("")
async def get_hillview_images(
	request: Request,
	top_left_lat: float = Query(..., description="Top left latitude"),
	top_left_lon: float = Query(..., description="Top left longitude"),
	bottom_right_lat: float = Query(..., description="Bottom right latitude"),
	bottom_right_lon: float = Query(..., description="Bottom right longitude"),
	client_id: str = Query(..., description="Client ID"),
	picks: str = Query(None, description="Comma-separated list of picked photo IDs"),
	max_photos: int = Query(400, description="Maximum number of photos to return"),
	db: AsyncSession = Depends(get_db),
	current_user: Optional[User] = Depends(get_current_user_optional_with_query)
):
	"""Get Hillview images from database filtered by bounding box area"""
	# Apply rate limiting with optional user context (better limits for authenticated users)
	await general_rate_limiter.enforce_rate_limit(request, 'public_read', current_user)

	try:
		# Parse picks parameter if provided
		picked_ids = []
		if picks:
			picked_ids = [id.strip() for id in picks.split(',') if id.strip()]
			log.debug(f"Processing picks: {picked_ids}")

		# Create bounding box geometry (min_lng, min_lat, max_lng, max_lat, srid)
		bbox = ST_MakeEnvelope(top_left_lon, bottom_right_lat, bottom_right_lon, top_left_lat, 4326)

		log.debug(f"Querying photos from database for bbox: {top_left_lat}, {top_left_lon}, {bottom_right_lat}, {bottom_right_lon}")
		log.info(f"Hillview endpoint - current_user: {current_user.username if current_user else 'None'} (ID: {current_user.id if current_user else 'None'})")

		current_user_id = current_user.id if current_user else None

		# Get picked photos first (they have priority)
		picked_photos = await query_picked_photos(db, bbox, picked_ids, current_user_id)
		log.info(f"Found {len(picked_photos)} picked photos in bounds")

		# Get regular photos up to the limit minus picked photos
		remaining_limit = max_photos - len(picked_photos)
		regular_photos = []
		if remaining_limit > 0:
			regular_photos = await query_photos_in_bounds(
				db, bbox, current_user_id,
				exclude_ids=picked_ids,
				limit=remaining_limit
			)
			log.info(f"Found {len(regular_photos)} regular photos")

		# Combine picked photos first, then regular photos
		filtered_photos = picked_photos + regular_photos
		log.info(f"Found {len(filtered_photos)} total photos in database for bbox (max_photos: {max_photos})")

		# Create generator for EventSource streaming
		async def generate_stream():
			try:
				# Send the data as a single event with proper type field
				data = {
					'type': 'photos',
					'photos': filtered_photos,
					'total_count': len(filtered_photos),
					'hasNext': False,  # Hillview returns all photos in one batch
					'bbox': {
						'top_left_lat': top_left_lat,
						'top_left_lon': top_left_lon,
						'bottom_right_lat': bottom_right_lat,
						'bottom_right_lon': bottom_right_lon
					}
				}
				yield f"data: {json.dumps(data)}\n\n"

				# Send completion event to match Mapillary behavior
				yield f"data: {json.dumps({'type': 'stream_complete', 'total_live_photos': 0, 'total_cached_photos': len(filtered_photos), 'total_all_photos': len(filtered_photos)})}\n\n"

			except Exception as e:
				log.error(f"Stream error in hillview endpoint: {str(e)}")
				yield f"data: {json.dumps({'type': 'error', 'message': f'Stream error: {str(e)}'})}\n\n"

		# Return EventSource streaming response
		return StreamingResponse(
			generate_stream(),
			media_type="text/event-stream",
			headers={
				"Cache-Control": "no-cache, no-store, must-revalidate",
				"Connection": "keep-alive",
				"Access-Control-Allow-Origin": "*",
				"Access-Control-Allow-Headers": "Cache-Control, Content-Type, Authorization",
				"Access-Control-Allow-Methods": "GET, OPTIONS",
				"Access-Control-Expose-Headers": "*",
				"X-Accel-Buffering": "no",  # Disable nginx buffering
				"Content-Type": "text/event-stream; charset=utf-8"
			}
		)

	except Exception as e:
		log.error(f"Error querying photos from database: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Database error: {str(e)}"
		)