"""
UTC datetime utilities for consistent timezone handling across the application.

This module provides standardized UTC datetime operations to prevent timezone
consistency issues that can cause intermittent JWT expiration failures and
other time-related bugs.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional


def utcnow() -> datetime:
	"""
	Get current UTC datetime with timezone info.
	
	Replacement for datetime.utcnow() which returns timezone-naive datetime.
	This function always returns timezone-aware UTC datetime to prevent
	comparison issues between timezone-aware and timezone-naive datetimes.
	
	Returns:
		datetime: Current UTC time with timezone info
	"""
	return datetime.now(timezone.utc)


def utc_from_timestamp(timestamp: float) -> datetime:
	"""
	Convert Unix timestamp to timezone-aware UTC datetime.
	
	Args:
		timestamp: Unix timestamp (seconds since epoch)
		
	Returns:
		datetime: UTC datetime with timezone info
	"""
	return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def utc_plus_timedelta(delta: timedelta) -> datetime:
	"""
	Get UTC datetime plus a timedelta.
	
	Args:
		delta: Time difference to add
		
	Returns:
		datetime: UTC datetime plus delta with timezone info
	"""
	return utcnow() + delta


def utc_minus_timedelta(delta: timedelta) -> datetime:
	"""
	Get UTC datetime minus a timedelta.
	
	Args:
		delta: Time difference to subtract
		
	Returns:
		datetime: UTC datetime minus delta with timezone info
	"""
	return utcnow() - delta


def is_expired(expires_at: datetime, now: Optional[datetime] = None) -> bool:
	"""
	Check if a datetime has expired compared to current UTC time.
	
	Args:
		expires_at: Expiration datetime (should be timezone-aware)
		now: Current time for comparison (defaults to utcnow())
		
	Returns:
		bool: True if expired, False otherwise
	"""
	if now is None:
		now = utcnow()
	return expires_at <= now


def ensure_timezone_aware(dt: datetime) -> datetime:
	"""
	Ensure datetime is timezone-aware, assuming UTC if naive.
	
	Args:
		dt: Datetime that may or may not have timezone info
		
	Returns:
		datetime: Timezone-aware datetime
	"""
	if dt.tzinfo is None:
		return dt.replace(tzinfo=timezone.utc)
	return dt