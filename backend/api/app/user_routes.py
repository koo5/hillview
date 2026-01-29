import datetime
import os
import sys
import uuid
import logging
import asyncio
import requests
from typing import Optional, Dict, Any, Union
from urllib.parse import urlencode, quote

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_, func, desc
from geoalchemy2.functions import ST_X, ST_Y, ST_Point
from pydantic import BaseModel

# Add common module path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import User, UserPublicKey, Photo
from common.utc import utcnow
from photos import delete_all_user_photo_files
from jwt_service import create_upload_authorization_token
from auth import (
	authenticate_user, create_access_token, create_refresh_token, get_current_active_user,
	get_password_hash, Token, UserCreate, UserLogin, UserOut, UserOAuth, RefreshTokenRequest,
	OAUTH_PROVIDERS, ACCESS_TOKEN_EXPIRE_MINUTES,
	blacklist_token, get_current_user, get_current_user_optional_with_query
)
from rate_limiter import auth_rate_limiter, check_auth_rate_limit, rate_limit_user_profile, rate_limit_user_registration, get_client_ip, general_rate_limiter, rate_limit_photo_operations
from common.config import is_rate_limiting_disabled
from security_utils import validate_username, validate_email, validate_oauth_redirect_uri, validate_password
from security_audit import security_audit

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["users"])

# OAuth session storage (in-memory, for production use Redis/database)
oauth_sessions: Dict[str, Dict[str, Any]] = {}

async def cleanup_expired_sessions():
    """Clean up expired OAuth sessions"""
    current_time = utcnow()
    expired_sessions = [
        session_id for session_id, session in oauth_sessions.items()
        if current_time > session.get('expires_at', current_time)
    ]
    for session_id in expired_sessions:
        del oauth_sessions[session_id]
        log.info(f"Cleaned up expired OAuth session: {session_id}")

    # Also log session count for monitoring
    if len(oauth_sessions) > 0:
        log.info(f"Active OAuth sessions: {len(oauth_sessions)}")

# Background cleanup task
import asyncio
from contextlib import asynccontextmanager

_cleanup_task = None

async def start_session_cleanup():
    """Start background task to clean up expired sessions"""
    global _cleanup_task
    if _cleanup_task is None:
        async def cleanup_loop():
            while True:
                try:
                    await cleanup_expired_sessions()
                    await asyncio.sleep(300)  # Clean every 5 minutes
                except Exception as e:
                    log.error(f"Session cleanup error: {e}")
                    await asyncio.sleep(60)  # Retry after 1 minute on error

        _cleanup_task = asyncio.create_task(cleanup_loop())
        log.info("Started OAuth session cleanup background task")

async def stop_session_cleanup():
    """Stop background cleanup task"""
    global _cleanup_task
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
        _cleanup_task = None
        log.info("Stopped OAuth session cleanup background task")

def store_oauth_session(tokens: Dict[str, Any], user_info: Dict[str, Any]) -> str:
    """Store OAuth tokens and return session ID"""
    session_id = str(uuid.uuid4())
    expires_at = utcnow() + datetime.timedelta(minutes=10)  # 10 minute session

    oauth_sessions[session_id] = {
        'access_token': tokens['access_token'],
        'refresh_token': tokens.get('refresh_token'),
        'expires_at': expires_at,
        'token_expires_at': tokens['expires_at'],
        'user_info': user_info,
        'created_at': utcnow()
    }

    log.info(f"Stored OAuth session {session_id} for user {user_info.get('username', 'unknown')}")
    return session_id

# Authentication routes
@router.post("/auth/register", response_model=UserOut)
async def register_user(request: Request, user: UserCreate, db: AsyncSession = Depends(get_db)):
	# Apply rate limiting for user registration
	await rate_limit_user_registration(request)

	# Validate input
	validated_username = validate_username(user.username)
	validated_email = validate_email(user.email)
	validated_password = validate_password(user.password)

	log.info(f"Registration attempt for user: {validated_username}, email: {validated_email}")

	# Check if username or email already exists
	result = await db.execute(
		select(User).where(
			or_(User.username == validated_username, User.email == validated_email)
		)
	)
	existing_user = result.scalars().first()
	if existing_user:
		log.warning(f"Registration failed - username or email already exists: {user.username}, {user.email}")
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Username or email already registered"
		)

	# Create new user
	try:
		hashed_password = get_password_hash(validated_password)
		db_user = User(
			email=validated_email,
			username=validated_username,
			hashed_password=hashed_password
		)
		db.add(db_user)
		await db.commit()
		await db.refresh(db_user)
		log.info(f"User registered successfully: {user.username}, ID: {db_user.id}")
		return db_user
	except HTTPException:
		raise
	except Exception as e:
		log.error(f"Error during user registration: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Registration failed: {str(e)}"
		)

@router.post("/auth/token", response_model=Token)
async def login_for_access_token(
	request: Request,
	form_data: OAuth2PasswordRequestForm = Depends(),
	db: AsyncSession = Depends(get_db)
):
	# Check rate limit before attempting authentication
	identifier = auth_rate_limiter.get_identifier(request, form_data.username)
	await check_auth_rate_limit(request, form_data.username)

	user = await authenticate_user(db, form_data.username, form_data.password)
	if not user:
		# Record failed attempt for rate limiting and audit
		await auth_rate_limiter.record_failed_attempt(identifier)

		# Log failed login attempt to security audit
		await security_audit.log_failed_login(
			db=db,
			request=request,
			username=form_data.username
		)

		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Incorrect username or password",
			headers={"WWW-Authenticate": "Bearer"},
		)

	# Clear failed attempts on successful login
	await auth_rate_limiter.clear_failed_attempts(identifier)

	# Log successful login to security audit
	await security_audit.log_successful_login(
		db=db,
		request=request,
		user=user,
		auth_method="password"
	)

	access_token, expires = create_access_token(
		data={"sub": user.id, "username": user.username},
		expires_delta=ACCESS_TOKEN_EXPIRE_MINUTES
	)

	refresh_token, refresh_expires = create_refresh_token(
		data={"sub": user.username, "user_id": user.id}
	)

	return {
		"access_token": access_token,
		"refresh_token": refresh_token,
		"token_type": "bearer",
		"expires_at": expires,
		"refresh_token_expires_at": refresh_expires
	}

@router.post("/auth/logout")
async def logout(
	request: Request,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""Logout user by blacklisting their current token."""
	try:
		# Extract token from Authorization header
		auth_header = request.headers.get("Authorization")
		if auth_header and auth_header.startswith("Bearer "):
			token = auth_header[7:]  # Remove "Bearer " prefix
			await blacklist_token(token, current_user.id, "logout", db)
		return {"message": "Successfully logged out"}
	except Exception as e:
		log.error(f"Error during logout: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Logout failed"
		)

@router.post("/auth/refresh", response_model=Token)
async def refresh_access_token(
	request: Request,
	refresh_request: RefreshTokenRequest,
	db: AsyncSession = Depends(get_db)
):
	"""Refresh an access token using a refresh token."""
	try:
		# Rate limit refresh requests
		if not is_rate_limiting_disabled():
			identifier = auth_rate_limiter.get_identifier(request)
			if not await auth_rate_limiter.check_rate_limit(identifier, max_requests=10, window_seconds=300):
				raise HTTPException(
					status_code=status.HTTP_429_TOO_MANY_REQUESTS,
					detail="Too many refresh requests. Try again later.",
					headers={"Retry-After": "300"}
				)

		# Verify refresh token using proper JWT validation service
		from jwt_service import validate_token

		payload = validate_token(refresh_request.refresh_token, verify_exp=True)
		if not payload:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="Invalid refresh token"
			)

		username: str = payload.get("sub")
		user_id: str = payload.get("user_id")
		token_type: str = payload.get("type")

		if not username or not user_id or token_type != "refresh":
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="Invalid refresh token"
			)

		# Get user from database
		result = await db.execute(
			select(User).where(User.username == username, User.id == user_id)
		)
		user = result.scalars().first()

		if not user or not user.is_active:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="User not found or inactive"
			)

		# Create new access token
		access_token, expires = create_access_token(
			data={"sub": user.id, "username": user.username},
			expires_delta=ACCESS_TOKEN_EXPIRE_MINUTES
		)

		# Optionally create new refresh token (rotate refresh tokens for better security)
		new_refresh_token, new_refresh_expires = create_refresh_token(
			data={"sub": user.username, "user_id": user.id}
		)

		# Log successful refresh
		await security_audit.log_event(
			db=db,
			event_type="token_refresh_success",
			user_identifier=user.username,
			ip_address=get_client_ip(request),
			user_agent=request.headers.get("user-agent"),
			event_details={"user_id": user.id},
			severity="info",
			user_id=user.id
		)

		return {
			"access_token": access_token,
			"refresh_token": new_refresh_token,
			"token_type": "bearer",
			"expires_at": expires,
			"refresh_token_expires_at": new_refresh_expires.isoformat() if hasattr(new_refresh_expires, 'isoformat') else new_refresh_expires
		}

	except HTTPException:
		raise
	except Exception as e:
		log.error(f"Error during token refresh: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Token refresh failed"
		)

@router.post("/auth/oauth-session")
async def create_oauth_session(
	request: Request,
	db: AsyncSession = Depends(get_db)
):
	"""
	Create a new OAuth session for mobile polling
	Returns a session_id that can be used for polling
	"""
	# Rate limit session creation
	if not is_rate_limiting_disabled():
		identifier = auth_rate_limiter.get_identifier(request)
		if not await auth_rate_limiter.check_rate_limit(identifier, max_requests=10, window_seconds=300):
			raise HTTPException(
				status_code=status.HTTP_429_TOO_MANY_REQUESTS,
				detail="Too many OAuth session requests.",
				headers={"Retry-After": "30"}
			)

	# Generate session ID for polling
	session_id = str(uuid.uuid4())
	expires_at = utcnow() + datetime.timedelta(minutes=10)

	# Create pending session (no tokens yet)
	oauth_sessions[session_id] = {
		'status': 'pending',
		'expires_at': expires_at,
		'created_at': utcnow(),
		'client_ip': get_client_ip(request)
	}

	log.info(f"Created OAuth session for polling: {session_id}")

	return {
		"session_id": session_id,
		"expires_at": expires_at.isoformat(),
		"status": "pending"
	}

@router.get("/auth/oauth-redirect")
async def oauth_redirect(
	provider: str,
	request: Request,
	redirect_uri: Optional[str] = None,
	session_id: Optional[str] = None,
	db: AsyncSession = Depends(get_db)
):
	"""
	Initiate OAuth flow with proper redirect URI for both web and mobile
	"""
	# Rate limit OAuth redirects to prevent abuse
	if not is_rate_limiting_disabled():
		identifier = auth_rate_limiter.get_identifier(request)
		if not await auth_rate_limiter.check_rate_limit(identifier, max_requests=20, window_seconds=300):
			raise HTTPException(
				status_code=status.HTTP_429_TOO_MANY_REQUESTS,
				detail="Too many OAuth requests. Try again later.",
				headers={"Retry-After": "300"}
			)

	# Handle redirect URI - if none provided and we have a session_id, use polling flow
	if redirect_uri is None:
		if session_id:
			# Polling flow - use localhost callback since tokens will be retrieved via polling
			validated_redirect_uri = "http://localhost:8055/api/auth/oauth-polling-callback"
		else:
			raise HTTPException(status_code=400, detail="redirect_uri is required when not using polling")
	else:
		# Validate and sanitize redirect URI
		# Define allowed domains for OAuth redirects (include mobile deep links)
		if (redirect_uri.startswith("cz.hillview://") or
			redirect_uri.startswith("cz.hillviedev://")):
			# Mobile deep link - allow it
			validated_redirect_uri = redirect_uri
		else:
			# Web redirect - validate against allowed domains
			allowed_domains = {
				'localhost:8212', 'localhost', '127.0.0.1', 'localhost:8055',
				'hillview.cz', 'api.hillview.cz', 'api.ipv4.hillview.cz', 'tauri.localhost'
			}
			try:
				validated_redirect_uri = validate_oauth_redirect_uri(redirect_uri, allowed_domains)
			except Exception as e:
				await security_audit.log_event(
					db=db,
					event_type="oauth_redirect_invalid",
					ip_address=get_client_ip(request),
					user_agent=request.headers.get("user-agent"),
					event_details={"provider": provider, "invalid_redirect_uri": redirect_uri, "error": str(e)},
					severity="warning"
				)
				raise HTTPException(status_code=400, detail="Invalid redirect URI")

	log.info(f"OAuth redirect initiated - Provider: {provider}, Redirect URI: {validated_redirect_uri}")
	log.info(f"Request base URL: {request.base_url}")

	# Log OAuth redirect attempt for audit
	await security_audit.log_event(
		db=db,
		event_type="oauth_redirect_initiated",
		ip_address=request.client.host if request.client else None,
		user_agent=request.headers.get("user-agent"),
		event_details={"provider": provider, "redirect_uri": validated_redirect_uri},
		severity="info"
	)

	if provider not in OAUTH_PROVIDERS:
		log.error(f"Unsupported OAuth provider: {provider}")
		raise HTTPException(status_code=400, detail="Unsupported OAuth provider")

	provider_config = OAUTH_PROVIDERS[provider]
	log.info(f"Provider config - Client ID: {provider_config['client_id'][:10]}..., Auth URL: {provider_config['auth_url']}")

	# Build OAuth URL with appropriate redirect URI
	if session_id:
		# Polling flow: always use API server callback regardless of redirect_uri format
		server_callback_uri = f"{request.base_url}api/auth/oauth-callback"
		log.info(f"Polling flow detected - Server callback URI: {server_callback_uri}")
	elif (validated_redirect_uri.startswith("cz.hillview://") or
		validated_redirect_uri.startswith("cz.hillviedev://")):
		# Legacy mobile flow: OAuth provider should redirect to API server callback
		server_callback_uri = f"{request.base_url}api/auth/oauth-callback"
		log.info(f"Legacy mobile flow detected - Server callback URI: {server_callback_uri}")
	else:
		# Web flow: OAuth provider should redirect to frontend callback
		# Extract frontend origin from the redirect_uri
		from urllib.parse import urlparse
		parsed = urlparse(validated_redirect_uri)
		frontend_origin = f"{parsed.scheme}://{parsed.netloc}"
		server_callback_uri = f"{frontend_origin}/oauth/callback"
		log.info(f"Web flow detected - Frontend origin: {frontend_origin}, Server callback URI: {server_callback_uri}")

	# Encode provider, redirect URI, and optional session_id in state
	if session_id:
		state_data = f"{provider}:{validated_redirect_uri}:{session_id}"
		log.info(f"Using polling session: {session_id}")
	else:
		state_data = f"{provider}:{validated_redirect_uri}"
	oauth_params = {
		"client_id": provider_config["client_id"],
		"redirect_uri": server_callback_uri,  # Dynamic server callback
		"response_type": "code",
		"state": state_data  # Store provider and final destination in state
	}

	# Add provider-specific scopes
	if provider == "google":
		oauth_params["scope"] = "email profile"
		# Add device parameters for mobile flows to handle private IP restriction
		if (validated_redirect_uri.startswith("cz.hillview://") or
			validated_redirect_uri.startswith("cz.hillviedev://")):
			import uuid
			oauth_params["device_id"] = str(uuid.uuid4())
			oauth_params["device_name"] = "Hillview Android App"
	elif provider == "github":
		oauth_params["scope"] = "user:email"

	auth_url = f"{provider_config['auth_url']}?{urlencode(oauth_params)}"

	log.info(f"OAuth params: {oauth_params}")
	log.info(f"Final OAuth URL: {auth_url}")
	log.info(f"Redirecting to OAuth provider {provider} with final destination: {validated_redirect_uri}")
	return RedirectResponse(auth_url)

@router.get("/auth/oauth-callback")
async def oauth_callback(
	request: Request,
	code: str,
	state: Optional[str] = None,
	db: AsyncSession = Depends(get_db)
):
	"""
	Enhanced OAuth callback that supports both web and mobile flows
	"""
	# Rate limit OAuth callbacks to prevent abuse
	if not is_rate_limiting_disabled():
		identifier = auth_rate_limiter.get_identifier(request)
		if not await auth_rate_limiter.check_rate_limit(identifier, max_requests=30, window_seconds=300):
			await security_audit.log_event(
				db=db,
				event_type="oauth_callback_rate_limited",
				ip_address=get_client_ip(request),
				user_agent=request.headers.get("user-agent"),
				event_details={"code_prefix": code[:10] if code else None, "state": state},
				severity="warning"
			)
			raise HTTPException(
				status_code=status.HTTP_429_TOO_MANY_REQUESTS,
				detail="Too many OAuth callback requests.",
				headers={"Retry-After": "300"}
			)

	log.info(f"OAuth callback received with code and state: {state}")

	# Extract provider, final destination, and optional session_id from state
	polling_session_id = None
	if state and ":" in state:
		# Split on first colon to get provider
		provider, remainder = state.split(":", 1)

		# Check if remainder has session ID (format: url:session_id)
		# Session ID is always after the last colon and is a UUID format
		if remainder and ":" in remainder:
			# Split from the right to get the last part as potential session ID
			url_part, potential_session = remainder.rsplit(":", 1)

			# Check if the last part looks like a session ID (UUID format)
			if len(potential_session) >= 30 and "-" in potential_session:
				final_redirect_uri = url_part
				polling_session_id = potential_session
			else:
				# Last part doesn't look like session ID, treat whole remainder as URL
				final_redirect_uri = remainder
				polling_session_id = None
		else:
			final_redirect_uri = remainder
			polling_session_id = None
	else:
		# Fallback to default if state is malformed
		provider = "google"
		final_redirect_uri = state

	log.info(f"Parsed state - Provider: {provider}, Redirect: {final_redirect_uri}, Session: {polling_session_id}")

	if provider not in OAUTH_PROVIDERS:
		raise HTTPException(status_code=400, detail="Invalid OAuth provider")

	provider_config = OAUTH_PROVIDERS[provider]

	# Exchange code for JWT using existing logic
	# Use the same redirect URI logic as the redirect endpoint
	if polling_session_id:
		# Polling flow: always use the server callback URI (same as used in OAuth redirect)
		server_callback_uri = f"{request.base_url}api/auth/oauth-callback"
	elif (final_redirect_uri and
		(final_redirect_uri.startswith("cz.hillview://") or
		 final_redirect_uri.startswith("cz.hillviedev://"))):
		# Mobile flow: used API server callback
		server_callback_uri = f"{request.base_url}api/auth/oauth-callback"
	else:
		# Web flow: used frontend callback
		from urllib.parse import urlparse
		parsed = urlparse(final_redirect_uri or "http://localhost:5173")
		frontend_origin = f"{parsed.scheme}://{parsed.netloc}"
		server_callback_uri = f"{frontend_origin}/oauth/callback"

	oauth_data = UserOAuth(
		provider=provider,
		code=code,
		redirect_uri=server_callback_uri
	)

	# Reuse existing OAuth login logic
	try:
		jwt_result = await oauth_login_internal(oauth_data, db, request)
		jwt_token = jwt_result["access_token"]
		refresh_token = jwt_result.get("refresh_token")  # Get refresh token
		expires_at = jwt_result["expires_at"]
		refresh_token_expires_at = jwt_result.get("refresh_token_expires_at")
		user_info = jwt_result.get("user_info", {})

		# Log successful OAuth login
		await security_audit.log_event(
			db=db,
			event_type="oauth_login_success",
			user_identifier=user_info.get("username"),
			ip_address=get_client_ip(request),
			user_agent=request.headers.get("user-agent"),
			event_details={
				"provider": provider,
				"auth_method": "oauth",
				"user_role": user_info.get("role"),
				"redirect_uri": final_redirect_uri
			},
			severity="info",
			user_id=user_info.get("user_id")
		)

	except Exception as e:
		# Log failed OAuth attempt
		await security_audit.log_event(
			db=db,
			event_type="oauth_login_failed",
			ip_address=get_client_ip(request),
			user_agent=request.headers.get("user-agent"),
			event_details={
				"provider": provider,
				"error": str(e),
				"code_prefix": code[:10] if code else None,
				"state": state
			},
			severity="warning"
		)
		raise

	# Clean up expired sessions before processing
	await cleanup_expired_sessions()

	# Check if deep link mode is requested via query parameter
	use_deep_links = request.query_params.get("use_deep_links") == "true"

	# Detect if this is a mobile app request or has a polling session
	if (polling_session_id or
		(final_redirect_uri and
		 (final_redirect_uri.startswith("cz.hillview://") or
		  final_redirect_uri.startswith("cz.hillviedev://")) and not use_deep_links)):
		# Mobile app: use polling mechanism instead of deep links
		log.info("Mobile OAuth callback detected, using polling mechanism")

		# Store tokens in session with limited lifetime
		tokens = {
			'access_token': jwt_token,
			'refresh_token': refresh_token,
			'expires_at': expires_at,
			'refresh_token_expires_at': refresh_token_expires_at
		}

		if polling_session_id:
			# Update existing session with tokens
			session = oauth_sessions.get(polling_session_id)
			if session:
				session.update({
					'access_token': jwt_token,
					'refresh_token': refresh_token,
					'token_expires_at': expires_at,
					'refresh_token_expires_at': refresh_token_expires_at,
					'user_info': user_info,
					'status': 'completed'
				})
				session_id = polling_session_id
				log.info(f"Updated existing polling session: {session_id}")
			else:
				# Session expired or invalid, create new one
				session_id = store_oauth_session(tokens, user_info)
				log.warning(f"Polling session {polling_session_id} not found, created new: {session_id}")
		else:
			# No polling session, create new one (legacy mobile flow)
			session_id = store_oauth_session(tokens, user_info)

		# Determine the appropriate deep link URL
		deep_link_url = None
		if final_redirect_uri and (final_redirect_uri.startswith("cz.hillview://") or final_redirect_uri.startswith("cz.hillviedev://")):
			# Use the provided deep link URL, but redirect to auth callback with session ID
			if "://" in final_redirect_uri:
				scheme = final_redirect_uri.split("://")[0]
				deep_link_url = f"{scheme}://auth?session_id={session_id}"
			else:
				deep_link_url = f"cz.hillview://auth?session_id={session_id}"
		else:
			# Default deep link for development
			deep_link_url = f"cz.hillview://auth?session_id={session_id}"

		# Create a simple success page that automatically tries to redirect to the app
		success_html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Login Successful - Hillview</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 20px;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            padding: 40px;
            max-width: 400px;
            width: 100%;
            text-align: center;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        }}
        h1 {{ margin-top: 0; color: #333; }}
        .success {{ color: #28a745; font-size: 48px; margin-bottom: 20px; }}
        .message {{ color: #666; margin: 20px 0; line-height: 1.4; }}
        .session-id {{
            font-family: monospace;
            background: #f8f9fa;
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 12px;
            color: #666;
            margin: 16px 0;
        }}
        .redirect-info {{
            background: #e3f2fd;
            border: 1px solid #90caf9;
            border-radius: 8px;
            padding: 16px;
            margin: 20px 0;
            color: #1565c0;
        }}
        .manual-link {{
            display: inline-block;
            background: #2196f3;
            color: white;
            padding: 12px 24px;
            border-radius: 6px;
            text-decoration: none;
            margin: 16px 0;
            font-weight: 500;
        }}
        .manual-link:hover {{
            background: #1976d2;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="success">✅</div>
        <h1>Login Successful!</h1>
        <div class="redirect-info">
            <strong>Redirecting to app...</strong><br>
        </div>
        <a href="{deep_link_url}" class="manual-link">Open Hillview App</a>

        <div class="message">
            <small>You can safely close this browser tab now.</small>
        </div>

        <div class="session-id">Session: {session_id}</div>
        <small><a href="{deep_link_url}" class="session-id">{deep_link_url}</a></small>

    </div>

    <script>
        // Try to redirect to the app immediately
        function redirectToApp() {{
            console.log('Attempting to redirect to app: {deep_link_url}');
            window.location.href = '{deep_link_url}';
        }}

        // Try redirect immediately
        redirectToApp();

        // Fallback: try again after a short delay
        setTimeout(redirectToApp, 1000);

        // Auto-close tab after 10 seconds if possible
        setTimeout(function() {{
            try {{
                console.log('Attempting to close tab');
                window.close();
            }} catch (e) {{
                console.log('Cannot close tab:', e);
            }}
        }}, 10000);
    </script>
</body>
</html>
"""

		return HTMLResponse(content=success_html)
	elif (final_redirect_uri and use_deep_links and
		  (final_redirect_uri.startswith("cz.hillview://") or
		   final_redirect_uri.startswith("cz.hillviedev://"))):
		# Mobile app with deep link enabled: redirect directly with tokens
		log.info("Mobile OAuth callback with deep links enabled, redirecting to app")

		from urllib.parse import urlencode
		params = {
			'token': jwt_token,
			'refresh_token': refresh_token,
			'expires_at': expires_at,
			'refresh_token_expires_at': refresh_token_expires_at,
			'token_type': 'bearer'
		}

		# Remove None values
		params = {k: v for k, v in params.items() if v is not None}

		deep_link_url = f"{final_redirect_uri}?{urlencode(params)}"
		log.info(f"Redirecting to deep link: {deep_link_url}")

		return RedirectResponse(deep_link_url)
	else:
		# Web app: existing behavior (redirect to dashboard)
		# Note: For web app, you might want to set cookies here
		log.info("Web OAuth callback, redirecting to dashboard")
		response = RedirectResponse("/")
		response.set_cookie(
			"auth_token",
			jwt_token,
			httponly=True,
			secure=True,
			samesite="lax",
			expires=expires_at
		)
		return response

@router.get("/auth/oauth-status/{session_id}")
async def get_oauth_status(
	session_id: str,
	request: Request,
	db: AsyncSession = Depends(get_db)
):
	"""
	Poll for OAuth completion status
	Returns tokens when OAuth is complete, or 404 if session not found/expired
	"""
	# Rate limit polling requests per session (not per IP)
	if not is_rate_limiting_disabled():
		# Use session_id as identifier for more granular rate limiting
		session_identifier = f"oauth_poll:{session_id}"
		if not await auth_rate_limiter.check_rate_limit(session_identifier, max_requests=72, window_seconds=360):  # 1 request per 5 seconds for 6 minutes
			raise HTTPException(
				status_code=status.HTTP_429_TOO_MANY_REQUESTS,
				detail="Polling too frequently for this session. Please slow down.",
				headers={"Retry-After": "5"}
			)

	# Clean up expired sessions
	await cleanup_expired_sessions()

	# Check if session exists and is valid
	session = oauth_sessions.get(session_id)
	if not session:
		# Session not found or expired
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="OAuth session not found or expired"
		)

	# Check if OAuth flow is complete (has access_token)
	if 'access_token' not in session:
		# OAuth flow still in progress
		raise HTTPException(
			status_code=status.HTTP_202_ACCEPTED,
			detail="OAuth flow in progress, keep polling"
		)

	# Session found and OAuth complete - return tokens and clean up
	access_token = session['access_token']
	refresh_token = session.get('refresh_token')
	token_expires_at = session['token_expires_at']
	refresh_token_expires_at = session.get('refresh_token_expires_at')
	user_info = session['user_info']

	# Log successful OAuth completion
	await security_audit.log_event(
		db=db,
		event_type="oauth_polling_success",
		user_identifier=user_info.get('username'),
		ip_address=request.client.host if request.client else None,
		user_agent=request.headers.get("user-agent"),
		event_details={
			"session_id": session_id,
			"user_role": user_info.get("role"),
			"polling_completion": True
		},
		severity="info",
		user_id=user_info.get("user_id")
	)

	# Clean up the session immediately after use
	del oauth_sessions[session_id]
	log.info(f"OAuth polling successful and session cleaned up: {session_id}")

	# Return the same format as the regular auth token endpoint
	response_data = {
		"access_token": access_token,
		"token_type": "bearer",
		"expires_at": token_expires_at.isoformat() if isinstance(token_expires_at, datetime.datetime) else token_expires_at
	}

	if refresh_token:
		response_data["refresh_token"] = refresh_token

	if refresh_token_expires_at:
		response_data["refresh_token_expires_at"] = refresh_token_expires_at if isinstance(refresh_token_expires_at, str) else refresh_token_expires_at.isoformat()

	return response_data

@router.post("/auth/oauth", response_model=Token)
async def oauth_login(
		oauth_data: UserOAuth,
	request: Request,
	db: AsyncSession = Depends(get_db)
):
	"""Public OAuth endpoint for API clients"""
	# Rate limit OAuth API endpoint
	if not is_rate_limiting_disabled():
		identifier = auth_rate_limiter.get_identifier(request)
		if not await auth_rate_limiter.check_rate_limit(identifier, max_requests=15, window_seconds=300):
			raise HTTPException(
				status_code=status.HTTP_429_TOO_MANY_REQUESTS,
				detail="Too many OAuth requests. Try again later.",
				headers={"Retry-After": "300"}
			)

	log.info(f"POST /auth/oauth called - Provider: {oauth_data.provider}, Code length: {len(oauth_data.code) if oauth_data.code else 0}, Redirect URI: {oauth_data.redirect_uri}")
	return await oauth_login_internal(oauth_data, db, request)

async def oauth_login_internal(
		oauth_data: UserOAuth,
	db: AsyncSession,
	request: Optional[Request] = None
) -> dict:
	# Validate provider
	provider = oauth_data.provider
	log.info(f"oauth_login_internal - Provider: {provider}")

	if provider not in OAUTH_PROVIDERS:
		log.error(f"Unsupported OAuth provider: {provider}")
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Unsupported OAuth provider: {provider}"
		)

	provider_config = OAUTH_PROVIDERS[provider]
	log.info(f"Provider config loaded - Client ID: {provider_config['client_id'][:10]}..., Has client_secret: {bool(provider_config['client_secret'])}")

	# Validate redirect URI to prevent open redirect attacks
	redirect_uri = oauth_data.redirect_uri or provider_config["redirect_uri"]
	log.info(f"Redirect URI resolution - oauth_data.redirect_uri: {oauth_data.redirect_uri}, provider_config redirect_uri: {provider_config['redirect_uri']}, final: {redirect_uri}")

	if redirect_uri:
		# Define allowed domains for OAuth redirects (include port for localhost)
		allowed_domains = {'localhost:8212', 'localhost', '127.0.0.1', 'localhost:8055', 'hillview.cz', 'api.hillview.cz', 'api.ipv4.hillview.cz'}
		log.info(f"Validating redirect URI: {redirect_uri} against allowed domains: {allowed_domains}")
		redirect_uri = validate_oauth_redirect_uri(redirect_uri, allowed_domains)
		log.info(f"Redirect URI after validation: {redirect_uri}")
	else:
		log.warning("No redirect URI provided")

	# Validate OAuth code (basic check)
	if not oauth_data.code or len(oauth_data.code) > 500:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Invalid OAuth authorization code"
		)

	# Exchange code for token (implementation depends on provider)
	# This is a simplified example
	token_data = {
		"client_id": provider_config["client_id"],
		"client_secret": provider_config["client_secret"],
		"code": oauth_data.code,
		"redirect_uri": redirect_uri,
		"grant_type": "authorization_code"
	}

	log.info(f"Exchanging OAuth code for token with {provider}")
	log.info(f"Token exchange data: {dict(token_data, client_secret='[REDACTED]', code='[REDACTED]')}")
	log.info(f"Token URL: {provider_config['token_url']}")

	# GitHub returns different format based on Accept header
	headers = {}
	if provider == "github":
		headers["Accept"] = "application/json"

	log.info(f"Request headers: {headers}")

	token_response = requests.post(provider_config["token_url"], data=token_data, headers=headers)
	log.info(f"Token exchange response: Status {token_response.status_code}, Headers: {dict(token_response.headers)}")

	if token_response.status_code != 200:
		log.error(f"Token exchange failed: {token_response.status_code} - {token_response.text}")
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Failed to obtain OAuth token: {token_response.text}"
		)

	# Get user info from provider
	token_json = token_response.json() if token_response.headers.get('content-type', '').startswith('application/json') else {}
	access_token = token_json.get("access_token")

	if not access_token and provider == "github" and "access_token=" in token_response.text:
		# Parse access token from response for GitHub if needed
		access_token = token_response.text.split("access_token=")[1].split("&")[0]

	headers = {"Authorization": f"Bearer {access_token}"}
	if provider == "github":
		headers["Accept"] = "application/json"

	userinfo_response = requests.get(provider_config["userinfo_url"], headers=headers)

	# For GitHub, we need to make an additional request to get the email if it's not public
	if provider == "github" and userinfo_response.status_code == 200:
		email = userinfo_response.json().get("email")
		if not email:
			email_response = requests.get("https://api.github.com/user/emails", headers=headers)
			if email_response.status_code == 200:
				emails = email_response.json()
				primary_email = next((e for e in emails if e.get("primary")), None)
				if primary_email:
					email = primary_email.get("email")

	if userinfo_response.status_code != 200:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Failed to obtain user info from OAuth provider"
		)

	userinfo = userinfo_response.json()

	# Get or create user based on OAuth ID
	oauth_id = userinfo.get("id") or userinfo.get("sub")
	email = userinfo.get("email")

	if not oauth_id:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="OAuth provider did not return required user ID"
		)

	if not email and provider == "github":
		# For GitHub, use login as fallback if email is not available
		email = f"{userinfo.get('login')}@github.com"
	elif not email:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="OAuth provider did not return required email"
		)

	# Check if user exists
	result = await db.execute(
		select(User).where(
			or_(
				User.oauth_id == oauth_id,
				User.email == email
			)
		)
	)
	user = result.scalars().first()

	if not user:
		# Create new user
		username = email.split("@")[0]
		# Check if username exists and append numbers if needed
		base_username = username
		counter = 1
		while True:
			result = await db.execute(select(User).where(User.username == username))
			if not result.scalars().first():
				break
			username = f"{base_username}{counter}"
			counter += 1

		user = User(
			email=email,
			username=username,
			oauth_provider=provider,
			oauth_id=oauth_id,
			is_verified=True  # OAuth users are considered verified
		)
		db.add(user)
		await db.commit()
		await db.refresh(user)
	elif not user.oauth_id:
		# Link existing user to OAuth
		user.oauth_provider = provider
		user.oauth_id = oauth_id
		user.is_verified = True
		await db.commit()

	# Create access token and refresh token (just like login endpoint)
	access_token, expires = create_access_token(
		data={"sub": user.id, "username": user.username},
		expires_delta=ACCESS_TOKEN_EXPIRE_MINUTES
	)

	refresh_token, refresh_expires = create_refresh_token(
		data={"sub": user.username, "user_id": user.id}
	)

	return {
		"access_token": access_token,
		"refresh_token": refresh_token,
		"token_type": "bearer",
		"expires_at": expires,
		"refresh_token_expires_at": refresh_expires.isoformat() if hasattr(refresh_expires, 'isoformat') else refresh_expires,
		"user_info": {
			"user_id": user.id,
			"username": user.username,
			"role": user.role.value if user.role else "user"
		}
	}

@router.get("/auth/me", response_model=UserOut)
async def read_users_me(
	request: Request,
	current_user: User = Depends(get_current_active_user)
):
	# Apply user profile rate limiting
	await rate_limit_user_profile(request, current_user.id)
	return current_user

@router.get("/user/profile")
async def get_user_profile(
	request: Request,
	current_user: User = Depends(get_current_active_user)
):
	"""Get detailed user profile information"""
	# Apply user profile rate limiting
	await rate_limit_user_profile(request, current_user.id)
	return {
		"id": current_user.id,
		"username": current_user.username,
		"email": current_user.email,
		"is_active": current_user.is_active,
		"created_at": current_user.created_at,
		"provider": current_user.oauth_provider,
	}

@router.delete("/user/delete")
async def delete_user_account(
	request: Request,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""Delete the current user's account and all associated data"""
	# Apply user profile rate limiting
	await rate_limit_user_profile(request, current_user.id)

	try:
		# First, get all user's photos and delete their files before CASCADE deletes DB records
		# Get all user's photos to delete their files
		photos_result = await db.execute(
			select(Photo).where(Photo.owner_id == current_user.id)
		)
		user_photos = photos_result.scalars().all()

		# Delete photo files from filesystem - must succeed before DB deletion
		if user_photos:
			deleted_count = await delete_all_user_photo_files(user_photos)
			if deleted_count != len(user_photos):
				# Some file deletions failed - abort user deletion
				raise HTTPException(
					status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
					detail=f"Failed to delete all photo files ({deleted_count}/{len(user_photos)} succeeded). User deletion aborted."
				)
			log.info(f"Successfully deleted {deleted_count} photo files for user {current_user.id}")

		# Now delete the user - CASCADE constraint will delete database records
		await db.delete(current_user)
		await db.commit()

		return {"message": "Account successfully deleted"}
	except Exception as e:
		await db.rollback()
		log.error(f"Error deleting user account: {e}")
		raise HTTPException(status_code=500, detail="Failed to delete account")


# Client public key registration for secure uploads
class ClientPublicKeyData(BaseModel):
	public_key_pem: str
	key_id: str
	created_at: str

@router.post("/auth/register-client-key")
async def register_client_public_key(
	request: Request,
	key_data: ClientPublicKeyData,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""Register client's ECDSA public key for secure upload authorization."""
	try:
		log.info(f"Registering client public key for user {current_user.id}, key_id: {key_data.key_id}")

		# Check if this key_id already exists for this user
		result = await db.execute(
			select(UserPublicKey).where(
				UserPublicKey.user_id == current_user.id,
				UserPublicKey.key_id == key_data.key_id
			)
		)
		existing_key = result.scalars().first()

		if existing_key:
			return {
				"message": "Client public key already registered",
				"key_id": key_data.key_id,
			}

		# Create new key record
		user_public_key = UserPublicKey(
			user_id=current_user.id,
			key_id=key_data.key_id,
			public_key_pem=key_data.public_key_pem,
			created_at=datetime.datetime.fromisoformat(key_data.created_at.replace('Z', '+00:00')),
			is_active=True
		)
		db.add(user_public_key)
		await db.commit()

		log.info(f"Created new client public key for user {current_user.id}")

		return {
			"message": "Client public key registered successfully",
			"key_id": key_data.key_id
		}

	except HTTPException:
		raise
	except Exception as e:
		await db.rollback()
		log.error(f"Error registering client public key: {e}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to register client public key"
		)

# Upload authorization for secure uploads
class UploadAuthorizationRequest(BaseModel):
	filename: str
	file_size: int
	content_type: str
	file_md5: str  # MD5 hash for duplicate detection
	client_key_id: str  # Key ID that will be used for signing
	description: Optional[str] = None
	is_public: bool = True
	# Geolocation data from client (EXIF or device GPS)
	latitude: Optional[float] = None
	longitude: Optional[float] = None
	altitude: Optional[float] = None
	compass_angle: Optional[float] = None
	captured_at: Optional[datetime.datetime] = None

class UploadAuthorizationResponse(BaseModel):
	upload_jwt: str
	photo_id: str
	expires_at: datetime.datetime
	worker_url: str  # URL of worker service for upload
	upload_authorized_at: int  # Unix timestamp for client signature generation

class DuplicateFileResponse(BaseModel):
	duplicate: bool
	message: str
	existing_photo_id: str
	existing_filename: str
	existing_upload_date: Optional[str]

UploadAuthorizationResponseUnion = Union[UploadAuthorizationResponse, DuplicateFileResponse]

@router.post("/photos/authorize-upload", response_model=UploadAuthorizationResponseUnion)
async def authorize_upload(
	request: Request,
	auth_request: UploadAuthorizationRequest,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""Create upload authorization JWT for secure photo upload to worker."""
	try:
		log.info(f"Creating upload authorization for user {current_user.id}: {auth_request.filename}, {auth_request.file_size} bytes, MD5: {auth_request.file_md5}, lat/lon: {auth_request.latitude}/{auth_request.longitude}, bearing: {auth_request.compass_angle}, captured_at: {auth_request.captured_at}, key_id: {auth_request.client_key_id}")

		# Basic validation of request parameters
		if not auth_request.filename.strip():
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Filename cannot be empty"
			)

		if auth_request.file_size <= 0:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="File size must be positive"
			)

		if not auth_request.content_type.startswith('image/'):
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Only image files are supported"
			)

		# Validate MD5 hash format (32 hex characters)
		if not auth_request.file_md5 or len(auth_request.file_md5) != 32:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Valid MD5 hash is required (32 hex characters)"
			)

		# Create pending photo record
		photo_id = str(uuid.uuid4())
		upload_authorized_at = datetime.datetime.now(datetime.timezone.utc)

		# Check for duplicate files by MD5 hash (per-user scope)
		result = await db.execute(
			select(Photo).where(
				Photo.owner_id == current_user.id,
				Photo.file_md5 == auth_request.file_md5
			)
		)
		existing_photo = result.scalars().first()

		if existing_photo:

			if existing_photo.processing_status in ["authorized", "error"]:
				# If there's already an authorized photo with this MD5, allow new upload
				log.info(f"Existing authorized photo found with same MD5 for user {current_user.id}, allowing new upload: MD5={auth_request.file_md5}, row id={str(existing_photo.id)}")
				# we should really just update the existing record instead of creating a new one, lets just reuse the existing id for now
				photo_id = existing_photo.id
				await db.delete(existing_photo)

			elif existing_photo.processing_status == 'completed':

				log.info(f"Duplicate file detected for user {current_user.id}: MD5={auth_request.file_md5}, row id={str(existing_photo.id)}, status={existing_photo.processing_status}")
				return {
					"duplicate": True,
					# completed: client just marks its local item as completed
					# - but it should probably also accept the new photo id
					"processing_status": existing_photo.processing_status,

					"message": f"File already exists. You previously uploaded this file as '{existing_photo.original_filename}' on {existing_photo.uploaded_at.strftime('%Y-%m-%d %H:%M:%S')}.",
					"existing_photo_id": existing_photo.id,
					"existing_filename": existing_photo.original_filename,
					"existing_upload_date": existing_photo.uploaded_at.isoformat() if existing_photo.uploaded_at else None
				}
			else:
				raise HTTPException(
					status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
					detail="Unexpected existing photo processing status"
				)

		# Get the specific client public key that will be used for signing
		result = await db.execute(
			select(UserPublicKey).where(
				UserPublicKey.user_id == current_user.id,
				UserPublicKey.key_id == auth_request.client_key_id,
				UserPublicKey.is_active == True
			)
		)
		user_public_key = result.scalars().first()

		if not user_public_key:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=f"Client public key '{auth_request.client_key_id}' not found or inactive. Please ensure the key is registered and active."
			)

		# Create geometry point from latitude/longitude if available
		geometry = None
		if auth_request.latitude is not None and auth_request.longitude is not None:
			geometry = ST_Point(auth_request.longitude, auth_request.latitude, 4326)  # WGS84 SRID

		# Convert timezone-aware captured_at to naive UTC for database storage
		captured_at_naive = None
		if auth_request.captured_at is not None:
			if auth_request.captured_at.tzinfo is not None:
				# Convert timezone-aware datetime to naive UTC
				captured_at_naive = auth_request.captured_at.astimezone(datetime.timezone.utc).replace(tzinfo=None)
			else:
				# Already naive, assume it's UTC
				captured_at_naive = auth_request.captured_at

		photo = Photo(
			id=photo_id,
			filename=None,  # Will be set by worker after file processing
			original_filename=auth_request.filename,
			file_md5=auth_request.file_md5,
			description=auth_request.description,
			is_public=auth_request.is_public,
			owner_id=current_user.id,
			processing_status="authorized",
			client_public_key_id=user_public_key.key_id,
			upload_authorized_at=upload_authorized_at,
			# Store geolocation data from client for immediate map display
			geometry=geometry,
			altitude=auth_request.altitude,
			compass_angle=auth_request.compass_angle,
			captured_at=captured_at_naive
		)

		db.add(photo)
		await db.commit()

		# Create upload authorization JWT
		upload_jwt, expires_at = create_upload_authorization_token({
			"photo_id": photo_id,
			"user_id": current_user.id,
			"client_public_key_id": user_public_key.key_id,
			"original_filename": auth_request.filename,
			"file_size": auth_request.file_size,
			"content_type": auth_request.content_type
		})

		log.info(f"Upload authorization created for photo {photo_id}")

		# Get worker URL from environment or default
		worker_url = os.getenv("WORKER_URL", "http://localhost:8056")

		r =  UploadAuthorizationResponse(
			upload_jwt=upload_jwt,
			photo_id=photo_id,
			expires_at=expires_at,
			worker_url=worker_url,
			upload_authorized_at=int(upload_authorized_at.timestamp())
		)
		log.debug(f"Upload authorization response: {r}")

		return r

	except HTTPException:
		raise
	except Exception as e:
		await db.rollback()
		log.error(f"Error creating upload authorization: {e}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to create upload authorization"
		)


	except HTTPException:
		raise
	except Exception as e:
		await db.rollback()
		log.error(f"Error creating upload authorization: {e}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to create upload authorization"
		)

# Cleanup endpoint for orphaned authorized photos
@router.delete("/photos/cleanup-orphaned")
async def cleanup_orphaned_photos(
	request: Request,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Clean up photos that have been authorized but never processed.
	These can accumulate if upload authorization succeeds but the actual upload fails.
	"""
	try:
		from datetime import timedelta

		# Find photos that have been in "authorized" status for more than 1 hour
		cutoff_time = datetime.datetime.now(datetime.timezone.utc) - timedelta(hours=1)

		result = await db.execute(
			select(Photo).where(
				Photo.owner_id == current_user.id,
				Photo.processing_status == "authorized",
				Photo.upload_authorized_at < cutoff_time
			)
		)
		orphaned_photos = result.scalars().all()

		if not orphaned_photos:
			return {
				"message": "No orphaned photos found",
				"cleaned_up_count": 0
			}

		# Delete orphaned photos
		for photo in orphaned_photos:
			await db.delete(photo)

		await db.commit()

		log.info(f"Cleaned up {len(orphaned_photos)} orphaned photos for user {current_user.id}")

		return {
			"message": f"Cleaned up {len(orphaned_photos)} orphaned photos",
			"cleaned_up_count": len(orphaned_photos)
		}

	except Exception as e:
		await db.rollback()
		log.error(f"Error cleaning up orphaned photos for user {current_user.id}: {e}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to cleanup orphaned photos"
		)

# User listing and profile endpoints
@router.get("/users/")
async def get_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional_with_query)
):
    """Get list of all users with their photo counts and latest photos."""
    # Apply rate limiting with optional user context (better limits for authenticated users)
    await general_rate_limiter.enforce_rate_limit(request, 'public_read', current_user)

    try:
        from hidden_content_filters import apply_hidden_content_filters

        # Get users with photo counts and latest photo info
        # First, get photo counts per user
        photo_counts_query = select(
            Photo.owner_id,
            func.count(Photo.id).label('photo_count'),
            func.max(Photo.uploaded_at).label('latest_photo_at')
        ).group_by(Photo.owner_id)

        # Apply hidden content filtering to photo counts
        photo_counts_query = apply_hidden_content_filters(
            photo_counts_query,
            current_user.id if current_user else None,
            'hillview'
        )

        photo_counts_result = await db.execute(photo_counts_query)
        photo_stats = {row.owner_id: {'count': row.photo_count, 'latest_at': row.latest_photo_at}
                      for row in photo_counts_result.all()}

        # Get all active users
        users_query = select(User).where(User.is_active == True)
        users_result = await db.execute(users_query)
        users = users_result.scalars().all()

        # For each user, get their latest photo URL
        user_list = []
        for user in users:
            stats = photo_stats.get(user.id, {'count': 0, 'latest_at': None})

            latest_photo_url = None
            if stats['latest_at']:
                # Get the latest photo for this user
                latest_photo_query = select(Photo).where(
                    Photo.owner_id == user.id,
                    Photo.uploaded_at == stats['latest_at']
                ).limit(1)

                # Apply hidden content filtering
                latest_photo_query = apply_hidden_content_filters(
                    latest_photo_query,
                    current_user.id if current_user else None,
                    'hillview'
                )

                latest_photo_result = await db.execute(latest_photo_query)
                latest_photo = latest_photo_result.scalar_one_or_none()

                if latest_photo and latest_photo.sizes:
                    latest_photo_url = latest_photo.sizes.get('320', {}).get('url')

            user_data = {
                "id": user.id,
                "username": user.username,
                "photo_count": stats['count'],
                "latest_photo_at": stats['latest_at'].isoformat() if stats['latest_at'] else None,
                "latest_photo_url": latest_photo_url
            }
            user_list.append(user_data)

        # Sort by photo count (descending) then by username
        user_list.sort(key=lambda x: (-x['photo_count'], x['username']))

        return user_list

    except Exception as e:
        log.error(f"Error getting users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get users"
        )

@router.get("/users/{user_id}/photos")
async def get_user_photos(
    user_id: str,
    request: Request,
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    limit: int = Query(20, ge=1, le=50, description="Number of photos per page"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional_with_query)
):
    """Get paginated photos for a specific user."""
    # Apply rate limiting with optional user context (better limits for authenticated users)
    await general_rate_limiter.enforce_rate_limit(request, 'public_read', current_user)

    try:
        from hidden_content_filters import apply_hidden_content_filters

        # Verify user exists
        user_query = select(User).where(User.id == user_id, User.is_active == True)
        user_result = await db.execute(user_query)
        user = user_result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Build base query for user's photos with extracted coordinates
        query = select(
            Photo,
            ST_Y(Photo.geometry).label('latitude'),
            ST_X(Photo.geometry).label('longitude')
        ).where(Photo.owner_id == user_id)

        # Apply hidden content filtering
        query = apply_hidden_content_filters(
            query,
            current_user.id if current_user else None,
            'hillview'
        )

        # Apply cursor-based pagination
        if cursor:
            try:
                cursor_date = datetime.datetime.fromisoformat(cursor.replace('Z', '+00:00'))
                query = query.where(Photo.uploaded_at < cursor_date)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid cursor format"
                )

        # Order by upload date (newest first) and apply limit
        query = query.order_by(desc(Photo.uploaded_at)).limit(limit + 1)

        result = await db.execute(query)
        photo_results = result.all()

        # Check if there are more photos
        has_more = len(photo_results) > limit
        if has_more:
            photo_results = photo_results[:-1]  # Remove the extra photo used for pagination check

        # Prepare response
        photo_list = []
        for photo, latitude, longitude in photo_results:
            photo_data = {
                "id": photo.id,
                "original_filename": photo.original_filename,
                "uploaded_at": photo.uploaded_at.isoformat() if photo.uploaded_at else None,
                "captured_at": photo.captured_at.isoformat() if photo.captured_at else None,
                "processing_status": photo.processing_status,
                "latitude": latitude,
                "longitude": longitude,
                "bearing": photo.compass_angle,
                "width": photo.width,
                "height": photo.height,
                "sizes": photo.sizes,
                "description": photo.description
            }
            photo_list.append(photo_data)

        # Get total count for this user
        count_query = select(func.count(Photo.id)).where(Photo.owner_id == user_id)
        count_query = apply_hidden_content_filters(
            count_query,
            current_user.id if current_user else None,
            'hillview'
        )
        count_result = await db.execute(count_query)
        total_count = count_result.scalar()

        # Prepare pagination info
        next_cursor = None
        if has_more and photo_results:
            next_cursor = photo_results[-1][0].uploaded_at.isoformat()

        return {
            "photos": photo_list,
            "user": {
                "id": user.id,
                "username": user.username
            },
            "pagination": {
                "next_cursor": next_cursor,
                "has_more": has_more
            },
            "counts": {
                "total": total_count
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error getting user photos: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user photos"
        )

# TODO: Admin endpoints temporarily disabled until role system is working
# Will be re-enabled after database migration and proper role handling
