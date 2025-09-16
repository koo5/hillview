#!/usr/bin/env python3
"""Test script for user_id and photo_id sanitization functions."""

import sys
import os
sys.path.append('common')

from common.security_utils import validate_user_id, validate_photo_id, SecurityValidationError

def test_valid_ids():
    """Test valid filesystem-safe IDs."""
    valid_ids = [
        "123e4567-e89b-12d3-a456-426614174000",  # Standard UUID
        "abc123-def456-789",                      # Alphanumeric with dashes
        "user-12345",                             # Simple format
        "photo-id-123",                           # Multi-dash format
        "abcDEF123"                              # Mixed case
    ]

    print("Testing valid IDs:")
    for test_id in valid_ids:
        try:
            sanitized_user_id = validate_user_id(test_id)
            sanitized_photo_id = validate_photo_id(test_id)
            print(f"  ✓ '{test_id}' -> user_id: '{sanitized_user_id}', photo_id: '{sanitized_photo_id}'")
        except SecurityValidationError as e:
            print(f"  ✗ '{test_id}' failed: {e}")

def test_invalid_ids():
    """Test invalid/unsafe IDs."""
    invalid_ids = [
        "../../../etc/passwd",     # Path traversal
        "user/id",                 # Forward slash
        "user\\id",                # Backslash
        "user id",                 # Space
        "user@id",                 # Special character
        "user.id",                 # Dot
        "",                        # Empty
        "   ",                     # Whitespace only
        "a" * 101,                 # Too long
        "user\x00id",              # Null byte
        "user\nid",                # Newline
        "user;rm -rf /",           # Command injection attempt
    ]

    print("\nTesting invalid IDs (should all fail):")
    for test_id in invalid_ids:
        try:
            sanitized = validate_user_id(test_id)
            print(f"  ✗ '{test_id}' incorrectly passed: '{sanitized}'")
        except SecurityValidationError as e:
            print(f"  ✓ '{test_id}' correctly rejected: {e}")

def test_edge_cases():
    """Test edge cases."""
    edge_cases = [
        "  abc123-def  ",          # Whitespace trimming
        "a",                       # Minimum length
        "a" * 100,                 # Maximum length
    ]

    print("\nTesting edge cases:")
    for test_id in edge_cases:
        try:
            sanitized = validate_user_id(test_id)
            print(f"  ✓ '{test_id}' -> '{sanitized}'")
        except SecurityValidationError as e:
            print(f"  ✗ '{test_id}' failed: {e}")

if __name__ == "__main__":
    print("Testing user_id and photo_id sanitization functions...\n")
    test_valid_ids()
    test_invalid_ids()
    test_edge_cases()
    print("\nTest completed.")