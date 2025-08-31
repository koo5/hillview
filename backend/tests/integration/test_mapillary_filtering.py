#!/usr/bin/env python3
"""
Test Mapillary photo filtering functionality using mock data.
"""

import requests
import json
from utils.test_utils import clear_test_database, API_URL

def setup_test_users():
    """Create test users and return auth tokens."""
    users = [
        {"username": "mapillary_user_1", "email": "map1@example.com", "password": "testpass123"},
        {"username": "mapillary_user_2", "email": "map2@example.com", "password": "testpass123"}
    ]
    
    auth_tokens = {}
    for user in users:
        # Register
        response = requests.post(f"{API_URL}/auth/register", json=user)
        if response.status_code != 200:
            print(f"Failed to register {user['username']}: {response.status_code}")
            continue
            
        # Login
        response = requests.post(f"{API_URL}/auth/token", data={"username": user["username"], "password": user["password"]})
        if response.status_code == 200:
            auth_tokens[user["username"]] = response.json()["access_token"]
            print(f"✓ Created user: {user['username']}")
    
    return auth_tokens

def create_mock_mapillary_data():
    """Create mock Mapillary data for testing."""
    return {
        "data": [
            {
                "id": "mock_mapillary_1",
                "geometry": {
                    "type": "Point",
                    "coordinates": [14.4378, 50.0755]  # Prague Castle area
                },
                "compass_angle": 45.0,
                "computed_compass_angle": 45.0,
                "computed_rotation": 0.0,
                "computed_altitude": 250.0,
                "captured_at": "2024-01-15T10:30:00Z",
                "is_pano": False,
                "thumb_1024_url": "https://mock.mapillary.com/thumb1.jpg",
                "creator": {
                    "username": "mock_creator_1",
                    "id": "mock_creator_1"
                }
            },
            {
                "id": "mock_mapillary_2", 
                "geometry": {
                    "type": "Point",
                    "coordinates": [14.4175, 50.0865]  # Old Town Square area
                },
                "compass_angle": 90.0,
                "computed_compass_angle": 90.0,
                "computed_rotation": 0.0,
                "computed_altitude": 220.0,
                "captured_at": "2024-01-15T11:00:00Z",
                "is_pano": False,
                "thumb_1024_url": "https://mock.mapillary.com/thumb2.jpg",
                "creator": {
                    "username": "mock_creator_2", 
                    "id": "mock_creator_2"
                }
            },
            {
                "id": "mock_mapillary_3",
                "geometry": {
                    "type": "Point",
                    "coordinates": [14.4362, 50.0819]  # Wenceslas Square area
                },
                "compass_angle": 135.0,
                "computed_compass_angle": 135.0,
                "computed_rotation": 0.0,
                "computed_altitude": 240.0,
                "captured_at": "2024-01-15T11:30:00Z",
                "is_pano": False,
                "thumb_1024_url": "https://mock.mapillary.com/thumb3.jpg",
                "creator": {
                    "username": "mock_creator_1",  # Same creator as photo 1
                    "id": "mock_creator_1"
                }
            },
            {
                "id": "mock_mapillary_4",
                "geometry": {
                    "type": "Point", 
                    "coordinates": [14.4208, 50.0870]  # Charles Bridge area
                },
                "compass_angle": 180.0,
                "computed_compass_angle": 180.0,
                "computed_rotation": 0.0,
                "computed_altitude": 190.0,
                "captured_at": "2024-01-15T12:00:00Z",
                "is_pano": False,
                "thumb_1024_url": "https://mock.mapillary.com/thumb4.jpg",
                "creator": {
                    "username": "mock_creator_3",
                    "id": "mock_creator_3"
                }
            }
        ]
    }

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

def verify_exact_mock_data(photos, expected_ids, test_name=""):
    """Verify that photos contain exactly the expected mock data and nothing else."""
    photo_ids = {photo['id'] for photo in photos}
    
    # Verify exact ID match
    assert photo_ids == expected_ids, f"{test_name} got unexpected photo IDs. Expected: {expected_ids}, Got: {photo_ids}"
    
    # Verify no real Mapillary data leaked through
    for photo_id in photo_ids:
        assert photo_id.startswith('mock_'), f"{test_name} Non-mock photo ID detected: {photo_id} (real Mapillary data leaked through!)"
    
    # Verify photo structure (all should have required fields)
    for photo in photos:
        assert 'id' in photo, f"{test_name} Photo missing 'id' field: {photo}"
        assert 'geometry' in photo, f"{test_name} Photo missing 'geometry' field: {photo}"
        assert 'coordinates' in photo['geometry'], f"{test_name} Photo missing coordinates: {photo}"
        assert 'creator' in photo, f"{test_name} Photo missing 'creator' field: {photo}"
        assert len(photo['geometry']['coordinates']) == 2, f"{test_name} Invalid coordinates format: {photo['geometry']['coordinates']}"
    
    return True

def get_mapillary_photos(bbox, token=None):
    """Get Mapillary photos from the API via SSE stream."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    headers["Accept"] = "text/event-stream"
    headers["Cache-Control"] = "no-cache"
    
    params = {
        "top_left_lat": bbox[3],    # north
        "top_left_lon": bbox[0],    # west  
        "bottom_right_lat": bbox[1], # south
        "bottom_right_lon": bbox[2], # east
        "client_id": "test_client"
    }
    
    response = requests.get(f"{API_URL}/mapillary", params=params, headers=headers, stream=True)
    
    if response.status_code == 200:
        photos = []
        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith('data: '):
                try:
                    data = json.loads(line[6:])  # Remove 'data: ' prefix
                    if data.get('type') == 'photos':
                        photos.extend(data.get('photos', []))
                    elif data.get('type') == 'stream_complete':
                        # End of stream
                        break
                except json.JSONDecodeError:
                    continue
        return photos
    else:
        print(f"Failed to get photos: {response.status_code} - {response.text}")
        return []

def test_mapillary_filtering():
    """Test Mapillary photo filtering functionality."""
    print("🧪 Starting Mapillary Filtering Tests")
    print("=" * 50)
    
    # Setup
    clear_test_database()
    auth_tokens = setup_test_users()
    
    if not auth_tokens:
        print("❌ Failed to setup test users")
        return False
    
    user1_token = auth_tokens.get("mapillary_user_1")
    user2_token = auth_tokens.get("mapillary_user_2") 
    
    # Set mock data
    mock_data = create_mock_mapillary_data()
    if not set_mock_mapillary_data(mock_data):
        return False
    
    # Prague area bbox [west, south, east, north]
    prague_bbox = [14.40, 50.07, 14.45, 50.09]
    
    try:
        print("\n--- Testing Baseline Mapillary Photos ---")
        # Test anonymous access
        anon_photos = get_mapillary_photos(prague_bbox)
        print(f"Anonymous user sees: {len(anon_photos)} Mapillary photos")
        
        # Test authenticated access  
        auth_photos = get_mapillary_photos(prague_bbox, user1_token)
        print(f"Authenticated user sees: {len(auth_photos)} Mapillary photos")
        
        assert len(anon_photos) == len(auth_photos), "Anonymous and authenticated should see same Mapillary photos initially"
        assert len(anon_photos) == 4, f"Expected 4 mock photos, got {len(anon_photos)}"
        
        # Verify we got exactly the expected mock photo IDs and nothing else
        expected_photo_ids = {"mock_mapillary_1", "mock_mapillary_2", "mock_mapillary_3", "mock_mapillary_4"}
        verify_exact_mock_data(anon_photos, expected_photo_ids, "Anonymous user")
        verify_exact_mock_data(auth_photos, expected_photo_ids, "Authenticated user")
        
        print(f"✓ Verified exact mock data: {sorted({p['id'] for p in anon_photos})}")
        print("✓ Confirmed no real Mapillary data leaked through")
        
        # Verify photo details match mock data
        for photo in anon_photos:
            if photo['id'] == 'mock_mapillary_1':
                assert photo['geometry']['coordinates'] == [14.4378, 50.0755], f"Wrong coordinates for mock_mapillary_1: {photo['geometry']['coordinates']}"
                assert photo['creator']['username'] == 'mock_creator_1', f"Wrong creator for mock_mapillary_1: {photo['creator']['username']}"
            elif photo['id'] == 'mock_mapillary_2':
                assert photo['geometry']['coordinates'] == [14.4175, 50.0865], f"Wrong coordinates for mock_mapillary_2: {photo['geometry']['coordinates']}"
                assert photo['creator']['username'] == 'mock_creator_2', f"Wrong creator for mock_mapillary_2: {photo['creator']['username']}"
        
        print("✓ Verified mock photo details are correct")
        
        print("\n--- Testing Individual Mapillary Photo Hiding ---")
        # Hide a specific Mapillary photo
        hide_data = {
            "photo_source": "mapillary",
            "photo_id": "mock_mapillary_1"
        }
        
        response = requests.post(f"{API_URL}/hidden-photos/", 
                               json=hide_data, 
                               headers={"Authorization": f"Bearer {user1_token}"})
        
        if response.status_code == 200:
            print("✓ Hidden Mapillary photo: mock_mapillary_1")
            
            # Check filtering
            filtered_photos = get_mapillary_photos(prague_bbox, user1_token)
            other_user_photos = get_mapillary_photos(prague_bbox, user2_token)
            
            assert len(filtered_photos) == 3, f"User1 should see 3 photos after hiding 1, got {len(filtered_photos)}"
            assert len(other_user_photos) == 4, f"User2 should still see 4 photos, got {len(other_user_photos)}"
            
            print(f"✓ User1 sees {len(filtered_photos)} photos (hidden 1)")
            print(f"✓ User2 sees {len(other_user_photos)} photos (no hiding)")
        else:
            print(f"⚠ Failed to hide photo: {response.status_code}")
            
        print("\n--- Testing Mapillary User Hiding ---")
        # Hide a Mapillary user (creator)
        hide_user_data = {
            "target_user_source": "mapillary", 
            "target_user_id": "mock_creator_1"
        }
        
        response = requests.post(f"{API_URL}/hidden-users/",
                               json=hide_user_data,
                               headers={"Authorization": f"Bearer {user1_token}"})
        
        if response.status_code == 200:
            print("✓ Hidden Mapillary user: mock_creator_1")
            
            # Check filtering (should hide photos from mock_creator_1)
            filtered_photos = get_mapillary_photos(prague_bbox, user1_token)
            
            # mock_creator_1 has photos 1 and 3, but photo 1 was already hidden individually
            # So hiding the user should additionally hide photo 3
            assert len(filtered_photos) == 2, f"User1 should see 2 photos after hiding creator, got {len(filtered_photos)}"
            
            # Verify the remaining photos are from other creators
            creator_ids = [photo.get('creator', {}).get('id') for photo in filtered_photos]
            assert 'mock_creator_1' not in creator_ids, "Hidden creator's photos should not appear"
            
            print(f"✓ User1 sees {len(filtered_photos)} photos after hiding creator")
        else:
            print(f"⚠ Failed to hide user: {response.status_code}")
        
        print("\n--- Testing Geographic Filtering ---")
        # Test smaller bbox that should exclude some photos
        small_bbox = [14.435, 50.075, 14.440, 50.078]  # Smaller area around Prague Castle
        small_area_photos = get_mapillary_photos(small_bbox, user2_token)  # User2 has no hidden items
        
        print(f"Smaller area shows: {len(small_area_photos)} photos")
        assert len(small_area_photos) <= 4, "Smaller area should show same or fewer photos"
        
        # Verify that only photos within the smaller bbox are returned
        expected_in_small_area = {"mock_mapillary_1"}  # Only this one should be in the small bbox
        verify_exact_mock_data(small_area_photos, expected_in_small_area, "Geographic filtering")
        
        # Verify coordinates are within the smaller bbox for all returned photos
        for photo in small_area_photos:
            lon, lat = photo['geometry']['coordinates']
            assert small_bbox[0] <= lon <= small_bbox[2], f"Photo {photo['id']} longitude {lon} outside bbox longitude range [{small_bbox[0]}, {small_bbox[2]}]"
            assert small_bbox[1] <= lat <= small_bbox[3], f"Photo {photo['id']} latitude {lat} outside bbox latitude range [{small_bbox[1]}, {small_bbox[3]}]"
        
        print(f"✓ Geographic filtering working correctly: {sorted({p['id'] for p in small_area_photos})}")
        print("✓ Verified exact geographic filtering results")
        
    finally:
        # Cleanup
        clear_mock_mapillary_data()
        print("\n✓ Test cleanup complete")
    
    print("\n🎉 All Mapillary filtering tests passed!")
    return True

if __name__ == "__main__":
    test_mapillary_filtering()