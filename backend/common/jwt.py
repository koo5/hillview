"""
Common JWT token validation utilities.
Lightweight authentication functions that don't require database access.
Uses asymmetric ECDSA keys for secure token validation without forgery risk.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import os
import logging

logger = logging.getLogger(__name__)

# ECDSA configuration
ALGORITHM = "ES256"

def _load_or_generate_keys():
    """Load ECDSA keys from environment or generate defaults for development."""
    private_key_pem = os.getenv("JWT_PRIVATE_KEY")
    public_key_pem = os.getenv("JWT_PUBLIC_KEY")
    
    if private_key_pem and public_key_pem:
        # Load keys from environment (production)
        try:
            private_key = serialization.load_pem_private_key(
                private_key_pem.encode(), 
                password=None
            )
            public_key = serialization.load_pem_public_key(public_key_pem.encode())
            logger.info("Loaded JWT ECDSA keys from environment")
            return private_key, public_key
        except Exception as e:
            logger.error(f"Failed to load JWT keys from environment: {e}")
            raise
    
    # Generate keys for development
    logger.warning("No JWT keys in environment, generating temporary ECDSA keys for development!")
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    
    # Log the generated keys for development use
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode()
    
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    
    logger.warning("Generated JWT_PRIVATE_KEY for development:")
    logger.warning(private_pem)
    logger.warning("Generated JWT_PUBLIC_KEY for development:")
    logger.warning(public_pem)
    
    return private_key, public_key

# Load keys (private key may be None in worker service)
try:
    PRIVATE_KEY, PUBLIC_KEY = _load_or_generate_keys()
except Exception:
    # Worker service may only have public key
    PRIVATE_KEY = None
    public_key_pem = os.getenv("JWT_PUBLIC_KEY")
    if public_key_pem:
        PUBLIC_KEY = serialization.load_pem_public_key(public_key_pem.encode())
        logger.info("Loaded JWT public key for verification only")
    else:
        logger.error("No JWT public key available for token verification")
        PUBLIC_KEY = None

def validate_jwt_token(token: str, verify_exp: bool = True) -> Optional[Dict[str, Any]]:
    """
    Validate a JWT token and return the payload if valid.
    Returns None if token is invalid or expired (when verify_exp=True).
    Uses ECDSA public key for verification - cannot forge tokens.
    
    Args:
        token: JWT token to validate
        verify_exp: Whether to verify expiration (default True)
    
    Returns:
        Dict with username, user_id, payload, and exp if valid, None otherwise
    """
    if not PUBLIC_KEY:
        logger.error("No public key available for JWT token verification")
        return None
        
    try:
        # Decode and validate JWT token with ECDSA public key
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=[ALGORITHM], options={"verify_exp": verify_exp})
        
        # Validate token type
        token_type = payload.get("type")
        if token_type != "access":
            logger.warning(f"Invalid token type: {token_type}")
            return None
        
        username: str = payload.get("sub")
        user_id: str = payload.get("user_id")
        
        if username is None or user_id is None:
            logger.warning("Token missing username or user_id")
            return None
        
        # Extract expiration time
        exp_timestamp = payload.get("exp")
        
        logger.debug(f"Token validated for user: {username}, id: {user_id}")
        return {
            "username": username,
            "user_id": user_id,
            "payload": payload,
            "exp": exp_timestamp
        }
        
    except JWTError as e:
        logger.warning(f"JWT Error: {str(e)}")
        return None

def create_access_token(data: dict, expires_delta: Optional[int] = None) -> tuple[str, datetime]:
    """
    Create a JWT access token using ECDSA private key.
    Only available in API server (requires private key).
    
    Args:
        data: Payload data to encode
        expires_delta: Expiration time in minutes (default: 30)
    
    Returns:
        Tuple of (encoded_jwt, expiration_datetime)
    """
    if not PRIVATE_KEY:
        raise RuntimeError("No private key available for token creation")
    
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + timedelta(minutes=expires_delta)
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=30)  # Default 30 minutes
    
    # Add issued at time and token type
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(to_encode, PRIVATE_KEY, algorithm=ALGORITHM)
    return encoded_jwt, expire

def create_refresh_token(data: dict) -> tuple[str, datetime]:
    """
    Create a JWT refresh token using ECDSA private key.
    Only available in API server (requires private key).
    
    Args:
        data: Payload data to encode
    
    Returns:
        Tuple of (encoded_jwt, expiration_datetime)
    """
    if not PRIVATE_KEY:
        raise RuntimeError("No private key available for token creation")
    
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=7)  # 7 day refresh tokens
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh"
    })
    
    encoded_jwt = jwt.encode(to_encode, PRIVATE_KEY, algorithm=ALGORITHM)
    return encoded_jwt, expire

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