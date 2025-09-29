import json
import os
from typing import Optional, Dict, Any
import logging
from fastapi import APIRouter, Query, HTTPException, status, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import Photo, User
from hidden_content_filters import apply_hidden_content_filters
from auth import get_current_user_optional_with_query, get_current_user_optional
from rate_limiter import rate_limit_public_read, general_rate_limiter

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

router = APIRouter(prefix="/api/hillview", tags=["hillview"])


@router.get("")
async def get_hillview_images(
	request: Request,
	top_left_lat: float = Query(..., description="Top left latitude"),
	top_left_lon: float = Query(..., description="Top left longitude"),
	bottom_right_lat: float = Query(..., description="Bottom right latitude"),
	bottom_right_lon: float = Query(..., description="Bottom right longitude"),
	client_id: str = Query(..., description="Client ID"),
	db: AsyncSession = Depends(get_db),
	current_user: Optional[User] = Depends(get_current_user_optional_with_query)
):
	"""Get Hillview images from database filtered by bounding box area"""
	# Apply rate limiting with optional user context (better limits for authenticated users)
	await general_rate_limiter.enforce_rate_limit(request, 'public_read', current_user)

	try:
		# Query photos from database that fall within the bounding box
		# Join with User table to get owner information
		query = select(Photo, User.username).join(User, Photo.owner_id == User.id).where(
			Photo.latitude.isnot(None),
			Photo.longitude.isnot(None),
			Photo.latitude >= bottom_right_lat,
			Photo.latitude <= top_left_lat,
			Photo.longitude >= top_left_lon,
			Photo.longitude <= bottom_right_lon,
			Photo.is_public == True
		)

		log.debug(f"Querying photos from database for bbox: {top_left_lat}, {top_left_lon}, {bottom_right_lat}, {bottom_right_lon}, query: {query}")
		log.info(f"Hillview endpoint - current_user: {current_user.username if current_user else 'None'} (ID: {current_user.id if current_user else 'None'})")

		# Apply hidden content filtering
		query = apply_hidden_content_filters(
			query,
			current_user.id if current_user else None,
			'hillview'
		)

		result = await db.execute(query)
		photo_user_pairs = result.all()

		# Transform photos to match Mapillary-like structure
		filtered_photos = []

		for photo, username in photo_user_pairs:
			photo_data = {
				'id': photo.id,
				'geometry': {
					'coordinates': [photo.longitude, photo.latitude]
				},
				'bearing': photo.compass_angle or 0,
				'computed_rotation': 0,
				'computed_bearing': photo.compass_angle or 0,
				'computed_altitude': photo.altitude or 0,
				'captured_at': photo.captured_at.isoformat() if photo.captured_at else '',
				'is_pano': False,
				'filename': photo.filename,
				'sizes': photo.sizes or {},
				# Add creator info to match Mapillary format
				'creator': {
					'username': username,
					'id': photo.owner_id
				}
			}
			filtered_photos.append(photo_data)

		# Sort by bearing like Mapillary endpoint
		filtered_photos.sort(key=lambda x: x.get('bearing', 0))

		log.info(f"Found {len(filtered_photos)} photos in database for bbox")

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
