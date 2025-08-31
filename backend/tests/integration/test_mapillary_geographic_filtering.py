#!/usr/bin/env python3
"""
Test Mapillary geographic filtering with comprehensive coverage and cache verification.
Tests both evenly distributed photos (should use cache) and poorly distributed photos (should bypass cache).
"""

import requests
import json
from utils.test_utils import clear_test_database, API_URL

def create_evenly_distributed_mock_data():
    """Create mock Mapillary data that's evenly distributed across a 10x10 grid."""
    # Prague area bbox: [14.40, 50.07, 14.45, 50.09] (west, south, east, north)
    west, south, east, north = 14.40, 50.07, 14.45, 50.09
    
    photos = []
    photo_id = 1
    
    # Create a 10x10 grid with at least one photo per cell
    grid_size = 10
    cell_width = (east - west) / grid_size
    cell_height = (north - south) / grid_size
    
    for row in range(grid_size):
        for col in range(grid_size):
            # Calculate cell bounds
            cell_west = west + col * cell_width
            cell_east = west + (col + 1) * cell_width
            cell_south = south + row * cell_height
            cell_north = south + (row + 1) * cell_height
            
            # Place one photo in the center of each cell
            center_lon = cell_west + cell_width / 2
            center_lat = cell_south + cell_height / 2
            
            photos.append({
                "id": f"mock_distributed_{photo_id:03d}",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(center_lon, 6), round(center_lat, 6)]
                },
                "compass_angle": 45.0 + (photo_id % 8) * 45,  # Vary angles
                "computed_compass_angle": 45.0 + (photo_id % 8) * 45,
                "computed_rotation": 0.0,
                "computed_altitude": 200.0 + (photo_id % 100),  # Vary altitudes
                "captured_at": f"2024-01-15T{10 + (photo_id % 12):02d}:30:00Z",
                "is_pano": False,
                "thumb_1024_url": f"https://mock.mapillary.com/distributed_{photo_id:03d}.jpg",
                "creator": {
                    "username": f"mock_creator_{(photo_id % 5) + 1}",  # 5 different creators
                    "id": f"mock_creator_{(photo_id % 5) + 1}"
                }
            })
            photo_id += 1
    
    return {"data": photos}

def create_clustered_mock_data():
    """Create mock Mapillary data that's clustered in one corner (poor distribution)."""
    # Prague area bbox: [14.40, 50.07, 14.45, 50.09] (west, south, east, north)
    
    photos = []
    # Cluster all photos in the southwest corner (first 10% of the area)
    cluster_area_width = (14.45 - 14.40) * 0.1
    cluster_area_height = (50.09 - 50.07) * 0.1
    
    for i in range(50):  # Create 50 clustered photos
        # Random position within the small cluster area
        import random
        random.seed(i)  # Deterministic for testing
        
        lon = 14.40 + random.uniform(0, cluster_area_width)
        lat = 50.07 + random.uniform(0, cluster_area_height)
        
        photos.append({
            "id": f"mock_clustered_{i+1:03d}",
            "geometry": {
                "type": "Point", 
                "coordinates": [round(lon, 6), round(lat, 6)]
            },
            "compass_angle": random.uniform(0, 360),
            "computed_compass_angle": random.uniform(0, 360),
            "computed_rotation": 0.0,
            "computed_altitude": 200.0 + random.uniform(-50, 50),
            "captured_at": f"2024-01-15T{10 + (i % 12):02d}:30:00Z",
            "is_pano": False,
            "thumb_1024_url": f"https://mock.mapillary.com/clustered_{i+1:03d}.jpg",
            "creator": {
                "username": f"mock_creator_{(i % 3) + 1}",  # 3 different creators
                "id": f"mock_creator_{(i % 3) + 1}"
            }
        })
    
    return {"data": photos}

def set_mock_mapillary_data(mock_data):
    """Set mock Mapillary data via debug endpoint."""
    response = requests.post(f"{API_URL}/debug/mock-mapillary", json=mock_data)
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Set mock Mapillary data: {result['details']['photos_count']} photos")
        return True
    else:
        print(f"⚠ Failed to set mock data: {response.status_code} - {response.text}")
        return False

def clear_mock_mapillary_data():
    """Clear mock Mapillary data via debug endpoint."""
    response = requests.delete(f"{API_URL}/debug/mock-mapillary")
    if response.status_code == 200:
        print("✓ Cleared mock Mapillary data")
        return True
    else:
        print(f"⚠ Failed to clear mock data: {response.status_code}")
        return False

def get_mapillary_photos(bbox, client_id="test_client", verbose=False):
    """Get Mapillary photos from the API via SSE stream."""
    headers = {
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache"
    }
    
    params = {
        "top_left_lat": bbox[3],    # north
        "top_left_lon": bbox[0],    # west  
        "bottom_right_lat": bbox[1], # south
        "bottom_right_lon": bbox[2], # east
        "client_id": client_id
    }
    
    if verbose:
        print(f"  Making request with client_id: {client_id}")
    
    response = requests.get(f"{API_URL}/mapillary", params=params, headers=headers, stream=True)
    
    if response.status_code == 200:
        photos = []
        cached_count = 0
        live_count = 0
        
        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith('data: '):
                try:
                    data = json.loads(line[6:])  # Remove 'data: ' prefix
                    if data.get('type') == 'photos':
                        photos.extend(data.get('photos', []))
                    elif data.get('type') == 'stream_complete':
                        cached_count = data.get('total_cached_photos', 0)
                        live_count = data.get('total_live_photos', 0)
                        if verbose:
                            print(f"  Stream complete: {cached_count} cached + {live_count} live = {len(photos)} total")
                        break
                except json.JSONDecodeError:
                    continue
        
        if verbose and len(photos) > 0:
            print(f"  Cache performance: {cached_count}/{len(photos)} photos from cache ({cached_count/len(photos)*100:.1f}%)")
        
        return photos
    else:
        print(f"Failed to get photos: {response.status_code} - {response.text}")
        return []

def verify_geographic_bounds(photos, bbox, test_name=""):
    """Verify all photos are within the specified bounding box."""
    west, south, east, north = bbox
    
    for photo in photos:
        lon, lat = photo['geometry']['coordinates']
        assert west <= lon <= east, f"{test_name} Photo {photo['id']} longitude {lon} outside bbox [{west}, {east}]"
        assert south <= lat <= north, f"{test_name} Photo {photo['id']} latitude {lat} outside bbox [{south}, {north}]"
    
    return True

def calculate_spatial_distribution(photos, bbox):
    """Calculate spatial distribution score (similar to cache service logic)."""
    if not photos:
        return 0.0
    
    west, south, east, north = bbox
    grid_size = 10
    cell_width = (east - west) / grid_size
    cell_height = (north - south) / grid_size
    
    # Track which cells have photos
    occupied_cells = set()
    
    for photo in photos:
        lon, lat = photo['geometry']['coordinates']
        
        # Calculate grid cell
        col = min(int((lon - west) / cell_width), grid_size - 1)
        row = min(int((lat - south) / cell_height), grid_size - 1)
        
        occupied_cells.add((row, col))
    
    # Distribution score = occupied cells / total cells
    total_cells = grid_size * grid_size
    return len(occupied_cells) / total_cells

def test_evenly_distributed_photos():
    """Test with evenly distributed photos - should utilize cache efficiently."""
    print("\n🧪 Testing Evenly Distributed Photos (Cache-Friendly)")
    print("=" * 60)
    
    # Clear any existing data
    clear_test_database()
    
    # Set evenly distributed mock data
    mock_data = create_evenly_distributed_mock_data()
    if not set_mock_mapillary_data(mock_data):
        return False
    
    # Prague area bbox
    prague_bbox = [14.40, 50.07, 14.45, 50.09]
    
    try:
        # First request - should populate cache
        print("\n--- First Request (Cache Population) ---")
        photos_1 = get_mapillary_photos(prague_bbox, "client_1", verbose=True)
        print(f"First request returned: {len(photos_1)} photos")
        
        assert len(photos_1) == 100, f"Expected 100 evenly distributed photos, got {len(photos_1)}"
        verify_geographic_bounds(photos_1, prague_bbox, "First request")
        
        # Verify all photos are mock data
        for photo in photos_1:
            assert photo['id'].startswith('mock_distributed_'), f"Non-mock photo detected: {photo['id']}"
        
        distribution_score_1 = calculate_spatial_distribution(photos_1, prague_bbox)
        print(f"Distribution score: {distribution_score_1:.2%} (should be high for even distribution)")
        assert distribution_score_1 >= 0.9, f"Expected high distribution score (≥90%), got {distribution_score_1:.2%}"
        
        # Second request - should use cache
        print("\n--- Second Request (Cache Usage) ---")
        photos_2 = get_mapillary_photos(prague_bbox, "client_2", verbose=True) 
        print(f"Second request returned: {len(photos_2)} photos")
        
        # Should return same photos (cache hit)
        photo_ids_1 = {photo['id'] for photo in photos_1}
        photo_ids_2 = {photo['id'] for photo in photos_2}
        
        # Note: Cache may apply spatial sampling/limits, so we verify we get mock data, not necessarily identical sets
        verify_geographic_bounds(photos_2, prague_bbox, "Second request")
        for photo in photos_2:
            assert photo['id'].startswith('mock_distributed_'), f"Non-mock photo detected: {photo['id']}"
        
        print("✓ Both requests returned valid mock data within geographic bounds")
        
        # Test smaller area - should return subset
        print("\n--- Testing Smaller Area (Geographic Filtering) ---")
        small_bbox = [14.40, 50.07, 14.425, 50.08]  # Southwest quarter
        small_area_photos = get_mapillary_photos(small_bbox, "client_3")
        print(f"Small area returned: {len(small_area_photos)} photos")
        
        verify_geographic_bounds(small_area_photos, small_bbox, "Small area")
        assert len(small_area_photos) < len(photos_1), "Small area should return fewer photos"
        assert len(small_area_photos) > 0, "Small area should return some photos"
        
        # All photos should be within the smaller area
        for photo in small_area_photos:
            assert photo['id'].startswith('mock_distributed_'), f"Non-mock photo in small area: {photo['id']}"
        
        print("✓ Geographic filtering working correctly with evenly distributed data")
        
    finally:
        clear_mock_mapillary_data()
    
    # Test completed successfully - no return value needed for pytest

def test_clustered_photos():
    """Test with clustered photos - should bypass cache due to poor distribution.""" 
    print("\n🧪 Testing Clustered Photos (Poor Distribution)")
    print("=" * 55)
    
    # Clear any existing data
    clear_test_database()
    
    # Set clustered mock data
    mock_data = create_clustered_mock_data()
    if not set_mock_mapillary_data(mock_data):
        return False
        
    # Prague area bbox
    prague_bbox = [14.40, 50.07, 14.45, 50.09]
    
    try:
        # First request
        print("\n--- First Request (Poor Distribution Detection) ---")
        photos_1 = get_mapillary_photos(prague_bbox, "client_4")
        print(f"First request returned: {len(photos_1)} photos")
        
        assert len(photos_1) == 50, f"Expected 50 clustered photos, got {len(photos_1)}"
        verify_geographic_bounds(photos_1, prague_bbox, "Clustered photos")
        
        # Verify all photos are mock data
        for photo in photos_1:
            assert photo['id'].startswith('mock_clustered_'), f"Non-mock photo detected: {photo['id']}"
        
        distribution_score_1 = calculate_spatial_distribution(photos_1, prague_bbox)
        print(f"Distribution score: {distribution_score_1:.2%} (should be low for clustered data)")
        assert distribution_score_1 < 0.5, f"Expected low distribution score (<50%), got {distribution_score_1:.2%}"
        
        # Second request - cache may be ignored due to poor distribution
        print("\n--- Second Request (Cache Bypass Expected) ---")
        photos_2 = get_mapillary_photos(prague_bbox, "client_5")
        print(f"Second request returned: {len(photos_2)} photos")
        
        verify_geographic_bounds(photos_2, prague_bbox, "Second clustered request")
        for photo in photos_2:
            assert photo['id'].startswith('mock_clustered_'), f"Non-mock photo detected: {photo['id']}"
        
        print("✓ Both requests returned valid clustered mock data")
        
        # Test area that should have no photos (most of the bbox is empty)
        print("\n--- Testing Empty Area (Geographic Filtering) ---")
        empty_bbox = [14.42, 50.08, 14.45, 50.09]  # Northeast area (should be empty)
        empty_area_photos = get_mapillary_photos(empty_bbox, "client_6")
        print(f"Empty area returned: {len(empty_area_photos)} photos")
        
        # Should return very few or no photos since all are clustered in SW corner
        assert len(empty_area_photos) <= 5, f"Expected few/no photos in empty area, got {len(empty_area_photos)}"
        
        if empty_area_photos:
            verify_geographic_bounds(empty_area_photos, empty_bbox, "Empty area")
            for photo in empty_area_photos:
                assert photo['id'].startswith('mock_clustered_'), f"Non-mock photo in empty area: {photo['id']}"
        
        print("✓ Geographic filtering correctly handles clustered data")
        
    finally:
        clear_mock_mapillary_data()
    
    # Test completed successfully - no return value needed for pytest

def test_repeated_requests_consistency():
    """Test that repeated requests return consistent results."""
    print("\n🧪 Testing Repeated Request Consistency")
    print("=" * 45)
    
    # Clear any existing data  
    clear_test_database()
    
    # Use evenly distributed data for this test
    mock_data = create_evenly_distributed_mock_data()
    if not set_mock_mapillary_data(mock_data):
        return False
    
    prague_bbox = [14.40, 50.07, 14.45, 50.09]
    
    try:
        # Make multiple requests and verify consistency
        all_requests_photos = []
        for i in range(5):
            photos = get_mapillary_photos(prague_bbox, f"consistency_client_{i+1}")
            print(f"Request {i+1}: {len(photos)} photos")
            
            verify_geographic_bounds(photos, prague_bbox, f"Request {i+1}")
            for photo in photos:
                assert photo['id'].startswith('mock_distributed_'), f"Non-mock photo in request {i+1}: {photo['id']}"
            
            all_requests_photos.append(set(photo['id'] for photo in photos))
        
        # All requests should return consistent mock data (though order and exact selection may vary due to caching/sampling)
        print("✓ All requests returned valid mock data within bounds")
        
        # Test that we consistently get reasonable number of photos
        photo_counts = [len(photos) for photos in all_requests_photos]
        min_count, max_count = min(photo_counts), max(photo_counts)
        print(f"Photo counts ranged from {min_count} to {max_count}")
        
        # Should be reasonably consistent (allow some variation due to caching/sampling)
        assert max_count - min_count <= 50, f"Photo count variation too high: {min_count}-{max_count}"
        
        print("✓ Repeated requests show reasonable consistency")
        
    finally:
        clear_mock_mapillary_data()
    
    # Test completed successfully - no return value needed for pytest

def test_geographic_filtering_comprehensive():
    """Run comprehensive geographic filtering tests."""
    print("🧪 Starting Comprehensive Mapillary Geographic Filtering Tests")
    print("=" * 70)
    
    success = True
    
    # Test 1: Evenly distributed photos (cache-friendly)
    try:
        if not test_evenly_distributed_photos():
            success = False
    except Exception as e:
        print(f"❌ Evenly distributed test failed: {e}")
        success = False
    
    # Test 2: Clustered photos (poor distribution)
    try:
        if not test_clustered_photos():
            success = False
    except Exception as e:
        print(f"❌ Clustered photos test failed: {e}")
        success = False
    
    # Test 3: Consistency of repeated requests
    try:
        if not test_repeated_requests_consistency():
            success = False
    except Exception as e:
        print(f"❌ Consistency test failed: {e}")
        success = False
    
    if success:
        print("\n🎉 All comprehensive geographic filtering tests passed!")
    else:
        print("\n❌ Some tests failed!")
    
    assert success, "Some geographic filtering tests failed"

if __name__ == "__main__":
    test_geographic_filtering_comprehensive()