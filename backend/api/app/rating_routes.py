"""Photo rating routes for thumbs up/down functionality."""
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, delete

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import PhotoRating, PhotoRatingType, User
from auth import get_current_active_user
from rate_limiter import rate_limit_photo_operations

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ratings", tags=["ratings"])

# Request/Response models
class RatingRequest(BaseModel):
    rating: str  # 'thumbs_up' or 'thumbs_down'

class RatingResponse(BaseModel):
    user_rating: Optional[str] = None  # User's current rating or None
    rating_counts: Dict[str, int]  # Aggregate counts

class RatingDeleteResponse(BaseModel):
    message: str
    rating_counts: Dict[str, int]

# Validate photo source
VALID_SOURCES = {'hillview', 'mapillary'}

def validate_photo_source(source: str) -> str:
    """Validate and return photo source."""
    if source not in VALID_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid photo source. Must be one of: {', '.join(VALID_SOURCES)}"
        )
    return source

def validate_rating_type(rating: str) -> PhotoRatingType:
    """Validate and convert rating string to enum."""
    rating_map = {
        'thumbs_up': PhotoRatingType.THUMBS_UP,
        'thumbs_down': PhotoRatingType.THUMBS_DOWN
    }
    
    if rating not in rating_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid rating. Must be 'thumbs_up' or 'thumbs_down'"
        )
    
    return rating_map[rating]

async def get_rating_counts(
    db: AsyncSession,
    photo_source: str, 
    photo_id: str
) -> Dict[str, int]:
    """Get aggregated rating counts for a photo."""
    result = await db.execute(
        select(
            PhotoRating.rating,
            func.count(PhotoRating.id)
        )
        .where(
            and_(
                PhotoRating.photo_source == photo_source,
                PhotoRating.photo_id == photo_id
            )
        )
        .group_by(PhotoRating.rating)
    )
    
    counts = {'thumbs_up': 0, 'thumbs_down': 0}
    for rating, count in result.fetchall():
        counts[rating.value.lower()] = count
    
    return counts

@router.post("/{source}/{photo_id}", response_model=RatingResponse)
async def set_photo_rating(
    source: str,
    photo_id: str,
    rating_request: RatingRequest,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Set or update a user's rating for a photo."""
    
    # Apply rate limiting
    await rate_limit_photo_operations(request, current_user.id)
    
    # Validate inputs
    photo_source = validate_photo_source(source)
    rating_type = validate_rating_type(rating_request.rating)
    
    logger.info(f"Setting {rating_type.value} rating for {photo_source} photo {photo_id} by user {current_user.id}")
    
    try:
        # Check if user already has a rating for this photo
        existing_rating_query = select(PhotoRating).where(
            and_(
                PhotoRating.user_id == current_user.id,
                PhotoRating.photo_source == photo_source,
                PhotoRating.photo_id == photo_id
            )
        )
        result = await db.execute(existing_rating_query)
        existing_rating = result.scalars().first()
        
        if existing_rating:
            # Update existing rating
            existing_rating.rating = rating_type
            logger.info(f"Updated existing rating to {rating_type.value}")
        else:
            # Create new rating
            new_rating = PhotoRating(
                user_id=current_user.id,
                photo_source=photo_source,
                photo_id=photo_id,
                rating=rating_type
            )
            db.add(new_rating)
            logger.info(f"Created new rating: {rating_type.value}")
        
        await db.commit()
        
        # Get updated counts and user's current rating
        rating_counts = await get_rating_counts(db, photo_source, photo_id)
        
        return RatingResponse(
            user_rating=rating_type.value.lower(),
            rating_counts=rating_counts
        )
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error setting rating: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set rating"
        )

@router.delete("/{source}/{photo_id}", response_model=RatingDeleteResponse)
async def delete_photo_rating(
    source: str,
    photo_id: str,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove a user's rating for a photo."""
    
    # Apply rate limiting
    await rate_limit_photo_operations(request, current_user.id)
    
    # Validate inputs
    photo_source = validate_photo_source(source)
    
    logger.info(f"Removing rating for {photo_source} photo {photo_id} by user {current_user.id}")
    
    try:
        # Find and delete the user's rating
        rating_query = select(PhotoRating).where(
            and_(
                PhotoRating.user_id == current_user.id,
                PhotoRating.photo_source == photo_source,
                PhotoRating.photo_id == photo_id
            )
        )
        result = await db.execute(rating_query)
        rating = result.scalars().first()
        
        if not rating:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rating not found"
            )
        
        await db.execute(delete(PhotoRating).where(PhotoRating.id == rating.id))
        await db.commit()
        
        logger.info(f"Removed {rating.rating.value} rating")
        
        # Get updated counts
        rating_counts = await get_rating_counts(db, photo_source, photo_id)
        
        return RatingDeleteResponse(
            message="Rating removed successfully",
            rating_counts=rating_counts
        )
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error removing rating: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove rating"
        )

@router.get("/{source}/{photo_id}", response_model=RatingResponse)
async def get_photo_rating(
    source: str,
    photo_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get rating information for a photo."""
    
    # Validate inputs
    photo_source = validate_photo_source(source)
    
    try:
        # Get user's current rating
        user_rating_query = select(PhotoRating).where(
            and_(
                PhotoRating.user_id == current_user.id,
                PhotoRating.photo_source == photo_source,
                PhotoRating.photo_id == photo_id
            )
        )
        result = await db.execute(user_rating_query)
        user_rating = result.scalars().first()
        
        # Get rating counts
        rating_counts = await get_rating_counts(db, photo_source, photo_id)
        
        return RatingResponse(
            user_rating=user_rating.rating.value.lower() if user_rating else None,
            rating_counts=rating_counts
        )
        
    except Exception as e:
        logger.error(f"Error getting rating: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get rating information"
        )