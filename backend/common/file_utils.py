"""
Common file handling utilities for photo processing.
Non-database file operations shared between API and worker services.
"""

import os
import logging
from pathlib import Path
from typing import Tuple

from .security_utils import (
    validate_file_upload_basic,
    sanitize_filename,
    generate_secure_filename,
    validate_file_path,
    check_file_content,
    SecurityValidationError
)

logger = logging.getLogger(__name__)

def validate_and_prepare_photo_file(
    filename: str, 
    file_size: int, 
    content_type: str,
    user_id: str,
    upload_base_dir: str = "./uploads"
) -> Tuple[str, str, Path]:
    """
    Validate uploaded file and prepare secure file path.
    
    Returns:
        - safe_filename: Sanitized original filename
        - secure_filename: Secure filename for storage
        - file_path: Full path where file should be saved
    
    Raises:
        SecurityValidationError: If validation fails
    """
    # Validate file upload
    safe_filename, ext = validate_file_upload_basic(
        filename=filename,
        file_size=file_size,
        content_type=content_type
    )
    
    # Generate secure filename with user ID
    secure_filename = generate_secure_filename(safe_filename, user_id)
    
    # Create user-specific upload directory
    upload_dir = Path(upload_base_dir)
    user_upload_dir = upload_dir / user_id
    user_upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Full file path
    file_path = user_upload_dir / secure_filename
    
    return safe_filename, secure_filename, file_path

def verify_saved_file_content(file_path: str, expected_type: str = "image") -> bool:
    """
    Verify that saved file content matches expected type.
    
    Returns:
        bool: True if content is valid, False otherwise
    """
    try:
        return check_file_content(file_path, expected_type)
    except Exception as e:
        logger.error(f"Error verifying file content {file_path}: {str(e)}")
        return False

def cleanup_file_on_error(file_path: Path):
    """
    Clean up a file if processing fails.
    Safe to call even if file doesn't exist.
    """
    try:
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Cleaned up file: {file_path}")
    except Exception as e:
        logger.warning(f"Failed to cleanup file {file_path}: {str(e)}")

def get_file_size_from_upload(file_handle) -> int:
    """
    Get file size from upload file handle.
    Resets file position to beginning after reading.
    """
    file_handle.seek(0, 2)  # Seek to end
    file_size = file_handle.tell()
    file_handle.seek(0)  # Reset to beginning
    return file_size