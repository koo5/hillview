"""Activity routes for recent photo activity across all users."""
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from geoalchemy2.functions import ST_X, ST_Y

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import Photo, User
from auth import get_current_user_optional_with_query
from hidden_content_filters import apply_hidden_content_filters
from rate_limiter import general_rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/activity", tags=["activity"])

@router.get("/recent")
async def get_recent_activity(
	request: Request,
	limit: int = 20,
	cursor: Optional[str] = None,
	db: AsyncSession = Depends(get_db),
	current_user: Optional[User] = Depends(get_current_user_optional_with_query)
):
	"""Get recent photos across all users with cursor-based pagination for activity feed."""
	# Apply rate limiting with optional user context (better limits for authenticated users)
	await general_rate_limiter.enforce_rate_limit(request, 'public_read', current_user)

	try:
		# Join Photo with User to get usernames for all photos, and extract coordinates from geometry
		query = select(
			Photo,
			User.username,
			ST_Y(Photo.geometry).label('latitude'),
			ST_X(Photo.geometry).label('longitude')
		).join(
			User, Photo.owner_id == User.id
		).order_by(Photo.uploaded_at.desc())

		# Apply cursor-based pagination if cursor is provided
		if cursor:
			try:
				# Cursor is the uploaded_at timestamp of the last photo from previous page
				cursor_datetime = datetime.fromisoformat(cursor.replace('Z', '+00:00'))
				query = query.filter(Photo.uploaded_at < cursor_datetime)
			except (ValueError, TypeError) as e:
				logger.warning(f"Invalid cursor format: {cursor}, error: {e}")
				raise HTTPException(
					status_code=status.HTTP_400_BAD_REQUEST,
					detail="Invalid cursor format"
				)

		# Apply limit
		query = query.limit(limit + 1)  # Fetch one extra to determine if there are more results

		# Apply hidden content filtering
		query = apply_hidden_content_filters(
			query,
			current_user.id if current_user else None,
			'hillview'
		)

		result = await db.execute(query)
		photo_results = result.all()

		# Determine if there are more results
		has_more = len(photo_results) > limit
		if has_more:
			photo_results = photo_results[:-1]  # Remove the extra item

		activity_data = []
		next_cursor = None

		for photo, username, latitude, longitude in photo_results:
			activity_data.append({
				"id": photo.id,
				"original_filename": photo.original_filename,
				"uploaded_at": photo.uploaded_at.isoformat() if photo.uploaded_at else None,
				"processing_status": photo.processing_status,
				"latitude": latitude,
				"longitude": longitude,
				"bearing": photo.compass_angle,
				"width": photo.width,
				"height": photo.height,
				"sizes": photo.sizes,
				"owner_username": username,
				"owner_id": photo.owner_id
			})

			# Set next_cursor to the last photo's uploaded_at timestamp
			if photo.uploaded_at:
				next_cursor = photo.uploaded_at.isoformat()

		return {
			"photos": activity_data,
			"has_more": has_more,
			"next_cursor": next_cursor if has_more else None
		}

	except HTTPException:
		raise  # Re-raise HTTP exceptions (like bad cursor format)
	except Exception as e:
		logger.error(f"Error getting recent activity: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to get recent activity"
		)