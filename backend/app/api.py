import asyncio
import datetime
import shutil
from pathlib import Path
from typing import List, Optional
import os
import json
import requests
import logging
from fastapi import FastAPI, Query, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_
import aiofiles
from pydantic import BaseModel
from dotenv import load_dotenv

from .database import get_db, Base, engine
from .models import User, Photo
from .auth import (
    authenticate_user, create_access_token, get_current_active_user,
    get_password_hash, Token, UserCreate, UserLogin, UserOut, UserOAuth,
    OAUTH_PROVIDERS, ACCESS_TOKEN_EXPIRE_MINUTES
)

load_dotenv()
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

TOKEN = open(os.path.expanduser(os.environ['MAPILLARY_CLIENT_TOKEN_FILE'])).read().strip()
url = "https://graph.mapillary.com/images"

clients = {}

app = FastAPI(title="Hillview API", description="API for Hillview application")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5000", "http://localhost:8089"],  # Add your frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create upload directories
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
THUMBNAIL_DIR = UPLOAD_DIR / "thumbnails"
UPLOAD_DIR.mkdir(exist_ok=True)
THUMBNAIL_DIR.mkdir(exist_ok=True)

# Initialize database
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        # Uncomment to create tables on startup (for development)
        # await conn.run_sync(Base.metadata.create_all)
        pass

# Authentication routes
@app.post("/api/auth/register", response_model=UserOut)
async def register_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check if username or email already exists
    result = await db.execute(
        select(User).where(
            or_(User.username == user.username, User.email == user.email)
        )
    )
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )
    
    # Create new user
    hashed_password = get_password_hash(user.password)
    db_user = User(
        email=user.email,
        username=user.username,
        hashed_password=hashed_password
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

@app.post("/api/auth/token", response_model=Token)
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

@app.post("/api/auth/oauth", response_model=Token)
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

@app.get("/api/auth/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user

@app.put("/api/auth/settings", response_model=UserOut)
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

@app.get("/api/photos", response_model=List[PhotoResponse])
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
    photo_id: str,
    db: AsyncSession
):
    """Background task to process uploaded photos"""
    # Here you would extract EXIF data, create thumbnails, etc.
    # For now, just create a simple thumbnail
    try:
        # This is a placeholder - in a real app you'd use PIL or similar
        # to create proper thumbnails and extract EXIF data
        shutil.copy(file_path, thumbnail_path)
        
        # Update the photo record with extracted data
        async with db.begin():
            result = await db.execute(select(Photo).where(Photo.id == photo_id))
            photo = result.scalars().first()
            if photo:
                # Here you would set latitude, longitude, etc. from EXIF
                photo.thumbnail_path = thumbnail_path
                await db.commit()
    except Exception as e:
        log.error(f"Error processing photo {photo_id}: {e}")

@app.post("/api/photos/upload", response_model=PhotoResponse)
async def upload_photo(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    description: str = Form(None),
    is_public: bool = Form(True),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # Create a unique filename
    file_ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{current_user.id}{file_ext}"
    file_path = UPLOAD_DIR / unique_filename
    thumbnail_path = THUMBNAIL_DIR / unique_filename
    
    # Save the uploaded file
    async with aiofiles.open(file_path, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)
    
    # Create photo record
    photo = Photo(
        filename=file.filename,
        filepath=str(file_path),
        description=description,
        is_public=is_public,
        owner_id=current_user.id
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    
    # Process the photo in the background
    background_tasks.add_task(
        process_photo,
        str(file_path),
        str(thumbnail_path),
        photo.id,
        db
    )
    
    return photo

@app.delete("/api/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
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

@app.get("/api/photos/{photo_id}/thumbnail")
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

@app.get("/api/mapillary")
async def get_images(top_left_lat: float = Query(..., description="Top left latitude"),
               top_left_lon: float = Query(..., description="Top left longitude"),
               bottom_right_lat: float = Query(..., description="Bottom right latitude"),
               bottom_right_lon: float = Query(..., description="Bottom right longitude"),
               client_id: str = Query(..., description="Client ID")):


    request_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S.%f")
    now = datetime.datetime.now()
    if client_id in clients:
        while True:
            now = datetime.datetime.now()
            if now - clients[client_id] < datetime.timedelta(seconds=1):
                log.info(f"Client {client_id} request {request_id} rate limited")
                await asyncio.sleep(1)
            else:
                break
    clients[client_id] = now

    params = {
        "limit": 200,
        "bbox": ",".join(map(str, [round(top_left_lon, 7), round(bottom_right_lat,7), round(bottom_right_lon,7), round(top_left_lat,7)])),
        "fields": "id,geometry,compass_angle,thumb_1024_url,computed_rotation,computed_compass_angle,computed_altitude,captured_at,is_pano",
        "access_token": TOKEN,
    }
    resp = requests.get(url, params=params)
    rr = resp.json()
    #log.debug(json.dumps(rr, indent=2))
    if 'data' in rr:
        sorted_data = sorted(rr['data'], key=lambda x: x['compass_angle'])
        log.info(f"Found {len(sorted_data)} images for client {client_id} request {request_id}")
        log.info(f"paging: {rr.get('paging')}")
        return sorted_data
    else:
        log.error(f"Error: {rr}")
        return []
