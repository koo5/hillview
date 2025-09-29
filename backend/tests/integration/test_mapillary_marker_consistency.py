"""
Integration test for Mapillary marker consistency - equivalent to the failing Playwright test.

This test verifies that:
1. Mock Mapillary data returns exactly 15 photos initially
2. After changing the bounding box (simulating map pan), we still get consistent results
3. No photo duplication occurs during area updates

This mirrors the failing test in frontend/tests-playwright/mapillary-marker-consistency.spec.ts
"""

import pytest
import requests
from typing import Dict, List, Any
import math

from utils.api_client import APIClient
from utils.test_utils import recreate_test_users


class TestMapillaryMarkerConsistency:
    """Test Mapillary photo loading consistency during map panning simulation"""

    @pytest.fixture(autouse=True)
    def setup_test_users(self):
        """Setup test users before each test"""
        recreate_test_users()

    def test_mock_data_structure_and_duplication(self):
        """
        Test the mock data structure itself and check for duplication issues
        """
        client = APIClient()

        # Create mock data with exact same structure as frontend
        print("📍 Creating mock data with frontend-identical structure...")
        mock_data = self._create_mock_mapillary_data_frontend_identical()

        print(f"📊 Mock data structure:")
        print(f"   Photos count: {len(mock_data['data'])}")
        print(f"   First photo: {mock_data['data'][0]}")
        print(f"   Photo IDs: {[p['id'] for p in mock_data['data'][:5]]}...")

        # Check for duplicates in mock data itself
        photo_ids = [photo['id'] for photo in mock_data['data']]
        unique_ids = set(photo_ids)
        assert len(photo_ids) == len(unique_ids), f"Mock data has duplicate IDs: {len(photo_ids)} vs {len(unique_ids)}"

        set_response = client.set_mock_mapillary_data(mock_data)
        print(f"✓ Set mock Mapillary data: {set_response}")

        # Clear database to remove cached data (prevents cache+live duplication)
        print("🗑️ Clearing database (including Mapillary cache)...")
        clear_db_response = client.clear_database()
        print(f"✓ Cleared database: {clear_db_response['message']}")

        # Verify backend stored exactly 15 photos
        assert set_response['details']['photos_count'] == 15

        # Make first request - should get 15 unique photos
        print("📍 First request - initial area...")
        bbox1 = {
            'top_left_lat': 50.115,
            'top_left_lng': 14.523,
            'bottom_right_lat': 50.114,
            'bottom_right_lng': 14.524
        }

        photos1 = client.get_mapillary_photos_by_bbox(**bbox1)
        photo_count1 = len(photos1.get('data', []))
        photo_ids1 = [p['id'] for p in photos1['data']]

        print(f"📍 First request returned: {photo_count1} photos")
        print(f"   Photo IDs: {photo_ids1[:5]}...")

        # Check for duplicates in response
        unique_ids1 = set(photo_ids1)
        if len(photo_ids1) != len(unique_ids1):
            duplicates = [pid for pid in photo_ids1 if photo_ids1.count(pid) > 1]
            print(f"❌ First request has {len(photo_ids1) - len(unique_ids1)} duplicates: {duplicates}")

        assert len(photo_ids1) == len(unique_ids1), "First request should not have duplicate photo IDs"
        assert photo_count1 == 15, f"Expected 15 photos, got {photo_count1}"

        # Make second request with slightly different bbox (simulating map pan)
        print("📍 Second request - simulating map pan...")
        bbox2 = {
            'top_left_lat': 50.1155,  # Slightly different
            'top_left_lng': 14.5235,  # Slightly different
            'bottom_right_lat': 50.1145,
            'bottom_right_lng': 14.5245
        }

        photos2 = client.get_mapillary_photos_by_bbox(**bbox2)
        photo_count2 = len(photos2.get('data', []))
        photo_ids2 = [p['id'] for p in photos2['data']]

        print(f"📍 Second request returned: {photo_count2} photos")
        print(f"   Photo IDs: {photo_ids2[:5]}...")

        # Check for duplicates in second response
        unique_ids2 = set(photo_ids2)
        if len(photo_ids2) != len(unique_ids2):
            duplicates = [pid for pid in photo_ids2 if photo_ids2.count(pid) > 1]
            print(f"❌ Second request has {len(photo_ids2) - len(unique_ids2)} duplicates: {duplicates}")

        assert len(photo_ids2) == len(unique_ids2), "Second request should not have duplicate photo IDs"

        # Compare the two responses
        print("🔍 Analyzing response differences...")
        common_ids = set(photo_ids1) & set(photo_ids2)
        only_in_first = set(photo_ids1) - set(photo_ids2)
        only_in_second = set(photo_ids2) - set(photo_ids1)

        print(f"   Common photos: {len(common_ids)}")
        print(f"   Only in first: {len(only_in_first)}")
        print(f"   Only in second: {len(only_in_second)}")

        # If mock photos cover both areas, we should get the same photos
        # If they don't overlap, we should get 0 photos in second request
        # But we should NEVER get 30 photos (duplication)

        if photo_count2 == 30:
            print("❌ DUPLICATION BUG REPRODUCED: Got 30 photos instead of 15!")
            print(f"   This matches the frontend bug - backend is duplicating photos")
            # Print the actual duplicate analysis
            for pid in set(photo_ids2):
                count = photo_ids2.count(pid)
                if count > 1:
                    print(f"   Photo {pid} appears {count} times")

        print("✅ Backend mock data consistency test completed")

    def test_mock_data_streaming_simulation(self):
        """
        Test that simulates the frontend streaming behavior to isolate the duplication
        """
        client = APIClient()

        # Clear mock data first, then set new mock data, then clear database
        print("🧹 Clearing existing mock data...")
        client.clear_mock_mapillary_data()
        print("📍 Setting up mock data...")
        mock_data = self._create_mock_mapillary_data_frontend_identical()
        client.set_mock_mapillary_data(mock_data)
        print("🗑️ Clearing database to remove cached data...")
        client.clear_database()

        # Simulate multiple rapid requests (like frontend map panning)
        print("🔄 Simulating rapid bbox changes like frontend map panning...")

        bbox_sequence = [
            (50.115, 14.523, 50.114, 14.524),    # Initial position
            (50.1155, 14.5235, 50.1145, 14.5245), # Pan 1
            (50.116, 14.524, 50.115, 14.525),    # Pan 2
            (50.1155, 14.5235, 50.1145, 14.5245), # Back to pan 1 position
        ]

        all_results = []
        for i, (tl_lat, tl_lng, br_lat, br_lng) in enumerate(bbox_sequence):
            print(f"🗺️ Request {i+1}: bbox {tl_lat}, {tl_lng} -> {br_lat}, {br_lng}")

            photos = client.get_mapillary_photos_by_bbox(
                top_left_lat=tl_lat, top_left_lng=tl_lng,
                bottom_right_lat=br_lat, bottom_right_lng=br_lng
            )

            photo_count = len(photos['data'])
            photo_ids = [p['id'] for p in photos['data']]
            unique_count = len(set(photo_ids))

            print(f"   Result: {photo_count} photos, {unique_count} unique")

            if photo_count != unique_count:
                print(f"   ❌ DUPLICATION DETECTED: {photo_count - unique_count} duplicates")

            all_results.append({
                'request': i+1,
                'total_photos': photo_count,
                'unique_photos': unique_count,
                'photo_ids': photo_ids
            })

            # Any request returning 30 photos indicates the bug
            if photo_count == 30:
                print(f"   ❌ BUG REPRODUCED: Request {i+1} returned 30 photos (should be ≤15)")

        print("📊 Summary of all requests:")
        for result in all_results:
            print(f"   Request {result['request']}: {result['total_photos']} total, {result['unique_photos']} unique")

    def _create_mock_mapillary_data_frontend_identical(self) -> Dict[str, Any]:
        """
        Create mock Mapillary data - EXACTLY identical to frontend createMockMapillaryData function
        This ensures we test the exact same data structure that's causing the frontend issue
        """
        # Use exact coordinates from frontend test
        center_lat = (50.114739147066835 + 50.114119952930224) / 2  # ~50.11443
        center_lng = (14.523099660873413 + 14.523957967758179) / 2  # ~14.5235

        base_latitude = center_lat
        base_longitude = center_lng
        photos = []

        for i in range(1, 16):  # 1 to 15 inclusive, exactly like frontend
            # Distribute photos very close to center to ensure they're within bbox
            angle = (i * 24) % 360  # Distribute in a circle
            distance = 0.0001 * ((i % 3) + 1)  # Very small distances (0.0001, 0.0002, 0.0003 degrees)
            lat_offset = distance * math.sin(angle * math.pi / 180)
            lng_offset = distance * math.cos(angle * math.pi / 180)

            photos.append({
                'id': f"mock_mapillary_{i:03d}",  # Exactly same ID format as frontend
                'geometry': {
                    'type': "Point",
                    'coordinates': [base_longitude + lng_offset, base_latitude + lat_offset]
                },
                'bearing': (i * 24) % 360,
                'computed_bearing': (i * 24) % 360,
                'computed_rotation': 0.0,
                'sequence_id': f"mock_sequence_{(i-1)//5 + 1}",  # Group into sequences of 5
                'captured_at': f"2023-07-{10+i:02d}T12:00:00Z",
                'organization_id': "mock_org_001"
            })

        return {'data': photos}

    def test_mock_data_backend_api_endpoints(self):
        """
        Test the backend mock data API endpoints directly to understand the data flow
        """
        client = APIClient()

        # Test 1: Clear and verify empty
        print("🧹 Testing clear functionality...")
        clear_result = client.clear_mock_mapillary_data()
        print(f"Clear result: {clear_result}")

        # Test 2: Set mock data and verify count
        print("📝 Testing set functionality...")
        mock_data = self._create_mock_mapillary_data_frontend_identical()
        set_result = client.set_mock_mapillary_data(mock_data)
        print(f"Set result: {set_result}")

        # Test 3: Check if backend is storing the data correctly
        # Make a request that should return all mock data
        print("🔍 Testing retrieval...")
        large_bbox_photos = client.get_mapillary_photos_by_bbox(
            top_left_lat=50.12, top_left_lng=14.52,
            bottom_right_lat=50.11, bottom_right_lng=14.53
        )

        retrieved_count = len(large_bbox_photos['data'])
        retrieved_ids = [p['id'] for p in large_bbox_photos['data']]

        print(f"Retrieved {retrieved_count} photos from large bbox")
        print(f"Photo IDs: {retrieved_ids}")

        # Check for any structural issues
        unique_retrieved = len(set(retrieved_ids))
        if retrieved_count != unique_retrieved:
            print(f"❌ Backend storage has duplicates: {retrieved_count} vs {unique_retrieved}")

        if retrieved_count == 30:
            print("❌ Backend is already returning 30 photos - storage issue!")
        elif retrieved_count == 15:
            print("✅ Backend storage is correct (15 photos)")
        else:
            print(f"⚠️ Unexpected count: {retrieved_count} photos")

        assert retrieved_count in [0, 15], f"Expected 0 or 15 photos, got {retrieved_count}"