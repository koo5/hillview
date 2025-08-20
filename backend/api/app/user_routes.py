import datetime
import os
from typing import Optional
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_
from pydantic import BaseModel
import requests
from urllib.parse import urlencode, quote

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import User
from .auth import (
    authenticate_user, create_access_token, get_current_active_user,
    get_password_hash, Token, UserCreate, UserLogin, UserOut, UserOAuth,
    OAUTH_PROVIDERS, ACCESS_TOKEN_EXPIRE_MINUTES,
    blacklist_token, get_current_user
)
from .rate_limiter import auth_rate_limiter, check_auth_rate_limit, rate_limit_user_profile
from .security_utils import validate_username, validate_email, validate_oauth_redirect_uri
from .security_audit import security_audit

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["users"])

# Authentication routes
@router.post("/auth/register", response_model=UserOut)
async def register_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    # Validate input
    validated_username = validate_username(user.username)
    validated_email = validate_email(user.email)
    
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
        # Validate password strength (min 8 chars)
        if len(user.password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters long"
            )
        
        hashed_password = get_password_hash(user.password)
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
        data={"sub": user.username, "user_id": user.id},
        expires_delta=datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_at": expires
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

@router.get("/auth/oauth-redirect")
async def oauth_redirect(
    provider: str,
    redirect_uri: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Initiate OAuth flow with proper redirect URI for both web and mobile
    """
    # Rate limit OAuth redirects to prevent abuse
    identifier = auth_rate_limiter.get_identifier(request)
    if not await auth_rate_limiter.check_rate_limit(identifier, max_requests=20, window_seconds=300):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OAuth requests. Try again later.",
            headers={"Retry-After": "300"}
        )
    
    # Validate and sanitize redirect URI  
    # Define allowed domains for OAuth redirects (include mobile deep links)
    if redirect_uri.startswith("com.hillview://"):
        # Mobile deep link - allow it
        validated_redirect_uri = redirect_uri
    else:
        # Web redirect - validate against allowed domains
        allowed_domains = {
            'localhost:8212', 'localhost', '127.0.0.1', 'localhost:8055', 
            'hillview.cz', 'api.hillview.cz', 'tauri.localhost'
        }
        try:
            validated_redirect_uri = validate_oauth_redirect_uri(redirect_uri, allowed_domains)
        except Exception as e:
            await security_audit.log_event(
                db=db,
                event_type="oauth_redirect_invalid",
                ip_address=request.client.host if request.client else None,
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
    # For mobile: use deep link, for web: use frontend callback
    if validated_redirect_uri.startswith("com.hillview://"):
        # Mobile flow: OAuth provider should redirect to API server callback
        server_callback_uri = f"{request.base_url}auth/oauth-callback"
        log.info(f"Mobile flow detected - Server callback URI: {server_callback_uri}")
    else:
        # Web flow: OAuth provider should redirect to frontend callback
        # Extract frontend origin from the redirect_uri
        from urllib.parse import urlparse
        parsed = urlparse(validated_redirect_uri)
        frontend_origin = f"{parsed.scheme}://{parsed.netloc}"
        server_callback_uri = f"{frontend_origin}/oauth/callback"
        log.info(f"Web flow detected - Frontend origin: {frontend_origin}, Server callback URI: {server_callback_uri}")
    
    # Encode both provider and final destination in state
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
    identifier = auth_rate_limiter.get_identifier(request)
    if not await auth_rate_limiter.check_rate_limit(identifier, max_requests=30, window_seconds=300):
        await security_audit.log_event(
            db=db,
            event_type="oauth_callback_rate_limited",
            ip_address=request.client.host if request.client else None,
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
    
    # Extract provider and final destination from state
    if state and ":" in state:
        provider, final_redirect_uri = state.split(":", 1)
    else:
        # Fallback to default if state is malformed
        provider = "google"
        final_redirect_uri = state
    
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=400, detail="Invalid OAuth provider")
    
    provider_config = OAUTH_PROVIDERS[provider]
    
    # Exchange code for JWT using existing logic
    # Use the same redirect URI logic as the redirect endpoint
    if final_redirect_uri and final_redirect_uri.startswith("com.hillview://"):
        # Mobile flow: used API server callback
        server_callback_uri = f"{request.base_url}auth/oauth-callback"
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
        expires_at = jwt_result["expires_at"]
        user_info = jwt_result.get("user_info", {})
        
        # Log successful OAuth login
        await security_audit.log_event(
            db=db,
            event_type="oauth_login_success",
            user_identifier=user_info.get("username"),
            ip_address=request.client.host if request.client else None,
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
            ip_address=request.client.host if request.client else None,
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
    
    # Detect if this is a mobile app request
    if final_redirect_uri and final_redirect_uri.startswith("com.hillview://"):
        # Mobile app: deep link back with token
        callback_url = f"{final_redirect_uri}?token={jwt_token}&expires_at={expires_at.isoformat()}"
        log.info(f"Mobile OAuth callback, redirecting to: {callback_url}")
        return RedirectResponse(callback_url)
    else:
        # Web app: existing behavior (redirect to dashboard)
        # Note: For web app, you might want to set cookies here
        log.info("Web OAuth callback, redirecting to dashboard")
        response = RedirectResponse("/dashboard")
        response.set_cookie(
            "auth_token", 
            jwt_token, 
            httponly=True,
            secure=True,
            samesite="lax",
            expires=expires_at
        )
        return response

@router.post("/auth/oauth", response_model=Token)
async def oauth_login(
        oauth_data: UserOAuth,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Public OAuth endpoint for API clients"""
    # Rate limit OAuth API endpoint
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
        allowed_domains = {'localhost:8212', 'localhost', '127.0.0.1', 'localhost:8055', 'hillview.ueueeu.eu'}
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
    
    # Create access token
    access_token, expires = create_access_token(
        data={"sub": user.username, "user_id": user.id},
        expires_delta=datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_at": expires,
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
        "auto_upload_enabled": current_user.auto_upload_enabled,
        "auto_upload_folder": current_user.auto_upload_folder
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
        # TODO: Add cascading delete for user's photos and other related data
        # For now, we'll just delete the user record
        # In a production app, you'd want to:
        # 1. Delete all user's photos from filesystem
        # 2. Delete all user's data from database (photos, sessions, etc.)
        # 3. Optionally anonymize instead of hard delete for data integrity
        
        await db.delete(current_user)
        await db.commit()
        
        return {"message": "Account successfully deleted"}
    except Exception as e:
        await db.rollback()
        log.error(f"Error deleting user account: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete account")

class UserSettingsUpdate(BaseModel):
    auto_upload_enabled: Optional[bool] = None
    auto_upload_folder: Optional[str] = None

@router.put("/auth/settings", response_model=UserOut)
async def update_user_settings(
    request: Request,
    settings: UserSettingsUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # Apply user profile rate limiting
    await rate_limit_user_profile(request, current_user.id)
    
    if settings.auto_upload_enabled is not None:
        current_user.auto_upload_enabled = settings.auto_upload_enabled
    if settings.auto_upload_folder is not None:
        current_user.auto_upload_folder = settings.auto_upload_folder
    
    await db.commit()
    await db.refresh(current_user)
    return current_user

# TODO: Admin endpoints temporarily disabled until role system is working
# Will be re-enabled after database migration and proper role handling