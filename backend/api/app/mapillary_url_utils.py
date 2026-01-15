"""Utilities for parsing and validating Mapillary photo URLs."""

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs

log = logging.getLogger(__name__)


def parse_url_expiry(url: str) -> Optional[datetime]:
    """
    Parse the expiry timestamp from a Mapillary photo URL.

    The 'oe' parameter in Mapillary URLs is a hex-encoded Unix timestamp
    indicating when the URL expires.

    Args:
        url: The Mapillary photo URL (e.g., thumb_1024_url)

    Returns:
        datetime object representing expiry time, or None if parsing fails
    """
    if not url:
        return None

    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)

        oe_values = query_params.get('oe')
        if not oe_values:
            return None

        oe_hex = oe_values[0]
        # The 'oe' parameter is a hex-encoded Unix timestamp
        expiry_timestamp = int(oe_hex, 16)
        expiry_dt = datetime.fromtimestamp(expiry_timestamp, tz=timezone.utc)

        return expiry_dt

    except (ValueError, TypeError) as e:
        log.debug(f"Failed to parse expiry from URL: {e}")
        return None


def is_url_expired(url: str, now: Optional[datetime] = None) -> Tuple[bool, Optional[datetime]]:
    """
    Check if a Mapillary photo URL has expired.

    Args:
        url: The Mapillary photo URL
        now: Optional datetime to compare against (defaults to current UTC time)

    Returns:
        Tuple of (is_expired: bool, expiry_datetime: Optional[datetime])
    """
    expiry = parse_url_expiry(url)
    if expiry is None:
        return (False, None)  # Can't determine, assume not expired

    if now is None:
        now = datetime.now(timezone.utc)

    return (now > expiry, expiry)


def check_photo_url_expiry(photo: dict, now: Optional[datetime] = None) -> Optional[dict]:
    """
    Check a photo dict for URL expiry and return expiry info if applicable.

    Args:
        photo: Photo dict with 'thumb_1024_url' or similar URL fields
        now: Optional datetime to compare against

    Returns:
        Dict with expiry info if expired, None otherwise
    """
    url = photo.get('thumb_1024_url')
    if not url:
        return None

    is_expired, expiry_dt = is_url_expired(url, now)

    if is_expired and expiry_dt:
        return {
            'photo_id': photo.get('id'),
            'expiry': expiry_dt.isoformat(),
            'url': url[:100] + '...' if len(url) > 100 else url  # Truncate for logging
        }

    return None
