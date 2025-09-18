"""Unit tests for security utilities."""

import pytest
import sys
import os

# Add common directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from common.security_utils import (
    validate_user_id,
    validate_photo_id,
    validate_filesystem_safe_id,
    SecurityValidationError
)


class TestFilesystemSafeIDValidation:
    """Test filesystem-safe ID validation functions."""

    def test_valid_uuid_format(self):
        """Test valid UUID format IDs."""
        valid_uuid = "123e4567-e89b-12d3-a456-426614174000"
        assert validate_user_id(valid_uuid) == valid_uuid
        assert validate_photo_id(valid_uuid) == valid_uuid

    def test_valid_alphanumeric_with_dashes(self):
        """Test valid alphanumeric IDs with dashes."""
        valid_ids = [
            "abc123-def456-789",
            "user-12345",
            "photo-id-123",
            "abcDEF123",
            "a",
            "a" * 100  # Maximum length
        ]

        for test_id in valid_ids:
            assert validate_user_id(test_id) == test_id
            assert validate_photo_id(test_id) == test_id

    def test_whitespace_trimming(self):
        """Test that whitespace is properly trimmed."""
        test_id = "  abc123-def  "
        expected = "abc123-def"
        assert validate_user_id(test_id) == expected
        assert validate_photo_id(test_id) == expected

    def test_path_traversal_rejection(self):
        """Test that path traversal attempts are rejected."""
        dangerous_paths = [
            "../../../etc/passwd",
            "../../secret",
            "../",
            "..",
            "user/../admin"
        ]

        for dangerous_path in dangerous_paths:
            with pytest.raises(SecurityValidationError, match="must contain only alphanumerics and dashes"):
                validate_user_id(dangerous_path)

    def test_filesystem_dangerous_characters(self):
        """Test that filesystem-dangerous characters are rejected."""
        dangerous_chars = [
            "user/id",      # Forward slash
            "user\\id",     # Backslash
            "user id",      # Space
            "user@id",      # Special character
            "user.id",      # Dot
            "user:id",      # Colon
            "user*id",      # Asterisk
            "user?id",      # Question mark
            "user<id",      # Less than
            "user>id",      # Greater than
            "user|id",      # Pipe
            "user\"id",     # Quote
        ]

        for dangerous_id in dangerous_chars:
            with pytest.raises(SecurityValidationError, match="must contain only alphanumerics and dashes"):
                validate_user_id(dangerous_id)

    def test_empty_and_whitespace_only(self):
        """Test that empty and whitespace-only IDs are rejected."""
        empty_ids = ["", "   ", "\t", "\n", "  \t  \n  "]

        for empty_id in empty_ids:
            with pytest.raises(SecurityValidationError, match="cannot be empty"):
                validate_user_id(empty_id)

    def test_length_limits(self):
        """Test length validation."""
        # Too long (over 100 characters)
        too_long = "a" * 101
        with pytest.raises(SecurityValidationError, match="length must be between 1 and 100 characters"):
            validate_user_id(too_long)

        # Exactly at limit should pass
        max_length = "a" * 100
        assert validate_user_id(max_length) == max_length

    def test_control_characters(self):
        """Test that control characters are rejected."""
        control_chars = [
            "user\x00id",    # Null byte
            "user\nid",      # Newline
            "user\rid",      # Carriage return
            "user\tid",      # Tab
            "user\x1fid",    # Unit separator
        ]

        for control_id in control_chars:
            with pytest.raises(SecurityValidationError, match="must contain only alphanumerics and dashes"):
                validate_user_id(control_id)

    def test_injection_attempts(self):
        """Test that common injection attempts are rejected."""
        injection_attempts = [
            "user;rm -rf /",
            "user && cat /etc/passwd",
            "user`whoami`",
            "user$(id)",
            "user'; DROP TABLE users; --",
        ]

        for injection in injection_attempts:
            with pytest.raises(SecurityValidationError, match="must contain only alphanumerics and dashes"):
                validate_user_id(injection)

    def test_non_string_input(self):
        """Test that non-string inputs are rejected."""
        non_strings = [123, None, [], {}, True]

        for non_string in non_strings:
            with pytest.raises(SecurityValidationError, match="must be a string"):
                validate_user_id(non_string)

    def test_generic_filesystem_safe_id_function(self):
        """Test the generic filesystem safe ID validation function."""
        valid_id = "test-id-123"
        assert validate_filesystem_safe_id(valid_id, "test_field") == valid_id

        with pytest.raises(SecurityValidationError, match="Invalid test_field"):
            validate_filesystem_safe_id("invalid/id", "test_field")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])