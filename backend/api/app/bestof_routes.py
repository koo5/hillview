"""Best-of routes – photos ranked by a composite score."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from geoalchemy2.functions import ST_X, ST_Y

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import Photo, PhotoRating, PhotoRatingType, User
from common.utc import format_utc
from auth import get_current_user_optional_with_query
from hidden_content_filters import apply_hidden_content_filters
from rate_limiter import general_rate_limiter
from annotation_routes import effective_annotation_count_subquery

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bestof", tags=["bestof"])


@router.get("/photos")
async def get_best_photos(
	request: Request,
	limit: int = 20,
	cursor: Optional[str] = None,
	db: AsyncSession = Depends(get_db),
	current_user: Optional[User] = Depends(get_current_user_optional_with_query)
):
	"""Get photos ranked by score (likes + annotations + resolution bonus)."""
	await general_rate_limiter.enforce_rate_limit(request, 'public_read', current_user)

	try:
		# Subquery: thumbs-up count per photo
		thumbs_up_sub = (
			select(
				PhotoRating.photo_id,
				func.count(PhotoRating.id).label('thumbs_up_count')
			)
			.where(
				and_(
					PhotoRating.photo_source == 'hillview',
					PhotoRating.rating == PhotoRatingType.THUMBS_UP
				)
			)
			.group_by(PhotoRating.photo_id)
			.subquery('thumbs_up_sub')
		)

		# Subquery: effective annotation count (from annotation controller)
		annotation_sub = effective_annotation_count_subquery()

		# Resolution bonus: floor(max(0, width - 10000) / 1000)
		resolution_bonus = func.floor(
			func.greatest(0, func.coalesce(Photo.width, 0) - 10000) / 10000
		)

		# Total score
		score_expr = (
			func.coalesce(thumbs_up_sub.c.thumbs_up_count, 0)
			+ func.coalesce(annotation_sub.c.annotation_count, 0)
			+ resolution_bonus
		).label('score')

		query = (
			select(
				Photo,
				User.username,
				ST_Y(Photo.geometry).label('latitude'),
				ST_X(Photo.geometry).label('longitude'),
				score_expr
			)
			.join(User, Photo.owner_id == User.id)
			.outerjoin(thumbs_up_sub, Photo.id == thumbs_up_sub.c.photo_id)
			.outerjoin(annotation_sub, Photo.id == annotation_sub.c.photo_id)
			.where(Photo.deleted == False)
			.order_by(score_expr.desc(), Photo.id.desc())
		)

		# Cursor-based pagination: cursor format is "score:photo_id"
		if cursor:
			try:
				parts = cursor.split(':', 1)
				cursor_score = int(parts[0])
				cursor_id = parts[1]
				query = query.where(
					or_(
						score_expr < cursor_score,
						and_(score_expr == cursor_score, Photo.id < cursor_id)
					)
				)
			except (ValueError, IndexError) as e:
				logger.warning(f"Invalid cursor format: {cursor}, error: {e}")
				raise HTTPException(
					status_code=status.HTTP_400_BAD_REQUEST,
					detail="Invalid cursor format"
				)

		query = query.limit(limit + 1)

		# Apply hidden content filtering
		query = apply_hidden_content_filters(
			query,
			current_user.id if current_user else None,
			'hillview'
		)

		result = await db.execute(query)
		photo_results = result.all()

		has_more = len(photo_results) > limit
		if has_more:
			photo_results = photo_results[:-1]

		photos_data = []
		next_cursor = None

		for photo, username, latitude, longitude, score in photo_results:
			score_int = int(score) if score else 0
			photos_data.append({
				"id": photo.id,
				"original_filename": photo.original_filename,
				"description": photo.description,
				"uploaded_at": format_utc(photo.uploaded_at),
				"captured_at": format_utc(photo.captured_at),
				"processing_status": photo.processing_status,
				"latitude": latitude,
				"longitude": longitude,
				"bearing": photo.compass_angle,
				"width": photo.width,
				"height": photo.height,
				"sizes": photo.sizes,
				"owner_username": username,
				"owner_id": photo.owner_id,
				"score": score_int
			})
			next_cursor = f"{score_int}:{photo.id}"

		return {
			"photos": photos_data,
			"has_more": has_more,
			"next_cursor": next_cursor if has_more else None
		}

	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"Error getting best-of photos: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to get best-of photos"
		)
