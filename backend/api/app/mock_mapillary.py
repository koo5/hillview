"""
Mock Mapillary service for testing filtering without hitting the real API.
"""
import logging
import shutil
import struct
import zlib
from typing import Dict, List, Any, Optional
from shapely.geometry import Polygon, Point

from common.config import get_pics_dir, get_pics_url

logger = logging.getLogger(__name__)


# Color palette for mock thumbnails
MOCK_COLORS = [
	(100, 150, 200), (200, 100, 100), (100, 200, 100),
	(200, 200, 100), (200, 100, 200), (100, 200, 200),
	(150, 100, 200), (200, 150, 100), (100, 200, 150),
	(180, 180, 100), (100, 180, 180), (180, 100, 180),
]


def generate_simple_png(width: int = 64, height: int = 64, r: int = 100, g: int = 150, b: int = 200) -> bytes:
	"""Generate a minimal solid-color PNG image using only stdlib (no Pillow)."""
	def make_chunk(chunk_type: bytes, data: bytes) -> bytes:
		chunk = chunk_type + data
		crc = struct.pack('>I', zlib.crc32(chunk) & 0xffffffff)
		return struct.pack('>I', len(data)) + chunk + crc

	signature = b'\x89PNG\r\n\x1a\n'
	ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
	ihdr = make_chunk(b'IHDR', ihdr_data)

	row = bytes([r, g, b] * width)
	raw_data = b''.join(b'\x00' + row for _ in range(height))
	idat = make_chunk(b'IDAT', zlib.compress(raw_data))
	iend = make_chunk(b'IEND', b'')

	return signature + ihdr + idat + iend


def _get_mock_images_dir():
	return get_pics_dir() / "mapillary-mock"


def generate_mock_images(mock_data: Dict[str, Any]) -> Dict[str, Any]:
	"""Generate mock thumbnail images and rewrite thumb_1024_url in mock_data."""
	pics_url = get_pics_url()
	if not pics_url:
		logger.warning("PICS_URL not set, skipping mock image generation")
		return mock_data

	mock_dir = _get_mock_images_dir()
	mock_dir.mkdir(parents=True, exist_ok=True)

	base_url = pics_url.rstrip('/')
	photos = mock_data.get('data', [])
	for i, photo in enumerate(photos):
		r, g, b = MOCK_COLORS[i % len(MOCK_COLORS)]
		png_data = generate_simple_png(64, 64, r, g, b)
		photo_id = photo.get('id', f'mock_{i}')
		filename = f"{photo_id}.png"
		(mock_dir / filename).write_bytes(png_data)
		photo['thumb_1024_url'] = f"{base_url}/mapillary-mock/{filename}"

	logger.info(f"Generated {len(photos)} mock thumbnail images in {mock_dir}")
	return mock_data


def cleanup_mock_images():
	"""Remove the mapillary-mock directory from PICS_DIR."""
	mock_dir = _get_mock_images_dir()
	if mock_dir.exists():
		shutil.rmtree(mock_dir)
		logger.info(f"Cleaned up mock images directory: {mock_dir}")

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
	
	def filter_by_bbox(self, bbox_coords: List[float], limit: int = 2000) -> Dict[str, Any]:
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