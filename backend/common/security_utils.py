"""Shared security utilities for file handling and input validation (no FastAPI dependencies)."""
import os
import re
import hashlib
import mimetypes
import json
import base64
from pathlib import Path
from typing import Optional, Set, Tuple, Dict, Any
import logging
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

try:
	from password_strength import PasswordPolicy
	_PASSWORD_STRENGTH_AVAILABLE = True
except ImportError:
	_PASSWORD_STRENGTH_AVAILABLE = False

logger = logging.getLogger(__name__)

# Allowed file extensions for uploads
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'}
ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp', 'image/tiff'}

# Maximum file sizes (in bytes)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_FILENAME_LENGTH = 255

# Image processing limits
MAX_IMAGE_DIMENSIONS = (32192, 32192)  # Max width, height
MAX_IMAGE_PIXELS = 167108864

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
		filename = 'unknown'

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

	# Check for common bypass attempts (but allow // in http://)
	suspicious_patterns = ['@', '\\', '%0d', '%0a', '\r', '\n']
	# Check for double slash outside of protocol (http:// is valid)
	if '//' in uri and not uri.lower().startswith(('http://', 'https://')):
		suspicious_patterns.append('//')

	if any(pattern in uri.lower() for pattern in suspicious_patterns):
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

def verify_model_file(model_path: str, expected_hash: Optional[str] = None) -> bool:
	"""Verify ML model file integrity and existence."""
	try:
		# Check if file exists and is readable
		if not os.path.exists(model_path):
			logger.warning(f"Model file not found: {model_path}")
			return False

		# Validate path is within expected directory
		try:
			validate_file_path(model_path, "/app")
		except SecurityValidationError as e:
			logger.error(f"Model path validation failed: {e}")
			return False

		# Check file size (basic sanity check - models shouldn't be too small)
		file_size = os.path.getsize(model_path)
		if file_size < 1024:  # Less than 1KB is suspicious for ML model
			logger.warning(f"Model file suspiciously small: {file_size} bytes")
			return False

		# If hash provided, verify integrity
		if expected_hash:
			with open(model_path, 'rb') as f:
				file_hash = hashlib.sha256(f.read()).hexdigest()
			if file_hash != expected_hash:
				logger.error(f"Model hash mismatch. Expected: {expected_hash}, Got: {file_hash}")
				return False

		return True

	except Exception as e:
		logger.error(f"Error verifying model file: {str(e)}")
		return False

def validate_image_dimensions(width: int, height: int) -> bool:
	"""Validate image dimensions to prevent resource exhaustion attacks."""
	try:
		# Check individual dimension limits
		if width > MAX_IMAGE_DIMENSIONS[0] or height > MAX_IMAGE_DIMENSIONS[1]:
			logger.warning(f"Image dimensions too large: {width}x{height} > {MAX_IMAGE_DIMENSIONS}")
			return False

		# Check total pixel count
		total_pixels = width * height
		if total_pixels > MAX_IMAGE_PIXELS:
			logger.warning(f"Image pixel count too large: {total_pixels} > {MAX_IMAGE_PIXELS}")
			return False

		return True

	except (ValueError, TypeError) as e:
		logger.error(f"Invalid image dimensions: {e}")
		return False

def validate_password_basic(password: str) -> str:
	"""Validate password strength requirements."""
	if not isinstance(password, str):
		raise SecurityValidationError("Password must be a string")

	# Check basic length requirements
	if len(password) < 8:
		raise SecurityValidationError("Password must be at least 8 characters long")

	if len(password) > 128:
		raise SecurityValidationError("Password must not exceed 128 characters")

	# Use password-strength library if available, otherwise fallback to basic checks
	if _PASSWORD_STRENGTH_AVAILABLE:
		policy = PasswordPolicy.from_names(
			strength=0.5  # need a password that scores at least 0.5 with its strength
		)

		# Test the password
		issues = policy.test(password)
		if issues:
			# Convert issues to readable error messages
			error_messages = []
			for issue in issues:
				if hasattr(issue, '__class__'):
					error_messages.append(str(issue))
			if error_messages:
				raise SecurityValidationError(f"Password is too weak: {', '.join(error_messages)}")
	else:
		# Fallback to basic validation
		# Check for at least one lowercase letter
		if not re.search(r'[a-z]', password):
			raise SecurityValidationError("Password must contain at least one lowercase letter")

		# Check for at least one uppercase letter or digit
		if not (re.search(r'[A-Z]', password) or re.search(r'[0-9]', password)):
			raise SecurityValidationError("Password must contain at least one uppercase letter or digit")

		# Check for common weak passwords
		weak_passwords = {
			"password", "password123", "12345678", "qwerty", "abc123", "letmein",
			"welcome", "monkey", "123456789", "password1", "admin", "administrator"
		}
		if password.lower() in weak_passwords:
			raise SecurityValidationError("Password is too common and easily guessable")

	return password

def validate_filesystem_safe_id(id_string: str, field_name: str = "ID") -> str:
	"""Validate ID contains only filesystem-safe characters (alphanumerics and dashes)."""
	if not isinstance(id_string, str):
		raise SecurityValidationError(f"{field_name} must be a string")

	# Remove any whitespace
	id_string = id_string.strip()

	if not id_string:
		raise SecurityValidationError(f"{field_name} cannot be empty")

	# Check that it contains only alphanumerics and dashes
	if not re.match(r'^[a-zA-Z0-9\-]+$', id_string):
		raise SecurityValidationError(f"Invalid {field_name}: must contain only alphanumerics and dashes")

	# Reasonable length limits
	if len(id_string) < 1 or len(id_string) > 100:
		raise SecurityValidationError(f"Invalid {field_name}: length must be between 1 and 100 characters")

	return id_string

def validate_photo_id(photo_id: str) -> str:
	"""Validate photo ID for filesystem safety."""
	return validate_filesystem_safe_id(photo_id, "photo_id")

def validate_user_id(user_id: str) -> str:
	"""Validate user ID for filesystem safety."""
	return validate_filesystem_safe_id(user_id, "user_id")

def generate_client_key_id(public_key_pem: str) -> str:
	"""
	Generate client_key_id from public key PEM using SHA256 fingerprint.

	Args:
		public_key_pem: PEM-formatted public key

	Returns:
		Client key ID in format "key_<sha256_hex>"
	"""
	try:
		hash_value = hashlib.sha256(public_key_pem.encode('utf-8')).hexdigest()
		return f"key_{hash_value}"
	except Exception as e:
		logger.error(f"Error generating client key ID: {e}")
		raise

def validate_client_key_id_fingerprint(client_key_id: str, public_key_pem: str) -> bool:
	"""
	Validate that client_key_id is the correct SHA256 fingerprint of public_key_pem.

	This prevents impersonation attacks where a malicious client could provide
	an arbitrary client_key_id with their own public key.

	Args:
		client_key_id: Client-provided key ID (should be "key_<sha256_hex>")
		public_key_pem: PEM-formatted public key

	Returns:
		True if client_key_id matches the SHA256 fingerprint of public_key_pem
	"""
	try:
		# Generate expected fingerprint
		expected_hash = hashlib.sha256(public_key_pem.encode('utf-8')).hexdigest()
		expected_key_id = f"key_{expected_hash}"

		# Compare with provided client_key_id
		is_valid = client_key_id == expected_key_id

		if not is_valid:
			logger.warning(f"Client key ID fingerprint mismatch: provided={client_key_id[:20]}..., expected={expected_key_id[:20]}...")

		return is_valid

	except Exception as e:
		logger.error(f"Error validating client key ID fingerprint: {e}")
		return False

def verify_ecdsa_signature(signature_base64: str, public_key_pem: str, message_data: any) -> bool:
	"""
	Verify ECDSA P-256 signature using the client's public key.

	Args:
		signature_base64: Base64-encoded ECDSA signature
		public_key_pem: PEM-formatted ECDSA P-256 public key
		message_data: list containing the signed data

	Returns:
		True if signature is valid, False otherwise
	"""
	try:
		# Load the client's public key
		public_key = serialization.load_pem_public_key(public_key_pem.encode())

		logger.debug(f"Verifying signature with public key: {public_key_pem}")
		# Create canonical JSON message (same format as ClientCryptoManager with sorted keys)
		message = json.dumps(message_data, separators=(',', ':'), ensure_ascii=False, sort_keys=True)
		logger.info(f"🔐 string for verification: '{message}'")
		logger.debug(f"signature_base64: {signature_base64}")
		# Decode the base64 signature
		signature_bytes = base64.b64decode(signature_base64)

		# Auto-detect signature format and convert if needed
		# Web Crypto API produces 64-byte IEEE P1363 format (r||s)
		# Android/Java produces variable-length ASN.1 DER format
		if len(signature_bytes) == 64:
			# Convert P1363 to DER format
			r = int.from_bytes(signature_bytes[:32], byteorder='big')
			s = int.from_bytes(signature_bytes[32:], byteorder='big')
			signature_bytes = encode_dss_signature(r, s)

		logger.debug(f"Verifying signature: {signature_bytes.hex()}")

		# Verify the signature
		public_key.verify(
			signature_bytes,
			message.encode('utf-8'),
			ec.ECDSA(hashes.SHA256())
		)

		logger.debug(f"Signature verification successful for message: {message}")
		return True

	except Exception as e:
		logger.warning(f"Signature verification failed: {e.message if hasattr(e, 'message') else str(e)}")
		logger.warning(type(e))
		logger.warning('-------')

		return False
