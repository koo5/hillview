import asyncio
import datetime
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
import os
import json
import requests
import logging
from fastapi import FastAPI, Query, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_
import aiofiles
from pydantic import BaseModel
from dotenv import load_dotenv

from .database import get_db, Base, engine, SessionLocal
from .models import User, Photo, CachedRegion, MapillaryPhotoCache
from .auth import (
    authenticate_user, create_access_token, get_current_active_user,
    get_password_hash, Token, UserCreate, UserLogin, UserOut, UserOAuth,
    OAUTH_PROVIDERS, ACCESS_TOKEN_EXPIRE_MINUTES
)
from .cache_service import MapillaryCacheService

load_dotenv()
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

TOKEN = open(os.path.expanduser(os.environ['MAPILLARY_CLIENT_TOKEN_FILE'])).read().strip()
url = "https://graph.mapillary.com/images"

# Configuration
DISABLE_MAPILLARY_CACHE = os.getenv("DISABLE_MAPILLARY_CACHE", "false").lower() in ("true", "1", "yes")

clients = {}

app = FastAPI(title="Hillview API", description="API for Hillview application")

# Add exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    log.error(f"Unhandled exception: {exc}")
    log.error(traceback.format_exc())
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": str(exc)},
    )

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5000", "http://localhost:8089"],  # Add your frontend URLs
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
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
        # Create tables on startup
        await conn.run_sync(Base.metadata.create_all)

# Authentication routes
@app.post("/api/auth/register", response_model=UserOut)
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
#
# @app.post("/api/photos/upload", response_model=PhotoResponse)
# async def upload_photo(
#     background_tasks: BackgroundTasks,
#     file: UploadFile = File(...),
#     description: str = Form(None),
#     is_public: bool = Form(True),
#     current_user: User = Depends(get_current_active_user),
#     db: AsyncSession = Depends(get_db)
# ):
#     # Create a unique filename
#     file_ext = os.path.splitext(file.filename)[1]
#     unique_filename = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{current_user.id}{file_ext}"
#     file_path = UPLOAD_DIR / unique_filename
#     thumbnail_path = THUMBNAIL_DIR / unique_filename
#
#     # Save the uploaded file
#     async with aiofiles.open(file_path, 'wb') as out_file:
#         content = await file.read()
#         await out_file.write(content)
#
#     # Create photo record
#     photo = Photo(
#         filename=file.filename,
#         filepath=str(file_path),
#         description=description,
#         is_public=is_public,
#         owner_id=current_user.id
#     )
#     db.add(photo)
#     await db.commit()
#     await db.refresh(photo)
#
#     # Process the photo in the background
#     background_tasks.add_task(
#         process_photo,
#         str(file_path),
#         str(thumbnail_path),
#         photo.id,
#         db
#     )
#
#     return photo

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

@app.get("/api/debug")
async def debug_endpoint():
    """Debug endpoint to check if the API is working properly"""
    return {"status": "ok", "message": "API is working properly"}

async def fetch_mapillary_data(
    top_left_lat: float,
    top_left_lon: float,
    bottom_right_lat: float,
    bottom_right_lon: float,
    cursor: Optional[str] = None
) -> Dict[str, Any]:
    """Fetch data from Mapillary API with optional cursor for pagination"""
    
    params = {
        "limit": 200,
        "bbox": ",".join(map(str, [round(top_left_lon, 7), round(bottom_right_lat,7), round(bottom_right_lon,7), round(top_left_lat,7)])),
        "fields": "id,geometry,compass_angle,thumb_1024_url,computed_rotation,computed_compass_angle,computed_altitude,captured_at,is_pano",
        "access_token": TOKEN,
    }
    
    if cursor:
        params["after"] = cursor
    
    resp = requests.get(url, params=params)
    rr = resp.json()
    
    if 'data' in rr:
        return {
            "data": rr['data'],
            "paging": rr.get('paging', {})
        }
    else:
        log.error(f"Mapillary API error: {rr}")
        return {"data": [], "paging": {}}

async def populate_cache_background(
    cache_service: MapillaryCacheService,
    region: CachedRegion,
    top_left_lat: float,
    top_left_lon: float,
    bottom_right_lat: float,
    bottom_right_lon: float
):
    """Background task to populate cache for a region"""
    
    try:
        cursor = region.last_cursor
        total_cached = 0
        
        while region.has_more:
            # Fetch data from Mapillary
            mapillary_response = await fetch_mapillary_data(
                top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon, cursor
            )
            
            photos_data = mapillary_response["data"]
            paging = mapillary_response["paging"]
            
            if not photos_data:
                break
            
            # Cache the photos
            cached_count = await cache_service.cache_photos(photos_data, region)
            total_cached += cached_count
            
            # Update cursor for next iteration
            if paging.get("next"):
                cursor = paging.get("cursors", {}).get("after")
                if cursor:
                    await cache_service.update_region_cursor(region, cursor)
                else:
                    break
            else:
                # No more data
                await cache_service.mark_region_complete(region, cursor)
                break
        
        log.info(f"Background cache population completed for region {region.id}: {total_cached} photos cached")
        
    except Exception as e:
        log.error(f"Error in background cache population: {str(e)}")

@app.get("/api/mapillary")
async def stream_mapillary_images(
    top_left_lat: float = Query(..., description="Top left latitude"),
    top_left_lon: float = Query(..., description="Top left longitude"),
    bottom_right_lat: float = Query(..., description="Bottom right latitude"),
    bottom_right_lon: float = Query(..., description="Bottom right longitude"),
    client_id: str = Query(..., description="Client ID")
):
    """Stream Mapillary images with Server-Sent Events"""
    
    async def generate_stream():
        request_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S.%f")
        log.info(f"Stream request {request_id} from client {client_id} (cache_disabled={DISABLE_MAPILLARY_CACHE})")
        
        total_live_photos = []  # Initialize here to avoid scope issues
        
        try:
            if DISABLE_MAPILLARY_CACHE:
                # Non-cached mode - stream directly from Mapillary API
                log.info(f"Mapillary cache disabled, streaming directly from API for request {request_id}")
                
                # Send cache status indicating no cache
                yield f"data: {json.dumps({'type': 'cache_status', 'cache_disabled': True, 'uncached_regions': 1})}\n\n"
                
                # Rate limiting
                now = datetime.datetime.now()
                if client_id in clients:
                    while True:
                        now = datetime.datetime.now()
                        if now - clients[client_id] < datetime.timedelta(seconds=1):
                            await asyncio.sleep(1)
                        else:
                            break
                clients[client_id] = now
                
                # Stream all pages directly from Mapillary
                cursor = None
                while True:
                    mapillary_response = await fetch_mapillary_data(
                        top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon, cursor
                    )
                    
                    photos_data = mapillary_response["data"]
                    paging = mapillary_response["paging"]
                    
                    if not photos_data:
                        break
                    
                    total_live_photos.extend(photos_data)
                    
                    # Stream this batch
                    sorted_batch = sorted(photos_data, key=lambda x: x.get('compass_angle', 0))
                    yield f"data: {json.dumps({'type': 'live_photos_batch', 'photos': sorted_batch, 'region': 'direct'})}\n\n"
                    
                    # Check for more pages
                    if paging.get("next"):
                        cursor = paging.get("cursors", {}).get("after")
                        if cursor:
                            # Rate limit between pages
                            await asyncio.sleep(1)
                        else:
                            break
                    else:
                        break
                
                # Send completion
                yield f"data: {json.dumps({'type': 'stream_complete', 'total_live_photos': len(total_live_photos)})}\n\n"
                
            else:
                # Cached mode - use cache service
                async with SessionLocal() as db:
                    cache_service = MapillaryCacheService(db)
                    
                    # Send initial response with cached data
                    cached_photos = await cache_service.get_cached_photos_in_bbox(
                        top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon
                    )
                
                if cached_photos:
                    sorted_cached = sorted(cached_photos, key=lambda x: x.get('compass_angle', 0))
                    yield f"data: {json.dumps({'type': 'cached_photos', 'photos': sorted_cached, 'count': len(sorted_cached)})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'cached_photos', 'photos': [], 'count': 0})}\n\n"
                
                # Calculate uncached regions
                uncached_regions = await cache_service.calculate_uncached_regions(
                    top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon
                )
                
                yield f"data: {json.dumps({'type': 'cache_status', 'uncached_regions': len(uncached_regions)})}\n\n"
                
                # Stream live data from uncached regions
                if uncached_regions:
                    # Rate limiting
                    now = datetime.datetime.now()
                    if client_id in clients:
                        while True:
                            now = datetime.datetime.now()
                            if now - clients[client_id] < datetime.timedelta(seconds=1):
                                await asyncio.sleep(1)
                            else:
                                break
                    clients[client_id] = now
                
                # total_live_photos already initialized above
                
                for region_bbox in uncached_regions:
                    try:
                        # Create cache region
                        region = await cache_service.create_cached_region(
                            region_bbox[0], region_bbox[1], region_bbox[2], region_bbox[3]
                        )
                    
                        cursor = None
                        region_photos = []
                    
                        # Stream all pages for this region
                        while True:
                            mapillary_response = await fetch_mapillary_data(
                                region_bbox[0], region_bbox[1], region_bbox[2], region_bbox[3], cursor
                            )
                            
                            photos_data = mapillary_response["data"]
                            paging = mapillary_response["paging"]
                            
                            if not photos_data:
                                break
                            
                            region_photos.extend(photos_data)
                            total_live_photos.extend(photos_data)
                            
                            # Cache the photos
                            await cache_service.cache_photos(photos_data, region)
                            
                            # Stream this batch
                            sorted_batch = sorted(photos_data, key=lambda x: x.get('compass_angle', 0))
                            yield f"data: {json.dumps({'type': 'live_photos_batch', 'photos': sorted_batch, 'region': region.id})}\n\n"
                            
                            # Check for more pages
                            if paging.get("next"):
                                cursor = paging.get("cursors", {}).get("after")
                                if cursor:
                                    await cache_service.update_region_cursor(region, cursor)
                                else:
                                    break
                            else:
                                break
                    
                        # Mark region as complete
                        await cache_service.mark_region_complete(region, cursor)
                        
                        yield f"data: {json.dumps({'type': 'region_complete', 'region': region.id, 'photos_count': len(region_photos)})}\n\n"
                        
                    except Exception as e:
                        log.error(f"Error streaming region {region_bbox}: {str(e)}")
                        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            
            # Send final summary
            yield f"data: {json.dumps({'type': 'stream_complete', 'total_live_photos': len(total_live_photos)})}\n\n"
        
        except Exception as e:
            log.error(f"Stream error: {str(e)}")
            yield f"data: {json.dumps({'type': 'error', 'message': f'Stream error: {str(e)}'})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

@app.get("/api/mapillary/stats")
async def get_cache_stats(db: AsyncSession = Depends(get_db)):
    """Get cache statistics"""
    cache_service = MapillaryCacheService(db)
    return await cache_service.get_cache_stats()
