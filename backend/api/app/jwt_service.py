"""
API server JWT service - handles API-specific token operations.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))

# Initialize environment first
from common import env_init

import logging
from datetime import datetime, timezone, timedelta
from common.utc import utcnow, utc_plus_timedelta
from typing import Optional, Dict, Any, Tuple

# Load common modules
from common.jwt_utils import load_or_generate_keys, create_jwt_token, validate_jwt_token

logger = logging.getLogger(__name__)

# API server keys (loaded once at startup - environment is now initialized)
PRIVATE_KEY, PUBLIC_KEY = load_or_generate_keys("API server")

# Import refresh token expiration configuration (in minutes)
REFRESH_TOKEN_EXPIRE_MINUTES = int(os.getenv("REFRESH_TOKEN_EXPIRE_MINUTES", str(7 * 24 * 60)))  # Default 7 days

def create_access_token(data: dict, expires_delta: Optional[int] = None) -> Tuple[str, datetime]:
	"""Create an access token for user authentication."""
	expires_minutes = expires_delta or 30  # Default 30 minutes
	
	to_encode = {
		**data,
		"type": "access"
	}
	
	return create_jwt_token(to_encode, PRIVATE_KEY, expires_minutes)

def create_refresh_token(data: dict) -> Tuple[str, datetime]:
	"""Create a refresh token with longer expiration."""
	expires_minutes = REFRESH_TOKEN_EXPIRE_MINUTES
	
	to_encode = {
		**data,
		"type": "refresh"
	}
	
	return create_jwt_token(to_encode, PRIVATE_KEY, expires_minutes)

def create_upload_authorization_token(data: dict) -> Tuple[str, datetime]:
	"""Create an upload authorization token for workers."""
	expires_minutes = 60  # 1 hour
	
	to_encode = {
		**data,
		"type": "upload_authorization"
	}
	
	return create_jwt_token(to_encode, PRIVATE_KEY, expires_minutes)

def validate_token(token: str, verify_exp: bool = True) -> Optional[Dict[str, Any]]:
	"""Validate a JWT token using this service's public key."""
	if not PUBLIC_KEY:
		logger.error("No public key available for token validation")
		return None
		
	return validate_jwt_token(token, PUBLIC_KEY, verify_exp)

def validate_upload_authorization_token(token: str) -> Optional[Dict[str, Any]]:
	"""
	Validate an upload authorization JWT token.
	Used by the API to verify upload authorization tokens.
	
	Args:
		token: Upload authorization JWT token
	
	Returns:
		Dict with upload metadata if valid, None otherwise
	"""
	payload = validate_token(token, verify_exp=True)
	if not payload:
		return None
		
	# Validate token type
	token_type = payload.get("type")
	if token_type != "upload_authorization":
		logger.warning(f"Invalid token type: {token_type}, expected upload_authorization")
		return None
	
	# Check required fields
	required_fields = ["photo_id", "user_id", "client_public_key_id"]
	for field in required_fields:
		if field not in payload:
			logger.warning(f"Upload authorization token missing required field: {field}")
			return None
	
	return payload