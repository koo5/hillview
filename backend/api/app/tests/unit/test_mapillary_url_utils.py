"""Tests for mapillary_url_utils module."""

import pytest
from datetime import datetime, timezone, timedelta
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from mapillary_url_utils import parse_url_expiry, is_url_expired, check_photo_url_expiry


class TestParseUrlExpiry:
    """Tests for parse_url_expiry function."""

    def test_parse_valid_url_with_oe_param(self):
        """Test parsing a URL with valid oe parameter."""
        # oe=67890ABC is hex for 1737003708 which is 2025-01-16 02:48:28 UTC
        url = "https://scontent.example.com/v/t51.12345?oe=67890ABC&other=param"
        expiry = parse_url_expiry(url)

        assert expiry is not None
        assert expiry.tzinfo == timezone.utc
        # Verify the timestamp decodes correctly
        assert expiry == datetime.fromtimestamp(0x67890ABC, tz=timezone.utc)

    def test_parse_url_without_oe_param(self):
        """Test parsing a URL without oe parameter."""
        url = "https://scontent.example.com/v/t51.12345?other=param"
        expiry = parse_url_expiry(url)

        assert expiry is None

    def test_parse_empty_url(self):
        """Test parsing empty URL."""
        assert parse_url_expiry("") is None
        assert parse_url_expiry(None) is None

    def test_parse_url_with_invalid_oe(self):
        """Test parsing URL with non-hex oe value."""
        url = "https://scontent.example.com/v/t51.12345?oe=notahex"
        expiry = parse_url_expiry(url)

        # Should return None on parse failure
        assert expiry is None


class TestIsUrlExpired:
    """Tests for is_url_expired function."""

    def test_expired_url(self):
        """Test detecting an expired URL."""
        # Use a timestamp in the past
        past_timestamp = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp())
        oe_hex = hex(past_timestamp)[2:]  # Remove '0x' prefix
        url = f"https://scontent.example.com/v/t51.12345?oe={oe_hex}"

        is_expired, expiry = is_url_expired(url)

        assert is_expired is True
        assert expiry is not None

    def test_valid_url(self):
        """Test detecting a non-expired URL."""
        # Use a timestamp in the future
        future_timestamp = int((datetime.now(timezone.utc) + timedelta(days=1)).timestamp())
        oe_hex = hex(future_timestamp)[2:]  # Remove '0x' prefix
        url = f"https://scontent.example.com/v/t51.12345?oe={oe_hex}"

        is_expired, expiry = is_url_expired(url)

        assert is_expired is False
        assert expiry is not None

    def test_url_without_expiry(self):
        """Test URL without expiry parameter."""
        url = "https://scontent.example.com/v/t51.12345"

        is_expired, expiry = is_url_expired(url)

        # Can't determine, assume not expired
        assert is_expired is False
        assert expiry is None

    def test_custom_now_parameter(self):
        """Test with custom 'now' parameter."""
        # Fixed timestamp: 2025-01-15 12:00:00 UTC (hex: 67881980)
        url = "https://scontent.example.com/v/t51.12345?oe=67881980"

        # Test with a time before expiry
        before_expiry = datetime(2025, 1, 14, 12, 0, 0, tzinfo=timezone.utc)
        is_expired, _ = is_url_expired(url, now=before_expiry)
        assert is_expired is False

        # Test with a time after expiry
        after_expiry = datetime(2025, 1, 16, 12, 0, 0, tzinfo=timezone.utc)
        is_expired, _ = is_url_expired(url, now=after_expiry)
        assert is_expired is True


class TestCheckPhotoUrlExpiry:
    """Tests for check_photo_url_expiry function."""

    def test_expired_photo_returns_info(self):
        """Test that expired photo returns expiry info."""
        past_timestamp = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
        oe_hex = hex(past_timestamp)[2:]

        photo = {
            'id': 'test_photo_123',
            'thumb_1024_url': f"https://scontent.example.com/v/t51?oe={oe_hex}"
        }

        result = check_photo_url_expiry(photo)

        assert result is not None
        assert result['photo_id'] == 'test_photo_123'
        assert 'expiry' in result
        assert 'url' in result

    def test_valid_photo_returns_none(self):
        """Test that non-expired photo returns None."""
        future_timestamp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
        oe_hex = hex(future_timestamp)[2:]

        photo = {
            'id': 'test_photo_456',
            'thumb_1024_url': f"https://scontent.example.com/v/t51?oe={oe_hex}"
        }

        result = check_photo_url_expiry(photo)

        assert result is None

    def test_photo_without_url_returns_none(self):
        """Test photo without thumb_1024_url returns None."""
        photo = {'id': 'test_photo_789'}

        result = check_photo_url_expiry(photo)

        assert result is None

    def test_long_url_is_truncated(self):
        """Test that very long URLs are truncated in the result."""
        past_timestamp = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
        oe_hex = hex(past_timestamp)[2:]

        long_url = f"https://scontent.example.com/{'x' * 200}?oe={oe_hex}"
        photo = {
            'id': 'test_photo',
            'thumb_1024_url': long_url
        }

        result = check_photo_url_expiry(photo)

        assert result is not None
        assert len(result['url']) <= 103  # 100 + '...'
        assert result['url'].endswith('...')
