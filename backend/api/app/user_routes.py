import datetime
import os
from typing import Optional
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_
from pydantic import BaseModel
import requests

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
from .rate_limiter import auth_rate_limiter, check_auth_rate_limit
from .security_utils import validate_username, validate_email, validate_oauth_redirect_uri

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
        # Record failed attempt for rate limiting
        await auth_rate_limiter.record_failed_attempt(identifier)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Clear failed attempts on successful login
    await auth_rate_limiter.clear_failed_attempts(identifier)
    
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

@router.post("/auth/oauth", response_model=Token)
async def oauth_login(
        oauth_data: UserOAuth,
    db: AsyncSession = Depends(get_db)
):
    # Validate provider
    provider = oauth_data.provider
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported OAuth provider: {provider}"
        )
    
    provider_config = OAUTH_PROVIDERS[provider]
    
    # Validate redirect URI to prevent open redirect attacks
    redirect_uri = oauth_data.redirect_uri or provider_config["redirect_uri"]
    if redirect_uri:
        # Define allowed domains for OAuth redirects
        allowed_domains = {'localhost', '127.0.0.1', 'hillview.ueueeu.eu'}  # Add your production domain
        redirect_uri = validate_oauth_redirect_uri(redirect_uri, allowed_domains)
    
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
    
    # GitHub returns different format based on Accept header
    headers = {}
    if provider == "github":
        headers["Accept"] = "application/json"
        
    token_response = requests.post(provider_config["token_url"], data=token_data, headers=headers)
    if token_response.status_code != 200:
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
        "expires_at": expires
    }

@router.get("/auth/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user

class UserSettingsUpdate(BaseModel):
    auto_upload_enabled: Optional[bool] = None
    auto_upload_folder: Optional[str] = None

@router.put("/auth/settings", response_model=UserOut)
async def update_user_settings(
    settings: UserSettingsUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    if settings.auto_upload_enabled is not None:
        current_user.auto_upload_enabled = settings.auto_upload_enabled
    if settings.auto_upload_folder is not None:
        current_user.auto_upload_folder = settings.auto_upload_folder
    
    await db.commit()
    await db.refresh(current_user)
    return current_user