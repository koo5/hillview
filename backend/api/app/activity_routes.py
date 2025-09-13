"""Activity routes for recent photo activity across all users."""
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

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
	limit: int = 100,
	db: AsyncSession = Depends(get_db),
	current_user: Optional[User] = Depends(get_current_user_optional_with_query)
):
	"""Get last 100 photos across all users with user information for activity feed."""
	# Apply general rate limiting
	await general_rate_limiter.enforce_rate_limit(request, 'activity_recent')
	
	try:
		# Join Photo with User to get usernames for all photos
		query = select(Photo, User.username).join(
			User, Photo.owner_id == User.id
		).order_by(Photo.uploaded_at.desc()).limit(limit)
		
		# Apply hidden content filtering
		query = apply_hidden_content_filters(
			query,
			current_user.id if current_user else None,
			'hillview'
		)
		
		result = await db.execute(query)
		photo_user_pairs = result.all()
		
		activity_data = []
		for photo, username in photo_user_pairs:
			activity_data.append({
				"id": photo.id,
				"original_filename": photo.original_filename,
				"uploaded_at": photo.uploaded_at.isoformat() if photo.uploaded_at else None,
				"processing_status": photo.processing_status,
				"latitude": photo.latitude,
				"longitude": photo.longitude,
				"width": photo.width,
				"height": photo.height,
				"sizes": photo.sizes,
				"owner_username": username,
				"owner_id": photo.owner_id
			})
		
		return activity_data
		
	except Exception as e:
		logger.error(f"Error getting recent activity: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to get recent activity"
		)