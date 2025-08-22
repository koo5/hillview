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
    if not current_user_id:
        # No filtering for anonymous users
        return query
    
    # Filter out photos explicitly hidden by the user
    query = query.where(
        Photo.id.notin_(
            select(HiddenPhoto.photo_id).where(
                and_(
                    HiddenPhoto.user_id == current_user_id,
                    HiddenPhoto.photo_source == photo_source
                )
            )
        )
    )
    
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
    if not current_user_id:
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
    
    return hidden_photo_filter + hidden_user_filter


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