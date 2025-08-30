"""
Generic JWT utilities for validation and key management.
No specific business logic - just reusable JWT operations.
"""

import os
from datetime import datetime, timezone, timedelta
from .utc import utcnow, utc_plus_timedelta
from typing import Optional, Dict, Any, Tuple
from jose import JWTError, jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import logging

logger = logging.getLogger(__name__)

# ECDSA configuration
ALGORITHM = "ES256"

def generate_ecdsa_key_pair():
	"""Generate a new ECDSA P-256 key pair for JWT signing."""
	private_key = ec.generate_private_key(ec.SECP256R1())
	public_key = private_key.public_key()
	return private_key, public_key

def serialize_private_key(private_key) -> str:
	"""Serialize private key to PEM format."""
	return private_key.private_bytes(
		encoding=serialization.Encoding.PEM,
		format=serialization.PrivateFormat.PKCS8,
		encryption_algorithm=serialization.NoEncryption()
	).decode()

def serialize_public_key(public_key) -> str:
	"""Serialize public key to PEM format."""
	return public_key.public_bytes(
		encoding=serialization.Encoding.PEM,
		format=serialization.PublicFormat.SubjectPublicKeyInfo
	).decode()

def load_private_key_from_pem(pem_data: str):
	"""Load private key from PEM string."""
	return serialization.load_pem_private_key(pem_data.encode(), password=None)

def load_public_key_from_pem(pem_data: str):
	"""Load public key from PEM string."""
	return serialization.load_pem_public_key(pem_data.encode())

def create_jwt_token(
	payload: Dict[str, Any],
	private_key,
	expires_minutes: int = 30
) -> Tuple[str, datetime]:
	"""
	Create a JWT token with the given payload and private key.

	Args:
		payload: Data to include in the JWT
		private_key: ECDSA private key for signing
		expires_minutes: Token expiration time in minutes

	Returns:
		Tuple of (JWT token string, expiration datetime)
	"""
	# Add expiration time
	expire_time = utc_plus_timedelta(timedelta(minutes=expires_minutes))
	payload_with_exp = {**payload, "exp": expire_time}

	# Create JWT token
	token = jwt.encode(payload_with_exp, private_key, algorithm=ALGORITHM)
	return token, expire_time

def validate_jwt_token(
	token: str,
	public_key,
	verify_exp: bool = True
) -> Optional[Dict[str, Any]]:
	"""
	Validate a JWT token using the provided public key.

	Args:
		token: JWT token to validate
		public_key: ECDSA public key for verification
		verify_exp: Whether to verify token expiration

	Returns:
		Decoded payload if valid, None if invalid
	"""
	logger.debug('Validating JWT token: %s', token)
	try:
		options = {"verify_exp": verify_exp}
		payload = jwt.decode(token, public_key, algorithms=[ALGORITHM], options=options)
		logger.debug('JWT validation successful, payload: %s', payload)
		return payload
	except JWTError as e:
		logger.debug(f"JWT validation failed: {e}")
		return None

def extract_bearer_token(authorization_header: Optional[str]) -> Optional[str]:
	"""
	Extract JWT token from Authorization header.
	Expected format: "Bearer <token>"
	"""
	if not authorization_header:
		return None

	parts = authorization_header.split()
	if len(parts) != 2 or parts[0].lower() != "bearer":
		return None

	return parts[1]

def format_keys_for_env(private_key_pem: str, public_key_pem: str, prefix: str = "JWT") -> str:
	"""Format keys for .env file with proper escaping."""
	private_escaped = private_key_pem.strip().replace('\n', '\\n')
	public_escaped = public_key_pem.strip().replace('\n', '\\n')

	return f'{prefix}_PRIVATE_KEY="{private_escaped}"\n{prefix}_PUBLIC_KEY="{public_escaped}"'

def load_or_generate_keys(service_name: str = "Service"):
	"""
	Generic key loading/generation function using standard JWT_PRIVATE_KEY/JWT_PUBLIC_KEY env vars.

	Args:
		service_name: Service name for logging (e.g., "API", "Worker")

	Returns:
		Tuple of (private_key, public_key)
	"""
	private_key_pem = os.getenv("JWT_PRIVATE_KEY")
	public_key_pem = os.getenv("JWT_PUBLIC_KEY")

	if private_key_pem and public_key_pem:
		try:
			private_key = load_private_key_from_pem(private_key_pem)
			public_key = load_public_key_from_pem(public_key_pem)
			logger.info(f"Loaded {service_name} JWT keys from environment")
			return private_key, public_key
		except Exception as e:
			logger.error(f"Failed to load {service_name} JWT keys: {e}")
			raise

	# Generate keys for development
	logger.warning(f"No {service_name} JWT keys in environment, generating temporary keys for development!")
	private_key, public_key = generate_ecdsa_key_pair()

	# Log formatted keys for development
	private_pem = serialize_private_key(private_key)
	public_pem = serialize_public_key(public_key)

	logger.warning(f"Generated {service_name} JWT keys for development - add these to your .env file:")
	logger.warning("")
	for line in format_keys_for_env(private_pem, public_pem).split('\n'):
		logger.warning(line)

	return private_key, public_key