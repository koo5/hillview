import json
import os
from typing import Optional, Dict, Any
import requests
import logging
from fastapi import APIRouter, Query, HTTPException, status
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hillview", tags=["hillview"])

GEO_PICS_URL = os.getenv("GEO_PICS_URL")

if not GEO_PICS_URL:
    log.warning("GEO_PICS_URL environment variable not set")

def parse_dms_coordinate(dms_str: str) -> float:
    """Parse DMS coordinate string like '[50, 10, 30023/1000]' to decimal degrees"""
    try:
        # Remove brackets and split
        coords = dms_str.strip('[]').split(', ')
        degrees = int(coords[0])
        minutes = int(coords[1])
        
        # Handle fractional seconds
        seconds_str = coords[2]
        if '/' in seconds_str:
            num, den = seconds_str.split('/')
            seconds = float(num) / float(den)
        else:
            seconds = float(seconds_str)
        
        # Convert to decimal degrees
        decimal = degrees + minutes/60 + seconds/3600
        return decimal
    except (ValueError, IndexError) as e:
        log.warning(f"Failed to parse DMS coordinate '{dms_str}': {e}")
        return 0.0

def is_point_in_bbox(lat: float, lon: float, top_left_lat: float, top_left_lon: float, 
                     bottom_right_lat: float, bottom_right_lon: float) -> bool:
    """Check if a point is within the bounding box"""
    return (bottom_right_lat <= lat <= top_left_lat and 
            top_left_lon <= lon <= bottom_right_lon)

@router.get("")
async def get_hillview_images(
    top_left_lat: float = Query(..., description="Top left latitude"),
    top_left_lon: float = Query(..., description="Top left longitude"),
    bottom_right_lat: float = Query(..., description="Bottom right latitude"),
    bottom_right_lon: float = Query(..., description="Bottom right longitude"),
    client_id: str = Query(..., description="Client ID")
):
    """Get Hillview images filtered by bounding box area"""
    
    if not GEO_PICS_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GEO_PICS_URL not configured"
        )
    
    try:
        # Fetch files.json from GEO_PICS_URL
        files_json_url = f"{GEO_PICS_URL}/files.json"
        log.info(f"Fetching files.json from {files_json_url}")
        
        response = requests.get(files_json_url)
        response.raise_for_status()
        
        files_data = response.json()
        
        # Filter files by bounding box area
        filtered_photos = []
        
        for file_info in files_data:
            # Extract GPS coordinates
            if 'latitude' in file_info and 'longitude' in file_info:
                lat = parse_dms_coordinate(file_info['latitude'])
                lon = parse_dms_coordinate(file_info['longitude'])
                
                if is_point_in_bbox(lat, lon, top_left_lat, top_left_lon, 
                                  bottom_right_lat, bottom_right_lon):
                    # Get bearing (compass angle)
                    bearing = float(file_info.get('bearing', 0))
                    
                    # Transform to match Mapillary-like structure
                    photo_data = {
                        'id': file_info.get('file', ''),
                        'geometry': {
                            'coordinates': [lon, lat]
                        },
                        'compass_angle': bearing,
                        'computed_rotation': 0,
                        'computed_compass_angle': bearing,
                        'computed_altitude': float(file_info.get('altitude', 0)),
                        'captured_at': '',  # Not available in current structure
                        'is_pano': False,
                        'filename': file_info.get('file', ''),
                        'filepath': file_info.get('filepath', ''),
                        'dir_name': file_info.get('dir_name', ''),
                        'sizes': file_info.get('sizes', {})
                    }
                    filtered_photos.append(photo_data)
        
        # Sort by compass angle like Mapillary endpoint
        filtered_photos.sort(key=lambda x: x.get('compass_angle', 0))
        
        log.info(f"Filtered {len(filtered_photos)} photos from {len(files_data)} total files")
        
        return {
            'data': filtered_photos,
            'total_count': len(filtered_photos),
            'bbox': {
                'top_left_lat': top_left_lat,
                'top_left_lon': top_left_lon,
                'bottom_right_lat': bottom_right_lat,
                'bottom_right_lon': bottom_right_lon
            }
        }
        
    except requests.RequestException as e:
        log.error(f"Error fetching files.json: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch data from GEO_PICS_URL: {str(e)}"
        )
    except json.JSONDecodeError as e:
        log.error(f"Error parsing files.json: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid JSON response from GEO_PICS_URL"
        )
    except Exception as e:
        log.error(f"Unexpected error in hillview endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )