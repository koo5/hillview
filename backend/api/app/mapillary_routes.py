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

from .database import get_db, SessionLocal
from .models import CachedRegion, MapillaryPhotoCache
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
DISABLE_MAPILLARY_CACHE = os.getenv("DISABLE_MAPILLARY_CACHE", "false").lower() in ("true", "1", "yes")

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
        "limit": 200,
        "bbox": ",".join(map(str, [round(top_left_lon, 7), round(bottom_right_lat,7), round(bottom_right_lon,7), round(top_left_lat,7)])),
        "fields": "id,geometry,compass_angle,thumb_1024_url,computed_rotation,computed_compass_angle,computed_altitude,captured_at,is_pano",
        "access_token": get_mapillary_token(),
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
    
    async def generate_stream(db_session: AsyncSession):
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
                cache_service = MapillaryCacheService(db_session)
                
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
        generate_stream(db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

@router.get("/stats")
async def get_cache_stats(db: AsyncSession = Depends(get_db)):
    """Get cache statistics"""
    cache_service = MapillaryCacheService(db)
    return await cache_service.get_cache_stats()