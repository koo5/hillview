"""
Worker JWT service - handles worker-specific token operations.
"""

import sys
import os
import logging
from typing import Optional, Dict, Any

# Add common directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from common.jwt_utils import (
	load_or_generate_keys, 
	create_jwt_token, 
	validate_jwt_token, 
	load_public_key_from_pem
)

logger = logging.getLogger(__name__)

# Worker's own keys for signing results
WORKER_PRIVATE_KEY, WORKER_PUBLIC_KEY = load_or_generate_keys("Worker")

# API server's public key for verifying upload authorization tokens
API_PUBLIC_KEY = None

def load_api_public_key():
	"""Load the API server's public key for verifying upload authorization tokens."""
	global API_PUBLIC_KEY
	
	api_public_key_pem = os.getenv("API_JWT_PUBLIC_KEY")
	if api_public_key_pem:
		try:
			API_PUBLIC_KEY = load_public_key_from_pem(api_public_key_pem)
			logger.info("Loaded API server JWT public key for verification")
		except Exception as e:
			logger.error(f"Failed to load API JWT public key: {e}")
			raise
	else:
		logger.warning("No API_JWT_PUBLIC_KEY found - worker cannot verify upload authorization tokens")

def validate_upload_authorization_token(token: str) -> Optional[Dict[str, Any]]:
	"""
	Validate an upload authorization JWT token from the API server.
	Used by worker services to verify upload permissions.
	
	Args:
		token: Upload authorization JWT token
	
	Returns:
		Dict with upload metadata if valid, None otherwise
	"""
	if not API_PUBLIC_KEY:
		logger.error("No API public key available for JWT token verification")
		return None
		
	try:
		# Decode and validate JWT token with API server's public key
		payload = validate_jwt_token(token, API_PUBLIC_KEY, verify_exp=True)
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
		
	except Exception as e:
		logger.warning(f"Upload authorization JWT Error: {str(e)}")
		return None

def sign_processing_result(result_data: Dict[str, Any]) -> str:
	"""
	Sign worker processing results with worker's private key.
	
	Args:
		result_data: Processing result data to sign
		
	Returns:
		JWT token containing signed result data
	"""
	if not WORKER_PRIVATE_KEY:
		raise ValueError("No worker private key available for signing")
		
	# Add worker signature metadata
	payload = {
		**result_data,
		"type": "worker_result",
		"worker_identity": result_data.get("processed_by_worker", "unknown")
	}
	
	token, expire_time = create_jwt_token(payload, WORKER_PRIVATE_KEY, expires_minutes=60)
	return token  # Worker just needs the token

# Load API public key on import
load_api_public_key()