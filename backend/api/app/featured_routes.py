"""Featured photo routes – find a well-annotated photo nearest to the client's location.

Used on first visit to give new users an immediate 'aha moment' by navigating the map
to a nearby annotated panorama.
"""
import ipaddress
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import and_, cast, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from geoalchemy2 import Geography
from geoalchemy2.functions import ST_X, ST_Y, ST_Point

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import Photo, PhotoAnnotation
from rate_limiter import general_rate_limiter, get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/featured", tags=["featured"])

# Minimum annotation count (non-'?') for a photo to be considered well-annotated
MIN_ANNOTATION_COUNT = 20

# GeoIP reader (opened once, shared across requests). None if DB unavailable.
_geoip_reader = None
_geoip_db_path = os.getenv('GEOIP_DB_PATH', '/app/data/GeoLite2-City.mmdb')

try:
    import geoip2.database
    import geoip2.errors
    if os.path.exists(_geoip_db_path):
        _geoip_reader = geoip2.database.Reader(_geoip_db_path)
        logger.info(f"Featured: GeoIP database loaded from {_geoip_db_path}")
    else:
        logger.warning(f"Featured: GeoIP database not found at {_geoip_db_path}; featured photo will use global fallback")
except ImportError:
    logger.warning("Featured: geoip2 library not installed; featured photo will use global fallback")
except Exception as e:
    logger.warning(f"Featured: failed to open GeoIP database at {_geoip_db_path}: {e}")


def _annotated_count_subquery():
    """Count of current, non-deleted, non-'?' annotations per photo."""
    return (
        select(
            PhotoAnnotation.photo_id,
            func.count(PhotoAnnotation.id).label('annotation_count')
        )
        .where(
            and_(
                PhotoAnnotation.is_current == True,
                PhotoAnnotation.event_type != 'deleted',
                PhotoAnnotation.body != '?',
            )
        )
        .group_by(PhotoAnnotation.photo_id)
        .subquery('featured_annotations')
    )


def _geolocate_ip(ip: str) -> Optional[tuple[float, float]]:
    """Return (lat, lon) for an IP, or None if unknown/private/lookup-failed."""
    if not _geoip_reader:
        return None
    try:
        addr = ipaddress.ip_address(ip)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast:
            return None
    except ValueError:
        return None
    try:
        import geoip2.errors
        response = _geoip_reader.city(ip)
        if response.location.latitude is None or response.location.longitude is None:
            return None
        return (response.location.latitude, response.location.longitude)
    except geoip2.errors.AddressNotFoundError:
        return None
    except Exception as e:
        logger.debug(f"Featured: GeoIP lookup failed for {ip}: {e}")
        return None


async def _query_global_best(db: AsyncSession, annotation_sub) -> Optional[dict]:
    """Return the single photo with the most non-'?' annotations (global fallback)."""
    query = (
        select(
            Photo.id,
            Photo.description,
            Photo.compass_angle,
            ST_Y(Photo.geometry).label('latitude'),
            ST_X(Photo.geometry).label('longitude'),
            annotation_sub.c.annotation_count,
        )
        .join(annotation_sub, Photo.id == annotation_sub.c.photo_id)
        .where(
            and_(
                annotation_sub.c.annotation_count >= MIN_ANNOTATION_COUNT,
                Photo.deleted == False,
                Photo.is_public == True,
                Photo.processing_status == 'completed',
                Photo.geometry.isnot(None),
            )
        )
        .order_by(annotation_sub.c.annotation_count.desc(), Photo.id.desc())
        .limit(1)
    )
    result = await db.execute(query)
    row = result.first()
    if not row:
        return None
    return {
        "id": row.id,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "bearing": row.compass_angle,
        "description": row.description,
    }


async def _query_nearest(
    db: AsyncSession, annotation_sub, lat: float, lon: float
) -> Optional[dict]:
    """Return the nearest well-annotated photo to (lat, lon)."""
    # Same 3-arg ST_Point(x, y, srid) form used by photo_routes.py
    point = ST_Point(lon, lat, 4326)
    # Cast both to geography so ST_Distance returns real-world meters.
    distance = func.ST_Distance(
        cast(Photo.geometry, Geography),
        cast(point, Geography),
    )
    query = (
        select(
            Photo.id,
            Photo.description,
            Photo.compass_angle,
            ST_Y(Photo.geometry).label('latitude'),
            ST_X(Photo.geometry).label('longitude'),
            annotation_sub.c.annotation_count,
        )
        .join(annotation_sub, Photo.id == annotation_sub.c.photo_id)
        .where(
            and_(
                annotation_sub.c.annotation_count >= MIN_ANNOTATION_COUNT,
                Photo.deleted == False,
                Photo.is_public == True,
                Photo.processing_status == 'completed',
                Photo.geometry.isnot(None),
            )
        )
        .order_by(distance.asc())
        .limit(1)
    )
    result = await db.execute(query)
    row = result.first()
    if not row:
        return None
    return {
        "id": row.id,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "bearing": row.compass_angle,
        "description": row.description,
    }


@router.get("/nearest")
async def get_nearest_featured_photo(
    request: Request,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
):
    """Return the well-annotated photo nearest to the caller's location.

    If `lat` and `lon` are provided, use them directly (useful for testing).
    Otherwise geolocate from the request's real client IP. If geolocation is
    unavailable, fall back to the globally best-annotated photo.
    """
    await general_rate_limiter.enforce_rate_limit(request, 'public_read')

    annotation_sub = _annotated_count_subquery()

    try:
        coords: Optional[tuple[float, float]] = None
        if lat is not None and lon is not None:
            coords = (lat, lon)
        else:
            client_ip = get_client_ip(request)
            coords = _geolocate_ip(client_ip)

        photo = None
        if coords is not None:
            photo = await _query_nearest(db, annotation_sub, coords[0], coords[1])
        if photo is None:
            photo = await _query_global_best(db, annotation_sub)

        return {"photo": photo}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting featured photo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get featured photo",
        )
