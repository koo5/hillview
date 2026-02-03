"""
Integration tests for photo-in-front persistence through picks mechanism.
Ensures the currently selected navigation photo stays loaded on map during panning.
"""

import pytest
import asyncio
from typing import List, Dict, Any
import json
import aiohttp
from datetime import datetime, timedelta

from tests.utils.api_client import APITestClient
from tests.utils.test_helpers import create_test_user, create_test_photo


class TestPhotoInFrontPersistence:
    """Test that the photo-in-front (selected for navigation) persists on map"""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Setup test client and test data"""
        self.client = APITestClient()
        self.base_url = "http://localhost:8055"

        # Create test user
        self.user_data = await create_test_user(self.client)
        self.auth_token = self.user_data['token']

        # Create many test photos to test culling scenarios
        self.test_photos = await self._create_test_photo_grid()

        yield

        # Cleanup
        await self._cleanup_test_data()

    async def _create_test_photo_grid(self) -> List[Dict[str, Any]]:
        """Create a grid of test photos to simulate dense photo area"""
        photos = []

        # Create a dense 20x20 grid of photos (400 total) to test culling
        base_lat = 50.08
        base_lng = 14.42

        for i in range(20):
            for j in range(20):
                lat = base_lat + i * 0.0005  # ~50m apart
                lng = base_lng + j * 0.0005

                photo = await create_test_photo(
                    self.client,
                    self.auth_token,
                    latitude=lat,
                    longitude=lng,
                    captured_at=datetime.now() - timedelta(minutes=i*20+j),
                    filename=f"grid_photo_{i}_{j}.jpg"
                )
                photos.append(photo)

                # Stop at 100 photos for faster tests
                if len(photos) >= 100:
                    return photos

        return photos

    async def _cleanup_test_data(self):
        """Clean up test photos and user"""
        for photo in self.test_photos:
            try:
                await self.client.delete(
                    f"/api/photos/{photo['id']}",
                    headers={"Authorization": f"Bearer {self.auth_token}"}
                )
            except:
                pass  # Ignore cleanup errors

    async def test_single_pick_persistence_at_edge(self):
        """Test that picked photo persists even when at edge of view bounds"""
        # Pick a photo that's at the edge of our grid
        edge_photo = self.test_photos[0]  # First photo, will be at corner
        pick_id = edge_photo['id']

        # Query with bounds that barely include the picked photo
        params = {
            'top_left_lat': edge_photo['latitude'] + 0.0001,  # Just barely includes
            'top_left_lon': edge_photo['longitude'] - 0.0001,
            'bottom_right_lat': edge_photo['latitude'] - 0.01,  # Extends far away
            'bottom_right_lon': edge_photo['longitude'] + 0.01,
            'client_id': 'test_client',
            'picks': pick_id,
            'max_photos': 50  # Limit to ensure culling would normally exclude edge photo
        }

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/api/hillview"
            async with session.get(url, params=params) as response:
                assert response.status == 200

                photos_data = await self._read_sse_photos(response)
                photos = photos_data['photos']
                photo_ids = [p['id'] for p in photos]

                assert pick_id in photo_ids, \
                    f"Picked photo {pick_id} should be included even at edge of bounds"

    async def test_pick_survives_culling(self):
        """Test that picked photo is retained even when normal culling would exclude it"""
        # Pick a photo in the middle of our grid
        middle_index = len(self.test_photos) // 2
        picked_photo = self.test_photos[middle_index]
        pick_id = picked_photo['id']

        # Query entire area but with very low limit
        params = {
            'top_left_lat': 50.12,
            'top_left_lon': 14.40,
            'bottom_right_lat': 50.06,
            'bottom_right_lon': 14.46,
            'client_id': 'test_client',
            'picks': pick_id,
            'max_photos': 5  # Very low limit - would normally exclude most photos
        }

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/api/hillview"
            async with session.get(url, params=params) as response:
                assert response.status == 200

                photos_data = await self._read_sse_photos(response)
                photos = photos_data['photos']

                assert len(photos) <= 5, f"Should respect max_photos limit, got {len(photos)}"

                photo_ids = [p['id'] for p in photos]
                assert pick_id in photo_ids, \
                    f"Picked photo should be included even with tight limit"

                # Picked photo should be first
                assert photos[0]['id'] == pick_id, \
                    "Picked photo should be prioritized to first position"

    async def test_pick_after_pan(self):
        """Simulate panning scenario: pick photo, then query different area overlapping original"""
        target_photo = self.test_photos[10]
        pick_id = target_photo['id']

        # First query: Area around the picked photo
        params1 = {
            'top_left_lat': target_photo['latitude'] + 0.002,
            'top_left_lon': target_photo['longitude'] - 0.002,
            'bottom_right_lat': target_photo['latitude'] - 0.002,
            'bottom_right_lon': target_photo['longitude'] + 0.002,
            'client_id': 'test_client',
            'picks': pick_id,
            'max_photos': 20
        }

        # Second query: Panned area that barely includes picked photo
        params2 = {
            'top_left_lat': target_photo['latitude'] + 0.004,  # Panned north
            'top_left_lon': target_photo['longitude'] - 0.001,
            'bottom_right_lat': target_photo['latitude'] - 0.0001,  # Barely includes
            'bottom_right_lon': target_photo['longitude'] + 0.004,  # Panned east
            'client_id': 'test_client',
            'picks': pick_id,
            'max_photos': 20
        }

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/api/hillview"

            # Query 1: Original view
            async with session.get(url, params=params1) as response:
                photos_data = await self._read_sse_photos(response)
                assert pick_id in [p['id'] for p in photos_data['photos']]

            # Query 2: After panning
            async with session.get(url, params=params2) as response:
                photos_data = await self._read_sse_photos(response)
                photo_ids = [p['id'] for p in photos_data['photos']]

                assert pick_id in photo_ids, \
                    "Picked photo should persist after panning"

                # Should still be prioritized
                assert photos_data['photos'][0]['id'] == pick_id, \
                    "Picked photo should remain prioritized after pan"

    async def test_pick_with_no_other_photos_in_bounds(self):
        """Test that pick is returned even when it's the only photo in bounds"""
        # Pick a corner photo
        corner_photo = self.test_photos[0]
        pick_id = corner_photo['id']

        # Query area that only contains the picked photo
        margin = 0.0002
        params = {
            'top_left_lat': corner_photo['latitude'] + margin,
            'top_left_lon': corner_photo['longitude'] - margin,
            'bottom_right_lat': corner_photo['latitude'] - margin,
            'bottom_right_lon': corner_photo['longitude'] + margin,
            'client_id': 'test_client',
            'picks': pick_id
        }

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/api/hillview"
            async with session.get(url, params=params) as response:
                assert response.status == 200

                photos_data = await self._read_sse_photos(response)
                photos = photos_data['photos']

                assert len(photos) >= 1, "Should return at least the picked photo"
                assert photos[0]['id'] == pick_id, "Should return the picked photo"

    async def test_pick_outside_bounds_not_returned(self):
        """Test that picked photo outside bounds is NOT returned (important boundary)"""
        some_photo = self.test_photos[0]
        pick_id = some_photo['id']

        # Query area that definitely doesn't contain the picked photo
        params = {
            'top_left_lat': some_photo['latitude'] + 1.0,  # Far north
            'top_left_lon': some_photo['longitude'] + 1.0,  # Far east
            'bottom_right_lat': some_photo['latitude'] + 0.5,
            'bottom_right_lon': some_photo['longitude'] + 1.5,
            'client_id': 'test_client',
            'picks': pick_id
        }

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/api/hillview"
            async with session.get(url, params=params) as response:
                assert response.status == 200

                photos_data = await self._read_sse_photos(response)
                photos = photos_data['photos']
                photo_ids = [p['id'] for p in photos]

                assert pick_id not in photo_ids, \
                    "Picked photo outside bounds should NOT be returned"

    async def _read_sse_photos(self, response) -> Dict[str, Any]:
        """Helper to read photos from SSE stream"""
        async for line in response.content:
            line_str = line.decode('utf-8').strip()
            if line_str.startswith('data: '):
                data = json.loads(line_str[6:])
                if data.get('type') == 'photos':
                    return data
        raise ValueError("No photos data found in SSE stream")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])