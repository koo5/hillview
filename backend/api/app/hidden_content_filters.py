"""SQL filtering utilities for hidden content."""
from sqlalchemy import select, and_
from sqlalchemy.sql import Select
from typing import Optional

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.models import Photo, User, HiddenPhoto, HiddenUser


def apply_hidden_content_filters(
    query: Select, 
    current_user_id: Optional[str],
    photo_source: str = 'hillview'
) -> Select:
    """
    Apply hidden content filtering to a SQLAlchemy query that selects Photos.
    
    Args:
        query: SQLAlchemy Select query that includes Photo
        current_user_id: ID of the current user (None for anonymous users)
        photo_source: 'hillview' or 'mapillary' for source-specific filtering
    
    Returns:
        Modified query with hidden content filters applied
    """
    import logging
    log = logging.getLogger(__name__)
    
    log.info(f"apply_hidden_content_filters called: user_id={current_user_id}, photo_source={photo_source}")
    
    if not current_user_id:
        # No filtering for anonymous users
        log.info("No current_user_id, skipping filtering")
        return query
    
    # Filter out photos explicitly hidden by the user
    log.info(f"Applying photo filtering for user {current_user_id}, source {photo_source}")
    
    hidden_photo_subquery = select(HiddenPhoto.photo_id).where(
        and_(
            HiddenPhoto.user_id == current_user_id,
            HiddenPhoto.photo_source == photo_source
        )
    )
    log.info(f"Hidden photo subquery: {hidden_photo_subquery}")
    
    query = query.where(
        Photo.id.notin_(hidden_photo_subquery)
    )
    log.info(f"Applied photo filtering, modified query: {query}")
    
    # Filter out photos by hidden users (for Hillview photos, filter by owner_id)
    if photo_source == 'hillview':
        query = query.where(
            Photo.owner_id.notin_(
                select(HiddenUser.target_user_id).where(
                    and_(
                        HiddenUser.hiding_user_id == current_user_id,
                        HiddenUser.target_user_source == 'hillview'
                    )
                )
            )
        )
    
    return query


def apply_mapillary_hidden_content_filters(
    mapillary_photos: list,
    current_user_id: Optional[str]
) -> str:
    """
    Generate SQL WHERE conditions for Mapillary photo filtering.
    This returns SQL fragments that can be used in the cache service queries.
    
    Args:
        mapillary_photos: Not used, kept for API compatibility
        current_user_id: ID of the current user (None for anonymous users)
    
    Returns:
        SQL WHERE clause fragment as string
    """
    import logging
    log = logging.getLogger(__name__)
    
    log.info(f"apply_mapillary_hidden_content_filters called with user_id: {current_user_id}")
    
    if not current_user_id:
        log.info("No user_id provided, skipping SQL-based filtering")
        return ""
    
    # Generate SQL fragments for hidden photo and user filtering
    hidden_photo_filter = f"""
        AND p.mapillary_id NOT IN (
            SELECT photo_id FROM hidden_photos 
            WHERE user_id = '{current_user_id}' 
            AND photo_source = 'mapillary'
        )
    """
    
    hidden_user_filter = f"""
        AND (p.creator_id IS NULL OR p.creator_id NOT IN (
            SELECT target_user_id FROM hidden_users 
            WHERE hiding_user_id = '{current_user_id}' 
            AND target_user_source = 'mapillary'
        ))
    """
    
    filters = hidden_photo_filter + hidden_user_filter
    log.info(f"Generated SQL filters for user {current_user_id}: {filters}")
    return filters


def get_hidden_photo_subquery(current_user_id: str, photo_source: str):
    """
    Get a subquery for hidden photos that can be reused in different contexts.
    
    Args:
        current_user_id: ID of the current user
        photo_source: 'hillview' or 'mapillary'
    
    Returns:
        SQLAlchemy subquery for hidden photo IDs
    """
    return select(HiddenPhoto.photo_id).where(
        and_(
            HiddenPhoto.user_id == current_user_id,
            HiddenPhoto.photo_source == photo_source
        )
    )


def get_hidden_user_subquery(current_user_id: str, user_source: str):
    """
    Get a subquery for hidden users that can be reused in different contexts.
    
    Args:
        current_user_id: ID of the current user
        user_source: 'hillview' or 'mapillary'
    
    Returns:
        SQLAlchemy subquery for hidden user IDs
    """
    return select(HiddenUser.target_user_id).where(
        and_(
            HiddenUser.hiding_user_id == current_user_id,
            HiddenUser.target_user_source == user_source
        )
    )


async def filter_mapillary_photos_list(
    photos: list, 
    current_user_id: Optional[str],
    db: "AsyncSession"
) -> list:
    """
    Filter a list of Mapillary photos to remove hidden content.
    
    Args:
        photos: List of Mapillary photo data dictionaries
        current_user_id: ID of the current user (None for anonymous users)
        db: Database session for querying hidden content
    
    Returns:
        Filtered list of photos with hidden content removed
    """
    import logging
    log = logging.getLogger(__name__)
    
    log.info(f"filter_mapillary_photos_list called with {len(photos)} photos, user_id: {current_user_id}")
    
    if not current_user_id or not photos:
        log.info(f"Skipping filtering: current_user_id={current_user_id}, photos_count={len(photos) if photos else 0}")
        return photos
    
    # Get photo IDs from the list
    photo_ids = [photo.get('id') for photo in photos if photo.get('id')]
    if not photo_ids:
        return photos
    
    # Query hidden photo IDs for this user
    hidden_photo_query = select(HiddenPhoto.photo_id).where(
        and_(
            HiddenPhoto.user_id == current_user_id,
            HiddenPhoto.photo_source == 'mapillary',
            HiddenPhoto.photo_id.in_(photo_ids)
        )
    )
    log.info(f"Querying hidden photos for user {current_user_id} with {len(photo_ids)} photo IDs")
    result = await db.execute(hidden_photo_query)
    hidden_photo_ids = set(row[0] for row in result.fetchall())
    log.info(f"Found {len(hidden_photo_ids)} hidden photos: {hidden_photo_ids}")
    
    # Get creator IDs from the photos
    creator_ids = [photo.get('creator', {}).get('id') for photo in photos 
                   if photo.get('creator', {}).get('id')]
    hidden_creator_ids = set()
    
    if creator_ids:
        # Query hidden user IDs for this user
        hidden_user_query = select(HiddenUser.target_user_id).where(
            and_(
                HiddenUser.hiding_user_id == current_user_id,
                HiddenUser.target_user_source == 'mapillary',
                HiddenUser.target_user_id.in_(creator_ids)
            )
        )
        log.info(f"Querying hidden users for user {current_user_id} with {len(creator_ids)} creator IDs")
        result = await db.execute(hidden_user_query)
        hidden_creator_ids = set(row[0] for row in result.fetchall())
        log.info(f"Found {len(hidden_creator_ids)} hidden creators: {hidden_creator_ids}")
    else:
        log.info("No creator IDs found in photos")
    
    # Filter photos
    filtered_photos = []
    filtered_count = 0
    for photo in photos:
        photo_id = photo.get('id')
        creator_id = photo.get('creator', {}).get('id')
        
        # Skip if photo is hidden
        if photo_id in hidden_photo_ids:
            log.info(f"Filtering out hidden photo: {photo_id}")
            filtered_count += 1
            continue
            
        # Skip if creator is hidden
        if creator_id in hidden_creator_ids:
            log.info(f"Filtering out photo from hidden creator: {photo_id} (creator: {creator_id})")
            filtered_count += 1
            continue
            
        filtered_photos.append(photo)
    
    log.info(f"Filtering complete: {len(filtered_photos)} photos remaining, {filtered_count} filtered out")
    return filtered_photos