"""Shared security utilities for file handling and input validation (no FastAPI dependencies)."""
import os
import re
import hashlib
import mimetypes
from pathlib import Path
from typing import Optional, Set, Tuple
import logging

logger = logging.getLogger(__name__)

# Allowed file extensions for uploads
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'}
ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp', 'image/tiff'}

# Maximum file sizes (in bytes)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_FILENAME_LENGTH = 255

# Regex patterns for validation
SAFE_FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.]+$')
USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]{3,30}$')
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

class SecurityValidationError(Exception):
    """Exception raised when security validation fails."""
    pass

def sanitize_filename(filename: str) -> str:
    """Sanitize a filename to prevent path traversal and other attacks."""
    if not filename:
        raise ValueError("Filename cannot be empty")
    
    # Remove any path components
    filename = os.path.basename(filename)
    
    # Remove any leading dots
    while filename.startswith('.'):
        filename = filename[1:]
    
    # Replace dangerous characters
    filename = re.sub(r'[^\w\s\-\.]', '_', filename)
    
    # Remove multiple dots to prevent extension confusion
    filename = re.sub(r'\.+', '.', filename)
    
    # Limit filename length
    if len(filename) > MAX_FILENAME_LENGTH:
        name, ext = os.path.splitext(filename)
        max_name_length = MAX_FILENAME_LENGTH - len(ext)
        filename = name[:max_name_length] + ext
    
    # Ensure filename is not empty after sanitization
    if not filename or filename == '.':
        filename = 'unnamed_file'
    
    return filename

def validate_file_path(file_path: str, base_directory: str) -> str:
    """Validate that a file path is within the allowed base directory."""
    # Convert to absolute paths
    base_path = Path(base_directory).resolve()
    requested_path = Path(file_path).resolve()
    
    # Check if the requested path is within the base directory
    try:
        requested_path.relative_to(base_path)
    except ValueError:
        logger.warning(f"Path traversal attempt detected: {file_path}")
        raise SecurityValidationError("Invalid file path - path traversal detected")
    
    # Additional checks for suspicious patterns
    path_str = str(requested_path)
    if '..' in path_str or '~' in path_str:
        logger.warning(f"Suspicious path pattern detected: {file_path}")
        raise SecurityValidationError("Invalid file path - suspicious pattern detected")
    
    return str(requested_path)

def validate_file_upload_basic(
    filename: str,
    file_size: int,
    content_type: Optional[str] = None,
    allowed_extensions: Set[str] = ALLOWED_IMAGE_EXTENSIONS
) -> Tuple[str, str]:
    """Validate an uploaded file for basic security issues (no FastAPI dependencies)."""
    # Sanitize filename
    safe_filename = sanitize_filename(filename)
    
    # Check file extension
    _, ext = os.path.splitext(safe_filename.lower())
    if ext not in allowed_extensions:
        raise SecurityValidationError(f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}")
    
    # Check file size
    if file_size > MAX_FILE_SIZE:
        raise SecurityValidationError(f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB")
    
    # Validate MIME type if provided
    if content_type:
        if content_type not in ALLOWED_MIME_TYPES:
            raise SecurityValidationError(f"Invalid content type: {content_type}")
        
        # Check MIME type matches extension
        expected_mime = mimetypes.guess_type(safe_filename)[0]
        if expected_mime and content_type != expected_mime:
            logger.warning(f"MIME type mismatch: {content_type} vs {expected_mime} for {safe_filename}")
    
    return safe_filename, ext

def validate_username_basic(username: str) -> str:
    """Validate username format (no FastAPI dependencies)."""
    if not username or not USERNAME_PATTERN.match(username):
        raise SecurityValidationError("Invalid username. Use 3-30 alphanumeric characters, hyphens, or underscores.")
    return username

def validate_email_basic(email: str) -> str:
    """Validate email format (no FastAPI dependencies)."""
    if not email or not EMAIL_PATTERN.match(email.lower()):
        raise SecurityValidationError("Invalid email address format")
    return email.lower()

def validate_oauth_redirect_uri_basic(uri: str, allowed_domains: Optional[Set[str]] = None) -> str:
    """Validate OAuth redirect URI to prevent open redirect attacks (no FastAPI dependencies)."""
    if not uri:
        raise SecurityValidationError("Redirect URI is required")
    
    # Check for common bypass attempts
    if any(pattern in uri.lower() for pattern in ['@', '//', '\\', '%0d', '%0a', '\r', '\n']):
        logger.warning(f"Suspicious redirect URI pattern: {uri}")
        raise SecurityValidationError("Invalid redirect URI")
    
    # If allowed domains are specified, validate against them
    if allowed_domains:
        from urllib.parse import urlparse
        parsed = urlparse(uri)
        if parsed.netloc and parsed.netloc not in allowed_domains:
            logger.warning(f"Redirect URI domain not allowed: {parsed.netloc}")
            raise SecurityValidationError("Redirect URI domain not allowed")
    
    return uri

def generate_secure_filename(original_filename: str, user_id: str) -> str:
    """Generate a secure filename with user ID and timestamp."""
    import time
    
    # Sanitize original filename
    safe_name = sanitize_filename(original_filename)
    name, ext = os.path.splitext(safe_name)
    
    # Generate unique filename with user ID and timestamp
    timestamp = int(time.time() * 1000)
    hash_input = f"{user_id}_{timestamp}_{name}".encode()
    file_hash = hashlib.sha256(hash_input).hexdigest()[:8]
    
    return f"{user_id}_{timestamp}_{file_hash}{ext}"

def check_file_content(file_path: str, expected_type: str = "image") -> bool:
    """Check file content matches expected type using file headers."""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(32)
        
        if expected_type == "image":
            # Check for common image file signatures
            image_signatures = [
                (b'\xff\xd8\xff', 'jpeg'),  # JPEG
                (b'\x89PNG\r\n\x1a\n', 'png'),  # PNG
                (b'GIF87a', 'gif'),  # GIF87a
                (b'GIF89a', 'gif'),  # GIF89a
                (b'RIFF', 'webp'),  # WebP (needs additional check)
                (b'BM', 'bmp'),  # BMP
                (b'II*\x00', 'tiff'),  # TIFF (little-endian)
                (b'MM\x00*', 'tiff'),  # TIFF (big-endian)
            ]
            
            for signature, file_type in image_signatures:
                if header.startswith(signature):
                    # Additional check for WebP
                    if file_type == 'webp' and header[8:12] != b'WEBP':
                        continue
                    return True
            
            logger.warning(f"File {file_path} does not match any known image signature")
            return False
        
        return True  # For other file types, return True for now
        
    except Exception as e:
        logger.error(f"Error checking file content: {str(e)}")
        return False