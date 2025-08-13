import asyncio
import datetime
import json
import os
from typing import Optional, Dict, Any
import requests
import logging
from fastapi import APIRouter, Query, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db, SessionLocal
from common.models import CachedRegion, MapillaryPhotoCache
from .cache_service import MapillaryCacheService

load_dotenv()
log = logging.getLogger(__name__)

# Lazy load token to avoid crash on import
TOKEN = None
url = "https://graph.mapillary.com/images"

def get_mapillary_token():
    global TOKEN
    if TOKEN is None:
        token_file = os.environ.get('MAPILLARY_CLIENT_TOKEN_FILE')
        if not token_file:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="MAPILLARY_CLIENT_TOKEN_FILE environment variable not set"
            )
        try:
            TOKEN = open(os.path.expanduser(token_file)).read().strip()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to read Mapillary token file: {str(e)}"
            )
    return TOKEN

# Configuration
ENABLE_MAPILLARY_CACHE = os.getenv("ENABLE_MAPILLARY_CACHE", "false").lower() in ("true", "1", "yes")
MAX_PHOTOS_PER_REQUEST = int(os.getenv("MAX_MAPILLARY_PHOTOS", "3000"))

clients = {}

router = APIRouter(prefix="/api/mapillary", tags=["mapillary"])

async def fetch_mapillary_data(
    top_left_lat: float,
    top_left_lon: float,
    bottom_right_lat: float,
    bottom_right_lon: float,
    cursor: Optional[str] = None
) -> Dict[str, Any]:
    """Fetch data from Mapillary API with optional cursor for pagination"""
    
    params = {
        "limit": 3000,
        "bbox": ",".join(map(str, [round(top_left_lon, 7), round(bottom_right_lat,7), round(bottom_right_lon,7), round(top_left_lat,7)])),
        "fields": "id,geometry,compass_angle,thumb_1024_url,computed_rotation,computed_compass_angle,computed_altitude,captured_at,is_pano",
        "access_token": get_mapillary_token(),
    }
    
    if cursor:
        params["after"] = cursor
    
    # Make API call with detailed error handling
    try:
        log.info(f"Making Mapillary API call to {url} with params: {params}")
        resp = requests.get(url, params=params, timeout=30)
        log.info(f"Mapillary API response status: {resp.status_code}")
        resp.raise_for_status()
        rr = resp.json()
        log.info(f"Mapillary API returned {len(rr.get('data', []))} photos")
    except requests.exceptions.Timeout as e:
        log.error(f"Mapillary API request timed out: {e}")
        return {"data": [], "paging": {}}
    except requests.exceptions.HTTPError as e:
        log.error(f"Mapillary API HTTP error {resp.status_code}: {e}")
        try:
            error_body = resp.text
            log.error(f"Mapillary API error response body: {error_body}")
        except:
            pass
        return {"data": [], "paging": {}}
    except requests.exceptions.RequestException as e:
        log.error(f"Mapillary API request failed: {e}")
        return {"data": [], "paging": {}}
    except Exception as e:
        log.error(f"Unexpected error in Mapillary API call: {e}")
        return {"data": [], "paging": {}}
    
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
            # Check if we've already reached reasonable limit before making API call
            if total_cached >= MAX_PHOTOS_PER_REQUEST:
                log.info(f"Background cache: Photo limit of {MAX_PHOTOS_PER_REQUEST} reached, stopping new API calls")
                break
                
            # Fetch data from Mapillary
            mapillary_response = await fetch_mapillary_data(
                top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon, cursor
            )
            
            photos_data = mapillary_response["data"]
            paging = mapillary_response["paging"]
            
            if not photos_data:
                break
            
            # Cache all photos from this batch (no truncation)
            cached_count = await cache_service.cache_photos(photos_data, region)
            total_cached += cached_count
            
            # If this batch put us over the limit, cache it all but stop making new requests
            if total_cached >= MAX_PHOTOS_PER_REQUEST:
                log.info(f"Background cache: Photo limit reached after caching {total_cached} photos, stopping API calls")
                break
            
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

@router.get("")
async def stream_mapillary_images(
    top_left_lat: float = Query(..., description="Top left latitude"),
    top_left_lon: float = Query(..., description="Top left longitude"),
    bottom_right_lat: float = Query(..., description="Bottom right latitude"),
    bottom_right_lon: float = Query(..., description="Bottom right longitude"),
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_db)
):
    """Stream Mapillary images with Server-Sent Events"""
    log.info(f"EventSource connection initiated by client {client_id} for bbox: ({top_left_lat}, {top_left_lon}) to ({bottom_right_lat}, {bottom_right_lon})")
    
    async def generate_stream(db_session: AsyncSession):
        request_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S.%f")
        log.info(f"Stream generator started for request {request_id} from client {client_id} (cache_enabled={ENABLE_MAPILLARY_CACHE})")
        
        # Track all photos (cached + live) to avoid memory issues
        total_photo_count = 0
        cached_photo_count = 0
        
        try:
            if not ENABLE_MAPILLARY_CACHE:
                # Non-cached mode - stream directly from Mapillary API
                log.info(f"Mapillary cache disabled, streaming directly from API for request {request_id}")
                
                # Cache disabled - proceeding with live API calls
                
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
                    
                    # Apply photo limit
                    original_batch_size = len(photos_data)
                    if total_photo_count + len(photos_data) > MAX_PHOTOS_PER_REQUEST:
                        # Truncate batch to stay within limit
                        remaining_slots = MAX_PHOTOS_PER_REQUEST - total_photo_count
                        photos_data = photos_data[:remaining_slots]
                        log.info(f"Photo limit reached, truncating batch from {original_batch_size} to {remaining_slots} photos")
                    else:
                        log.info(f"Streaming {len(photos_data)} live photos directly from Mapillary API")
                    
                    total_photo_count += len(photos_data)
                    log.info(f"Total photos streamed so far: {total_photo_count}/{MAX_PHOTOS_PER_REQUEST}")
                    
                    # Stream this batch
                    sorted_batch = sorted(photos_data, key=lambda x: x.get('compass_angle', 0))
                    # Region has more data if API indicates more pages available (regardless of our limit)
                    region_has_next = bool(paging.get("next"))
                    yield f"data: {json.dumps({'type': 'photos', 'photos': sorted_batch, 'hasNext': region_has_next})}\n\n"
                    
                    # Check if we've reached the photo limit
                    if total_photo_count >= MAX_PHOTOS_PER_REQUEST:
                        log.info(f"Photo limit of {MAX_PHOTOS_PER_REQUEST} reached, stopping fetch")
                        break
                    
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
                log.info(f"Direct stream complete for client {client_id}: {total_photo_count} total photos streamed from Mapillary API")
                yield f"data: {json.dumps({'type': 'stream_complete', 'total_live_photos': total_photo_count, 'total_cached_photos': 0, 'total_all_photos': total_photo_count})}\n\n"
                
            else:
                # Cached mode - use cache service
                cache_service = MapillaryCacheService(db_session)
                
                # Send initial response with cached data
                cached_photos = await cache_service.get_cached_photos_in_bbox(
                    top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon
                )
                
                if cached_photos:
                    log.info(f"Cache hit: Found {len(cached_photos)} cached photos for bbox")
                    sorted_cached = sorted(cached_photos, key=lambda x: x.get('compass_angle', 0))
                    
                    # Apply photo limit to cached photos
                    if len(sorted_cached) > MAX_PHOTOS_PER_REQUEST:
                        sorted_cached = sorted_cached[:MAX_PHOTOS_PER_REQUEST]
                        log.info(f"Limiting cached photos from {len(cached_photos)} to {MAX_PHOTOS_PER_REQUEST} due to MAX_PHOTOS_PER_REQUEST")
                    
                    cached_photo_count = len(sorted_cached)
                    log.info(f"Streaming {cached_photo_count} cached photos to client {client_id}")
                    # For cached photos from complete cache, region is exhausted if we have fewer than limit
                    # (assuming cache service marks regions as complete when no more data available)
                    region_exhausted = len(cached_photos) < MAX_PHOTOS_PER_REQUEST
                    yield f"data: {json.dumps({'type': 'photos', 'photos': sorted_cached, 'hasNext': not region_exhausted})}\n\n"
                else:
                    cached_photo_count = 0
                    log.info(f"Cache miss: No cached photos found for bbox")
                    log.info(f"Streaming 0 cached photos to client {client_id}")
                    # No cached photos means we haven't checked this region yet
                    yield f"data: {json.dumps({'type': 'photos', 'photos': [], 'hasNext': True})}\n\n"
                
                # Calculate uncached regions
                uncached_regions = await cache_service.calculate_uncached_regions(
                    top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon
                )
                
                log.info(f"Cache analysis: Found {len(uncached_regions)} uncached regions for bbox")
# Cache analysis complete - proceeding with any missing data fetch
                
                # Stream live data from uncached regions
                if uncached_regions:
                    log.info(f"Need to fetch data from Mapillary API for {len(uncached_regions)} uncached regions")
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
                
                # Count photos instead of accumulating them in memory
                
                for region_idx, region_bbox in enumerate(uncached_regions):
                    log.info(f"Processing uncached region {region_idx + 1}/{len(uncached_regions)}: {region_bbox}")
                    # Check if we've already reached the photo limit
                    if total_photo_count >= MAX_PHOTOS_PER_REQUEST:
                        log.info(f"Photo limit of {MAX_PHOTOS_PER_REQUEST} reached, skipping remaining regions")
                        break
                        
                    try:
                        # Create cache region
                        region = await cache_service.create_cached_region(
                            region_bbox[0], region_bbox[1], region_bbox[2], region_bbox[3]
                        )
                    
                        cursor = None
                        region_photos = []
                    
                        # Stream all pages for this region
                        while True:
                            log.info(f"Fetching data from Mapillary API for region {region.id} with cursor: {cursor}")
                            mapillary_response = await fetch_mapillary_data(
                                region_bbox[0], region_bbox[1], region_bbox[2], region_bbox[3], cursor
                            )
                            
                            photos_data = mapillary_response["data"]
                            paging = mapillary_response["paging"]
                            
                            if not photos_data:
                                log.info(f"No more photos returned from Mapillary API for region {region.id}")
                                break
                            
                            # Cache all photos we received (no limit for caching current batch)
                            region_photos.extend(photos_data)
                            await cache_service.cache_photos(photos_data, region)
                            
                            # Apply photo limit only for streaming
                            stream_photos = photos_data
                            if total_photo_count + len(photos_data) > MAX_PHOTOS_PER_REQUEST:
                                # Truncate stream batch to stay within limit
                                remaining_slots = MAX_PHOTOS_PER_REQUEST - total_photo_count
                                stream_photos = photos_data[:remaining_slots]
                                log.info(f"Photo limit reached, streaming only {remaining_slots} photos (but caching all {len(photos_data)} from this batch)")
                            else:
                                log.info(f"Streaming {len(stream_photos)} live photos from region {region.id} (cached {len(photos_data)})")
                            
                            total_photo_count += len(stream_photos)
                            log.info(f"Total photos streamed so far: {total_photo_count}/{MAX_PHOTOS_PER_REQUEST}")
                            
                            # Stream this batch (limited)
                            sorted_batch = sorted(stream_photos, key=lambda x: x.get('compass_angle', 0))
                            # Region has more data if API indicates more pages available (regardless of our limit)
                            region_has_next = bool(paging.get("next"))
                            yield f"data: {json.dumps({'type': 'photos', 'photos': sorted_batch, 'hasNext': region_has_next})}\n\n"
                            
                            # Check if we've reached the photo limit for streaming
                            if total_photo_count >= MAX_PHOTOS_PER_REQUEST:
                                log.info(f"Photo limit of {MAX_PHOTOS_PER_REQUEST} reached, stopping fetch")
                                break
                            
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
                        log.info(f"Region {region.id} completed: cached {len(region_photos)} total photos")
                        
                        yield f"data: {json.dumps({'type': 'region_complete', 'region': region.id, 'photos_count': len(region_photos)})}\n\n"
                        
                    except Exception as e:
                        log.error(f"Error streaming region {region_bbox}: {str(e)}", exc_info=True)
                        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            
            # Send final summary
            total_all_photos = cached_photo_count + total_photo_count
            log.info(f"Stream complete for client {client_id}: {total_all_photos} total photos ({cached_photo_count} cached + {total_photo_count} live)")
            yield f"data: {json.dumps({'type': 'stream_complete', 'total_live_photos': total_photo_count, 'total_cached_photos': cached_photo_count, 'total_all_photos': total_all_photos})}\n\n"
        
        except Exception as e:
            log.error(f"Stream error for request {request_id}: {str(e)}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': f'Stream error: {str(e)}'})}\n\n"
        
        finally:
            log.info(f"Stream generator finished for request {request_id} from client {client_id}")
    
    try:
        log.info(f"Creating StreamingResponse for client {client_id}")
        response = StreamingResponse(
            generate_stream(db),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Cache-Control, Content-Type, Authorization",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Expose-Headers": "*",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
                "Content-Type": "text/event-stream; charset=utf-8"
            }
        )
        log.info(f"StreamingResponse created successfully for client {client_id}")
        return response
    except Exception as e:
        log.error(f"Failed to create StreamingResponse for client {client_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create stream: {str(e)}"
        )

@router.get("/stats")
async def get_cache_stats(db: AsyncSession = Depends(get_db)):
    """Get cache statistics"""
    cache_service = MapillaryCacheService(db)
    return await cache_service.get_cache_stats()