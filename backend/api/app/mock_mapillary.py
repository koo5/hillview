"""
Mock Mapillary service for testing filtering without hitting the real API.
"""
import logging
from typing import Dict, List, Any, Optional
from shapely.geometry import Polygon, Point

logger = logging.getLogger(__name__)

class MockMapillaryService:
    """Service to mock Mapillary API responses for testing."""
    
    def __init__(self):
        self._mock_data: Optional[Dict[str, Any]] = None
    
    def set_mock_data(self, mock_response: Dict[str, Any]) -> None:
        """Set mock Mapillary response data."""
        self._mock_data = mock_response
        logger.info(f"Set mock Mapillary data with {len(mock_response.get('data', []))} photos")
    
    def clear_mock_data(self) -> None:
        """Clear mock data."""
        self._mock_data = None
        logger.info("Cleared mock Mapillary data")
    
    def has_mock_data(self) -> bool:
        """Check if mock data is available."""
        return self._mock_data is not None
    
    def filter_by_bbox(self, bbox_coords: List[float], limit: int = 250) -> Dict[str, Any]:
        """Filter mock data by bounding box coordinates with limit."""
        if not self._mock_data:
            return {"data": []}
        
        # Parse bbox: [west, south, east, north]
        west, south, east, north = bbox_coords
        bbox_polygon = Polygon([
            [west, south],
            [east, south], 
            [east, north],
            [west, north],
            [west, south]
        ])
        
        filtered_photos = []
        for photo in self._mock_data.get('data', []):
            geometry = photo.get('geometry', {})
            if geometry.get('type') == 'Point':
                coords = geometry.get('coordinates', [])
                if len(coords) >= 2:
                    lon, lat = coords[0], coords[1]
                    photo_point = Point(lon, lat)
                    
                    if bbox_polygon.contains(photo_point) or bbox_polygon.intersects(photo_point):
                        filtered_photos.append(photo)
                        # Apply limit
                        if len(filtered_photos) >= limit:
                            break
        
        logger.info(f"Filtered mock data: {len(self._mock_data.get('data', []))} -> {len(filtered_photos)} photos in bbox (limit: {limit})")
        return {"data": filtered_photos, "paging": {}}

# Global instance for the API to use
mock_mapillary_service = MockMapillaryService()