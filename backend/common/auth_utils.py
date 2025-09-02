"""
Authentication utilities for password hashing and verification.
Shared between API and tests.
"""
from passlib.context import CryptContext

# Password hashing context
# Use only bcrypt to avoid deprecated crypt module warnings
pwd_context = CryptContext(
	schemes=["bcrypt"], 
	deprecated="auto",
	bcrypt__rounds=12  # Use explicit rounds for bcrypt
)

def verify_password(plain_password: str, hashed_password: str) -> bool:
	"""Verify a plain password against a hashed password."""
	return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
	"""Hash a password using bcrypt."""
	return pwd_context.hash(password)