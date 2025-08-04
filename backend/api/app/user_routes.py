import datetime
import os
import shutil
from pathlib import Path
from typing import List, Optional
import logging
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_
import aiofiles
from pydantic import BaseModel
import requests

from .database import get_db
from .models import User, Photo
from .auth import (
    authenticate_user, create_access_token, get_current_active_user,
    get_password_hash, Token, UserCreate, UserLogin, UserOut, UserOAuth,
    OAUTH_PROVIDERS, ACCESS_TOKEN_EXPIRE_MINUTES
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["users"])

# Create upload directories
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(exist_ok=True)

# Authentication routes
@router.post("/auth/register", response_model=UserOut)
async def register_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    log.info(f"Registration attempt for user: {user.username}, email: {user.email}")
    
    # Check if username or email already exists
    result = await db.execute(
        select(User).where(
            or_(User.username == user.username, User.email == user.email)
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
        hashed_password = get_password_hash(user.password)
        db_user = User(
            email=user.email,
            username=user.username,
            hashed_password=hashed_password
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        log.info(f"User registered successfully: {user.username}, ID: {db_user.id}")
        return db_user
    except Exception as e:
        log.error(f"Error during user registration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )

@router.post("/auth/token", response_model=Token)
async def login_for_access_token(
        form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
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

@router.post("/auth/oauth", response_model=Token)
async def oauth_login(
        oauth_data: UserOAuth,
    db: AsyncSession = Depends(get_db)
):
    provider = oauth_data.provider
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported OAuth provider: {provider}"
        )
    
    provider_config = OAUTH_PROVIDERS[provider]
    
    # Exchange code for token (implementation depends on provider)
    # This is a simplified example
    token_data = {
        "client_id": provider_config["client_id"],
        "client_secret": provider_config["client_secret"],
        "code": oauth_data.code,
        "redirect_uri": oauth_data.redirect_uri or provider_config["redirect_uri"],
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

@router.put("/auth/settings", response_model=UserOut)
async def update_user_settings(
    auto_upload_enabled: bool = Form(...),
    auto_upload_folder: str = Form(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    current_user.auto_upload_enabled = auto_upload_enabled
    if auto_upload_folder:
        current_user.auto_upload_folder = auto_upload_folder
    
    await db.commit()
    await db.refresh(current_user)
    return current_user

# Photo management routes
class PhotoResponse(BaseModel):
    id: str
    filename: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    compass_angle: Optional[float] = None
    captured_at: Optional[datetime.datetime] = None
    uploaded_at: datetime.datetime
    thumbnail_url: Optional[str] = None
    is_public: bool
    
    class Config:
        from_attributes = True

@router.get("/photos", response_model=List[PhotoResponse])
async def get_user_photos(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Photo).where(Photo.owner_id == current_user.id)
    )
    photos = result.scalars().all()
    return photos

async def process_photo(
    file_path: str,
    thumbnail_path: str,
    photo_id: str
):
    """Background task to process uploaded photos"""
    # Here you would extract EXIF data, create thumbnails, etc.
    # For now, just create a simple thumbnail
    try:
        # This is a placeholder - in a real app you'd use PIL or similar
        # to create proper thumbnails and extract EXIF data
        shutil.copy(file_path, thumbnail_path)
        
        # Create a new database session for the background task
        from .database import SessionLocal
        async with SessionLocal() as db:
            # Update the photo record with extracted data
            result = await db.execute(select(Photo).where(Photo.id == photo_id))
            photo = result.scalars().first()
            if photo:
                # Here you would set latitude, longitude, etc. from EXIF
                photo.thumbnail_path = thumbnail_path
                await db.commit()
    except Exception as e:
        log.error(f"Error processing photo {photo_id}: {e}")

@router.delete("/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_photo(
    photo_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.owner_id == current_user.id)
    )
    photo = result.scalars().first()
    
    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found or you don't have permission to delete it"
        )
    
    # Delete the files
    if os.path.exists(photo.filepath):
        os.remove(photo.filepath)
    if photo.thumbnail_path and os.path.exists(photo.thumbnail_path):
        os.remove(photo.thumbnail_path)
    
    # Delete the database record
    await db.delete(photo)
    await db.commit()
    
    return None

@router.get("/photos/{photo_id}/thumbnail")
async def get_photo_thumbnail(
    photo_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Photo).where(
            (Photo.id == photo_id) & 
            ((Photo.owner_id == current_user.id) | (Photo.is_public == True))
        )
    )
    photo = result.scalars().first()
    
    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found or you don't have permission to view it"
        )
    
    # If thumbnail exists, return it
    if photo.thumbnail_path and os.path.exists(photo.thumbnail_path):
        return FileResponse(photo.thumbnail_path)
    
    # If no thumbnail, return the original image
    if os.path.exists(photo.filepath):
        return FileResponse(photo.filepath)
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Photo file not found"
    )