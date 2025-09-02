"""FastAPI-specific security utilities that wrap common security functions."""
from typing import Optional, Set, Tuple
from fastapi import HTTPException, status
import logging

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.security_utils import (
	SecurityValidationError,
	sanitize_filename as _sanitize_filename,
	validate_file_path as _validate_file_path,
	validate_file_upload_basic as _validate_file_upload_basic,
	validate_username_basic as _validate_username_basic,
	validate_email_basic as _validate_email_basic,
	validate_password_basic as _validate_password_basic,
	validate_oauth_redirect_uri_basic as _validate_oauth_redirect_uri_basic,
	generate_secure_filename as _generate_secure_filename,
	check_file_content as _check_file_content,
	ALLOWED_IMAGE_EXTENSIONS,
	ALLOWED_MIME_TYPES,
	MAX_FILE_SIZE,
	MAX_FILENAME_LENGTH
)

logger = logging.getLogger(__name__)

# Re-export constants
__all__ = [
	'ALLOWED_IMAGE_EXTENSIONS', 'ALLOWED_MIME_TYPES', 'MAX_FILE_SIZE', 'MAX_FILENAME_LENGTH',
	'sanitize_filename', 'validate_file_path', 'validate_file_upload', 'validate_username',
	'validate_email', 'validate_password', 'validate_oauth_redirect_uri', 'generate_secure_filename', 
	'check_file_content'
]

def _convert_security_error(func, *args, **kwargs):
	"""Convert SecurityValidationError to HTTPException."""
	try:
		return func(*args, **kwargs)
	except SecurityValidationError as e:
		if "File too large" in str(e):
			raise HTTPException(
				status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
				detail=str(e)
			)
		else:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=str(e)
			)

def sanitize_filename(filename: str) -> str:
	"""Sanitize a filename to prevent path traversal and other attacks."""
	return _sanitize_filename(filename)

def validate_file_path(file_path: str, base_directory: str) -> str:
	"""Validate that a file path is within the allowed base directory."""
	return _convert_security_error(_validate_file_path, file_path, base_directory)

def validate_file_upload(
	filename: str,
	file_size: int,
	content_type: Optional[str] = None,
	allowed_extensions: Set[str] = ALLOWED_IMAGE_EXTENSIONS
) -> Tuple[str, str]:
	"""Validate an uploaded file for security issues."""
	return _convert_security_error(_validate_file_upload_basic, filename, file_size, content_type, allowed_extensions)

def validate_username(username: str) -> str:
	"""Validate username format."""
	return _convert_security_error(_validate_username_basic, username)

def validate_email(email: str) -> str:
	"""Validate email format."""
	return _convert_security_error(_validate_email_basic, email)

def validate_password(password: str) -> str:
	"""Validate password strength."""
	return _convert_security_error(_validate_password_basic, password)

def validate_oauth_redirect_uri(uri: str, allowed_domains: Optional[Set[str]] = None) -> str:
	"""Validate OAuth redirect URI to prevent open redirect attacks."""
	return _convert_security_error(_validate_oauth_redirect_uri_basic, uri, allowed_domains)

def generate_secure_filename(original_filename: str, user_id: str) -> str:
	"""Generate a secure filename with user ID and timestamp."""
	return _generate_secure_filename(original_filename, user_id)

def check_file_content(file_path: str, expected_type: str = "image") -> bool:
	"""Check file content matches expected type using file headers."""
	return _check_file_content(file_path, expected_type)