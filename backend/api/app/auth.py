from datetime import datetime, timedelta
import sys
import os
import secrets
import uuid
import logging

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))

from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
from pydantic import BaseModel

from common.utc import utcnow, utc_plus_timedelta, utc_from_timestamp
from common.database import get_db
from common.models import User, TokenBlacklist
from jwt_service import (  # noqa: F401 - re-exported
	validate_token, create_access_token, create_refresh_token, REFRESH_TOKEN_EXPIRE_MINUTES,
)

logger = logging.getLogger(__name__)

# Security configuration
# Generate a secure random key if not provided
DEFAULT_SECRET_KEY = secrets.token_urlsafe(32)
SECRET_KEY = os.getenv("SECRET_KEY", DEFAULT_SECRET_KEY)

# Warn if using default key (should only happen in development)
if SECRET_KEY == DEFAULT_SECRET_KEY:
	logger.warning("Using auto-generated JWT secret key. Set SECRET_KEY environment variable in production!")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "100"))

# Test users configuration
TEST_USERS = os.getenv("TEST_USERS", "false").lower() in ("true", "1", "yes")


def is_strict_refresh_rotation_enabled() -> bool:
	"""Whether to enforce single-use refresh-token rotation with reuse detection.

	Gated for gradual rollout. Old app versions refresh from several contexts
	(WebView plugin, upload worker, push manager) without a shared refresh lock,
	so two of them can present the same refresh token at once. Strict mode treats
	that as token theft and revokes the whole session — which would spuriously log
	those old clients out. Set STRICT_REFRESH_ROTATION=false while old clients are
	still in the wild; flip to true (the default) once they've aged out.

	Read per-call (not cached at import) so it can be toggled by tests / a restart
	without code changes. Only the reuse *enforcement* is gated — logout family
	revocation and the session-revoked checks stay on regardless, since they don't
	depend on client concurrency behaviour and never fire for a well-behaved old app.
	"""
	return os.getenv("STRICT_REFRESH_ROTATION", "true").strip().lower() in ("true", "1", "yes")

# OAuth2 configuration
OAUTH_PROVIDERS = {
	"google": {
		"client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
		"client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
		"redirect_uri": os.getenv("GOOGLE_REDIRECT_URI", ""),
		"auth_url": "https://accounts.google.com/o/oauth2/auth",
		"token_url": "https://oauth2.googleapis.com/token",
		"userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
	},
	"github": {
		"client_id": os.getenv("GITHUB_CLIENT_ID", ""),
		"client_secret": os.getenv("GITHUB_CLIENT_SECRET", ""),
		"redirect_uri": os.getenv("GITHUB_REDIRECT_URI", ""),
		"auth_url": "https://github.com/login/oauth/authorize",
		"token_url": "https://github.com/login/oauth/access_token",
		"userinfo_url": "https://api.github.com/user",
	}
}

# Canonical public base URL of this API server, e.g. "https://api.hillview.cz/".
# When set, OAuth callback URIs are built from it rather than from the request's
# Host header, so a client-controlled Host can never leak into the redirect_uri
# sent to OAuth providers. Leave unset in dev, where the host legitimately varies
# (localhost vs 10.0.2.2 from the Android emulator). Not to be confused with
# API_URL (worker-internal, includes the /api path).
API_BASE_URL = os.getenv("API_BASE_URL", "")
if API_BASE_URL and not API_BASE_URL.endswith("/"):
	API_BASE_URL += "/"


def public_base_url(request: Request) -> str:
	"""Base URL for building absolute callback URLs, always ending with '/'.

	Prefers the configured canonical API_BASE_URL; falls back to the
	Host-header-derived request.base_url when unset (dev).
	"""
	return API_BASE_URL or str(request.base_url)

# Import password hashing utilities from common
from common.auth_utils import verify_password, get_password_hash

# OAuth2 token URL
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

# Models
class Token(BaseModel):
	access_token: str
	refresh_token: Optional[str] = None
	token_type: str
	# Pydantic serializes these as Z-terminated ISO-8601 instants (e.g.
	# "2026-06-28T12:19:34.495568Z"). The Android native token store parses them with
	# Java's DateTimeFormatter.ISO_INSTANT, which requires the trailing 'Z' and rejects a
	# "+00:00" offset. So always hand token expiries to clients through this model — not a
	# hand-rolled dict using datetime.isoformat(), which would emit "+00:00".
	expires_at: datetime
	refresh_token_expires_at: Optional[datetime] = None

class TokenData(BaseModel):
	username: Optional[str] = None
	user_id: Optional[str] = None

class RefreshTokenRequest(BaseModel):
	refresh_token: str

class UserCreate(BaseModel):
	email: str
	username: str
	password: str

class UserLogin(BaseModel):
	username: str
	password: str

class UserOAuth(BaseModel):
	provider: str
	code: str
	redirect_uri: Optional[str] = None

class UserOut(BaseModel):
	id: str
	email: str
	username: str
	is_active: bool
	is_test: bool
	created_at: datetime

	class Config:
		from_attributes = True

# Password hashing functions are now imported from common.auth_utils

# Token creation functions moved to common/jwt.py

async def get_user_by_username(db: AsyncSession, username: str):
	result = await db.execute(select(User).where(User.username == username))
	return result.scalars().first()

async def get_user_by_email(db: AsyncSession, email: str):
	result = await db.execute(select(User).where(User.email == email))
	return result.scalars().first()

async def get_user_by_oauth(db: AsyncSession, provider: str, oauth_id: str):
	result = await db.execute(
		select(User).where(User.oauth_provider == provider, User.oauth_id == oauth_id)
	)
	return result.scalars().first()

async def authenticate_user(db: AsyncSession, username: str, password: str):
	logger.debug(f"Authenticating user: {username}")
	user = await get_user_by_username(db, username)
	if not user:
		logger.debug(f"User not found by username, trying email: {username}")
		user = await get_user_by_email(db, username)  # Try with email

	if not user:
		logger.warning(f"Authentication failed: User not found: {username}")
		return False

	# Check if user is active BEFORE password verification
	if not user.is_active:
		logger.warning(f"Authentication failed: User is disabled: {username}")
		return False

	logger.debug(f"Verifying password for user {username}")
	logger.debug(f"Stored hash: {user.hashed_password[:50]}...")
	logger.debug(f"Password to verify: {password}")
	password_valid = verify_password(password, user.hashed_password)
	logger.debug(f"Password verification result: {password_valid}")
	if not password_valid:
		logger.warning(f"Authentication failed: Invalid password for user: {username}")
		return False

	logger.info(f"Authentication successful for user: {username}, id: {user.id}")
	return user

async def get_current_user(
	token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
):
	credentials_exception = HTTPException(
		status_code=status.HTTP_401_UNAUTHORIZED,
		detail="Could not validate credentials",
		headers={"WWW-Authenticate": "Bearer"},
	)

	inactive_user_exception = HTTPException(
		status_code=status.HTTP_403_FORBIDDEN,
		detail="User account is disabled",
	)

	# Use common JWT validation

	token_data_dict = validate_token(token)
	if not token_data_dict:
		logger.warning("Token validation failed")
		raise credentials_exception

	username = token_data_dict["username"]
	user_id = token_data_dict["sub"]

	# Check if token is blacklisted
	if await is_token_blacklisted(token, db):
		logger.warning(f"Blacklisted token used by user: {user_id}")
		raise credentials_exception

	# Session-family revocation: logout (and refresh-token reuse detection) revokes
	# the whole session by its sid, so *every* access token minted for that session
	# is rejected — not just the one token that happened to be blacklisted on logout.
	if await is_session_revoked(token_data_dict.get("sid"), db):
		logger.warning(f"Revoked session token used by user: {user_id}")
		raise credentials_exception

	# Debug force-logout flag (in-memory, set via /api/internal/debug/force-logout-user).
	# Mirrors blacklist semantics without needing the token itself.
	if is_user_force_logged_out(user_id):
		logger.warning(f"Force-logout flag set for user {user_id}; rejecting token")
		raise credentials_exception

	token_data = TokenData(username=username, user_id=user_id)

	# Fetch user from database
	result = await db.execute(select(User).where(User.id == user_id))
	user = result.scalars().first()

	if user is None:
		logger.warning(f"User not found with ID: {user_id}")
		raise credentials_exception

	# Check if user is active IMMEDIATELY after fetching
	if not user.is_active:
		logger.warning(f"Disabled user attempted access: {user_id}")
		raise inactive_user_exception

	logger.debug(f"User authenticated successfully: {user.username}, id: {user.id}")
	return user

# Check if token is blacklisted
async def is_token_blacklisted(token: str, db: AsyncSession) -> bool:
	"""Check if a token has been blacklisted."""
	result = await db.execute(
		select(TokenBlacklist).where(
			TokenBlacklist.token == token,
			TokenBlacklist.expires_at > utcnow()
		)
	)
	return result.scalars().first() is not None


# ------------------------------------------------------------
# Session-family revocation and refresh-token single-use.
#
# Access and refresh tokens minted together share a session id ("sid"); refresh
# tokens additionally carry a unique per-token id ("jti"). We reuse the existing
# token_blacklist table (no migration) by storing synthetic keys:
#   - "sid:<sid>" — a revoked session family (logout / reuse detection)
#   - "jti:<jti>" — a refresh token that has already been rotated away (spent)
# Both rows carry the natural expiry so they age out on their own.
# ------------------------------------------------------------
def new_session_id() -> str:
	"""Generate a session-family id shared by an access/refresh token pair."""
	return str(uuid.uuid4())


def new_refresh_jti() -> str:
	"""Generate a unique id for a single refresh token."""
	return str(uuid.uuid4())


def _session_key(sid: str) -> str:
	return f"sid:{sid}"


def _refresh_jti_key(jti: str) -> str:
	return f"jti:{jti}"


async def is_session_revoked(sid: Optional[str], db: AsyncSession) -> bool:
	"""True if the given session family has been revoked (logout / reuse)."""
	if not sid:
		return False
	result = await db.execute(
		select(TokenBlacklist).where(
			TokenBlacklist.token == _session_key(sid),
			TokenBlacklist.expires_at > utcnow()
		)
	)
	return result.scalars().first() is not None


async def is_refresh_token_spent(jti: Optional[str], db: AsyncSession) -> bool:
	"""True if this refresh token has already been rotated away (single-use)."""
	if not jti:
		return False
	result = await db.execute(
		select(TokenBlacklist).where(
			TokenBlacklist.token == _refresh_jti_key(jti),
			TokenBlacklist.expires_at > utcnow()
		)
	)
	return result.scalars().first() is not None


async def _record_blacklist_key(key: str, user_id: str, expires_at: datetime, reason: str, db: AsyncSession) -> None:
	"""Insert a synthetic blacklist row, tolerating a concurrent duplicate insert.

	The token column is unique, so a benign race (e.g. two tabs rotating the same
	refresh token at once) that tries to write the same key twice must not blow up
	— the row already existing is exactly the outcome we wanted.
	"""
	db.add(TokenBlacklist(token=key, user_id=user_id, expires_at=expires_at, reason=reason))
	try:
		await db.commit()
	except IntegrityError:
		await db.rollback()
		logger.debug(f"Blacklist key already present (concurrent write): {key}")


async def spend_refresh_token(jti: str, user_id: str, expires_at: datetime, db: AsyncSession) -> None:
	"""Mark a refresh token as used so it cannot be replayed after rotation."""
	if not jti:
		return
	await _record_blacklist_key(_refresh_jti_key(jti), user_id, expires_at, "refresh_rotated", db)


async def revoke_session(sid: Optional[str], user_id: str, db: AsyncSession, reason: str = "logout") -> None:
	"""Revoke a whole session family (all its access + refresh tokens).

	Expiry is set to the maximum refresh-token lifetime so the revocation
	outlives any refresh token in the family (logout only has the short-lived
	access token to hand, so we can't read the refresh expiry here).
	"""
	if not sid:
		return
	expires_at = utc_plus_timedelta(timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES))
	await _record_blacklist_key(_session_key(sid), user_id, expires_at, reason, db)


# ------------------------------------------------------------
# Debug: force-logout flag. Internal-only, in-memory, per-process.
#
# Set via POST /api/internal/debug/force-logout-user; read by
# get_current_user and refresh_access_token to reject any token
# belonging to the flagged user. Causes the client to observe the
# same 401 pattern as a real blacklist / session invalidation, which
# drives the Android "Login Required" notification flow.
# Cleared automatically on next successful password-auth login.
# ------------------------------------------------------------
_force_logout_user_ids: set[str] = set()


def force_user_logout(user_id: str) -> None:
	_force_logout_user_ids.add(str(user_id))


def clear_user_force_logout(user_id: str) -> None:
	_force_logout_user_ids.discard(str(user_id))


def is_user_force_logged_out(user_id: str) -> bool:
	return str(user_id) in _force_logout_user_ids


# Debug: short access-token TTL override. Internal-only, in-memory, per-process.
# Set via POST /api/internal/debug/set-access-ttl; read by the password-login
# endpoint so a test user receives a short-lived access token and crosses the
# client's proactive-refresh window on demand — used (with the `auth_refresh`
# debug delay) to exercise refresh-timeout / transient-failure handling without
# waiting out the ~100-minute access-token lifetime.
_access_ttl_override_seconds: dict[str, float] = {}


def set_user_access_ttl(user_id: str, seconds: float) -> None:
	_access_ttl_override_seconds[str(user_id)] = seconds


def clear_user_access_ttl(user_id: str) -> None:
	_access_ttl_override_seconds.pop(str(user_id), None)


def get_user_access_ttl(user_id: str) -> Optional[float]:
	return _access_ttl_override_seconds.get(str(user_id))

async def blacklist_token(token: str, user_id: str, reason: str, db: AsyncSession) -> None:
	"""Add a token to the blacklist."""
	try:
		# Decode token to get expiration time using proper JWT validation
		payload = validate_token(token, verify_exp=False)  # Don't verify expiry for blacklisting
		if payload:
			exp_timestamp = payload.get("exp")
			if exp_timestamp:
				# Must be tz-aware UTC: is_token_blacklisted compares against utcnow().
				# datetime.fromtimestamp() (no tz) returns naive *local* time, which on a
				# non-UTC host lands the expiry in the wrong instant and can drop the token
				# off the blacklist before it truly expires.
				expires_at = utc_from_timestamp(exp_timestamp)
			else:
				# Default to 30 days if no expiration
				expires_at = utc_plus_timedelta(timedelta(days=30))
		else:
			# If we can't decode the token, default to 30 days
			expires_at = utc_plus_timedelta(timedelta(days=30))

		blacklist_entry = TokenBlacklist(
			token=token,
			user_id=user_id,
			expires_at=expires_at,
			reason=reason
		)
		db.add(blacklist_entry)
		await db.commit()
		logger.info(f"Token blacklisted for user {user_id}, reason: {reason}")
	except Exception as e:
		logger.error(f"Error blacklisting token: {str(e)}")
		await db.rollback()
		raise

async def blacklist_all_user_tokens(user_id: str, reason: str, db: AsyncSession) -> None:
	"""Blacklist all tokens for a specific user when they're disabled."""
	# This is a placeholder - in production, you'd need to track all active tokens
	# For now, we'll rely on the is_active check in get_current_user
	logger.info(f"All tokens invalidated for user {user_id}, reason: {reason}")

async def get_current_active_user(current_user: User = Depends(get_current_user)):
	if not current_user.is_active:
		raise HTTPException(status_code=400, detail="Inactive user")
	return current_user

async def get_current_user_optional(
	token: Optional[str] = Depends(OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)),
	db: AsyncSession = Depends(get_db)
) -> Optional[User]:
	"""Get current user if authenticated, otherwise return None"""
	if not token:
		return None

	try:
		# Use common JWT validation (same as get_current_user)
		token_data_dict = validate_token(token)
		if not token_data_dict:
			return None

		user_id = token_data_dict.get("sub")
		if user_id is None:
			return None

		# Check if token is blacklisted
		if await is_token_blacklisted(token, db):
			logger.warning(f"Blacklisted token used for user ID: {user_id}")
			return None

		# Get user from database by ID
		result = await db.execute(select(User).where(User.id == user_id))
		user = result.scalars().first()

		if user is None or not user.is_active:
			return None

		return user

	except Exception as e:
		logger.debug(f"get_current_user_optional: Error: {str(e)}")
		return None

async def get_current_user_optional_with_query(
	request: Request,
	token: Optional[str] = Depends(OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)),
	db: AsyncSession = Depends(get_db)
) -> Optional[User]:
	"""Get current user if authenticated, checking both header and query params.
	Returns None if no token provided. Raises 401 if token provided but invalid."""

	credentials_exception = HTTPException(
		status_code=status.HTTP_401_UNAUTHORIZED,
		detail="Invalid authentication token",
		headers={"WWW-Authenticate": "Bearer"},
	)

	# First try header token
	if token:
		try:
			token_data_dict = validate_token(token)
			if not token_data_dict:
				logger.warning("Invalid token in Authorization header")
				raise credentials_exception

			user_id = token_data_dict.get("sub")
			if user_id is None:
				logger.warning("Token missing user ID")
				raise credentials_exception

			if await is_token_blacklisted(token, db):
				logger.warning(f"Blacklisted token used for user ID: {user_id}")
				raise credentials_exception

			result = await db.execute(select(User).where(User.id == user_id))
			user = result.scalars().first()

			if user is None:
				logger.warning(f"User not found with ID: {user_id}")
				raise credentials_exception

			if not user.is_active:
				logger.warning(f"Inactive user attempted access: {user_id}")
				raise credentials_exception

			return user
		except HTTPException:
			raise
		except Exception as e:
			logger.warning(f"Token validation error: {str(e)}")
			raise credentials_exception

	# If no header token, try query parameter
	if request:
		query_token = request.query_params.get('token')
		if query_token:
			try:
				token_data_dict = validate_token(query_token)
				if not token_data_dict:
					logger.warning("Invalid token in query parameter")
					raise credentials_exception

				user_id = token_data_dict.get("sub")
				if user_id is None:
					logger.warning("Query token missing user ID")
					raise credentials_exception

				if await is_token_blacklisted(query_token, db):
					logger.warning(f"Blacklisted query token used for user ID: {user_id}")
					raise credentials_exception

				result = await db.execute(select(User).where(User.id == user_id))
				user = result.scalars().first()

				if user is None:
					logger.warning(f"User not found with query token ID: {user_id}")
					raise credentials_exception

				if not user.is_active:
					logger.warning(f"Inactive user attempted access with query token: {user_id}")
					raise credentials_exception

				return user
			except HTTPException:
				raise
			except Exception as e:
				logger.warning(f"Query token validation error: {str(e)}")
				raise credentials_exception

	# No token provided - anonymous access allowed
	return None

def require_role(required_role: str):
	"""Dependency factory for role-based access control."""
	async def role_checker(current_user: User = Depends(get_current_active_user)):
		from common.models import UserRole

		# Convert string to enum if needed
		if isinstance(required_role, str):
			try:
				required_role_enum = UserRole(required_role)
			except ValueError:
				raise HTTPException(status_code=400, detail=f"Invalid role: {required_role}")
		else:
			required_role_enum = required_role

		# Check if user has the required role
		if current_user.role != required_role_enum:
			# Allow admin to access all endpoints
			if current_user.role != UserRole.ADMIN:
				raise HTTPException(
					status_code=403,
					detail=f"Access denied. Required role: {required_role_enum.value}, your role: {current_user.role.value}"
				)

		return current_user

	return role_checker

# Convenience functions for common roles
def require_admin():
	"""Require admin role."""
	from common.models import UserRole
	return require_role(UserRole.ADMIN)

def require_moderator():
	"""Require moderator role (admins also have access)."""
	async def moderator_checker(current_user: User = Depends(get_current_active_user)):
		from common.models import UserRole

		if current_user.role not in [UserRole.ADMIN, UserRole.MODERATOR]:
			raise HTTPException(
				status_code=403,
				detail=f"Access denied. Required role: moderator or admin, your role: {current_user.role.value}"
			)

		return current_user

	return moderator_checker

async def delete_users_by_usernames(db: AsyncSession, usernames: list[str]) -> dict:
	"""Delete users by usernames, including their owned photos. Returns summary of deletions."""
	from sqlalchemy import delete, select
	from common.models import Photo

	summary = {
		"photos_deleted": 0,
		"users_deleted": 0
	}

	try:
		# First, get user IDs for the specified usernames
		user_ids_query = select(User.id).where(User.username.in_(usernames))
		user_ids_result = await db.execute(user_ids_query)
		user_ids = [row[0] for row in user_ids_result.fetchall()]

		if user_ids:
			# First, get all photos to delete their files
			photos_query = select(Photo).where(Photo.owner_id.in_(user_ids))
			photos_result = await db.execute(photos_query)
			photos_to_delete = photos_result.scalars().all()

			# Delete photo files from filesystem
			if photos_to_delete:
				from photos import delete_all_user_photo_files
				deleted_files_count = await delete_all_user_photo_files(photos_to_delete)
				logger.info(f"Deleted {deleted_files_count}/{len(photos_to_delete)} photo files for users: {usernames}")

			# Delete photos from database
			photo_delete_stmt = delete(Photo).where(Photo.owner_id.in_(user_ids))
			photo_result = await db.execute(photo_delete_stmt)
			summary["photos_deleted"] = photo_result.rowcount
			if photo_result.rowcount > 0:
				logger.info(f"Deleted {photo_result.rowcount} photos from database for users: {usernames}")

		# Delete the users
		user_delete_stmt = delete(User).where(User.username.in_(usernames))
		user_result = await db.execute(user_delete_stmt)
		summary["users_deleted"] = user_result.rowcount
		if user_result.rowcount > 0:
			logger.info(f"Deleted {user_result.rowcount} users: {usernames}")

		await db.commit()
		return summary

	except Exception as e:
		logger.error(f"Error deleting users {usernames}: {str(e)}")
		await db.rollback()
		raise


async def recreate_test_users() -> dict:
	"""Recreate test users with fresh passwords. Returns summary of actions taken."""

	if not TEST_USERS:
		raise ValueError("TEST_USERS is not enabled")

	from common.database import SessionLocal

	async with SessionLocal() as db:

		from common.models import UserRole

		# Hardcoded test users with roles
		test_user_data = [
			("test", "StrongTestPassword123!", UserRole.USER),
			("admin", "StrongAdminPassword123!", UserRole.ADMIN),
			("testuser", "StrongTestUserPassword123!", UserRole.USER),
		]

		summary = {
			"photos_deleted": 0,
			"users_deleted": 0,
			"users_created": 0,
			"created_users": [],
			"user_passwords": {}
		}

		try:
			test_usernames = [username for username, _, _ in test_user_data]

			# Delete existing test users and their photos
			delete_summary = await delete_users_by_usernames(db, test_usernames)
			summary["photos_deleted"] = delete_summary["photos_deleted"]
			summary["users_deleted"] = delete_summary["users_deleted"]

			# Create fresh test users
			for username, password, role in test_user_data:
				hashed_password = get_password_hash(password)
				logger.info(f"Creating test user {username} with role {role.value} and password: {password}")
				new_user = User(
					username=username,
					email=f"{username}@test.local",
					hashed_password=hashed_password,
					role=role,
					is_active=True,
					is_test=True
				)

				db.add(new_user)
				summary["created_users"].append(username)
				summary["users_created"] += 1
				summary["user_passwords"][username] = password

			await db.commit()
			logger.info(f"Created {len(test_user_data)} fresh test users")

			return summary

		except Exception as e:
			logger.error(f"Error recreating test users: {str(e)}")
			await db.rollback()
			raise

