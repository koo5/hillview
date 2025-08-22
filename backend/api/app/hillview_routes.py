import json
import os
from typing import Optional, Dict, Any
import logging
from fastapi import APIRouter, Query, HTTPException, status, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from dotenv import load_dotenv

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import Photo, User
from .hidden_content_filters import apply_hidden_content_filters
from .auth import get_current_user_optional_with_query
from .rate_limiter import rate_limit_public_read

load_dotenv()
log = logging.getLogger(__name__)

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
    # Apply public read rate limiting
    await rate_limit_public_read(request)
    
    try:
        # Query photos from database that fall within the bounding box
        # Join with User table to check if photo owner is a test user
        query = select(Photo).join(User, Photo.owner_id == User.id).where(
            Photo.latitude.isnot(None),
            Photo.longitude.isnot(None),
            Photo.latitude >= bottom_right_lat,
            Photo.latitude <= top_left_lat,
            Photo.longitude >= top_left_lon,
            Photo.longitude <= bottom_right_lon,
            Photo.is_public == True
        )
        
        # Apply hidden content filtering
        query = apply_hidden_content_filters(
            query, 
            current_user.id if current_user else None,
            'hillview'
        )
        
        # Filter out test user photos if user is not authenticated
        if current_user is None:
            query = query.where(User.is_test == False)
            log.info("Filtering out test user photos for anonymous user")
        else:
            log.info(f"Authenticated user {current_user.username} requesting photos (including test user photos)")
        
        result = await db.execute(query)
        photos = result.scalars().all()
        
        # Transform photos to match Mapillary-like structure
        filtered_photos = []
        
        for photo in photos:
            photo_data = {
                'id': photo.id,
                'geometry': {
                    'coordinates': [photo.longitude, photo.latitude]
                },
                'compass_angle': photo.compass_angle or 0,
                'computed_rotation': 0,
                'computed_compass_angle': photo.compass_angle or 0,
                'computed_altitude': photo.altitude or 0,
                'captured_at': photo.captured_at.isoformat() if photo.captured_at else '',
                'is_pano': False,
                'filename': photo.filename,
                'filepath': photo.filepath,
                'dir_name': os.path.dirname(photo.filepath) if photo.filepath else '',
                'sizes': photo.sizes or {}
            }
            filtered_photos.append(photo_data)
        
        # Sort by compass angle like Mapillary endpoint
        filtered_photos.sort(key=lambda x: x.get('compass_angle', 0))
        
        log.info(f"Found {len(filtered_photos)} photos in database for bbox")
        
        return {
            'data': filtered_photos,
            'total_count': len(filtered_photos),
            'bbox': {
                'top_left_lat': top_left_lat,
                'top_left_lon': top_left_lon,
                'bottom_right_lat': bottom_right_lat,
                'bottom_right_lon': bottom_right_lon
            }
        }
        
    except Exception as e:
        log.error(f"Error querying photos from database: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )