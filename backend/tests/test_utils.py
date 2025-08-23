#!/usr/bin/env python3
"""
Shared utilities for hidden content tests.
"""

import os
import requests
from PIL import Image
import piexif
import io

# Test configuration
BASE_URL = os.getenv("TEST_API_URL", "http://localhost:8055")
API_URL = f"{BASE_URL}/api"

def clear_test_database():
    """Clear the database before running tests. Throws exception on failure."""
    print("Clearing database...")
    response = requests.post(f"{API_URL}/debug/clear-database")
    if response.status_code == 200:
        details = response.json().get("details", {})
        print(f"✓ Database cleared: {details}")
    else:
        raise Exception(f"Database clear failed: {response.status_code} - {response.text}")

def create_test_image(width: int = 100, height: int = 100, color: tuple = (255, 0, 0), 
                      lat: float = 50.0755, lon: float = 14.4378) -> bytes:
    """Create a real JPEG image with GPS coordinates for testing."""
    # Create a simple colored image
    img = Image.new('RGB', (width, height), color)
    
    # Convert coordinates to GPS EXIF format
    def decimal_to_dms(decimal_deg):
        """Convert decimal degrees to degrees, minutes, seconds."""
        deg = int(decimal_deg)
        minutes = abs((decimal_deg - deg) * 60)
        min_int = int(minutes)
        sec = (minutes - min_int) * 60
        return [(deg, 1), (min_int, 1), (int(sec * 100), 100)]
    
    # Create GPS EXIF data (Prague coordinates by default)
    gps_dict = {
        piexif.GPSIFD.GPSLatitude: decimal_to_dms(abs(lat)),
        piexif.GPSIFD.GPSLatitudeRef: 'N' if lat >= 0 else 'S',
        piexif.GPSIFD.GPSLongitude: decimal_to_dms(abs(lon)),
        piexif.GPSIFD.GPSLongitudeRef: 'E' if lon >= 0 else 'W',
    }
    
    exif_dict = {"GPS": gps_dict}
    exif_bytes = piexif.dump(exif_dict)
    
    # Save to bytes buffer with GPS EXIF
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='JPEG', quality=85, exif=exif_bytes)
    img_buffer.seek(0)
    
    return img_buffer.getvalue()

def create_test_photos(test_users: list, auth_tokens: dict):
    """Create test photos by uploading real images to the API."""
    print("Creating test photos for filtering tests...")
    
    # Create test photos for different users with different colors
    test_photos_data = [
        ("test_photo_1.jpg", "Test photo 1 for filtering", True, (255, 0, 0)),   # Red
        ("test_photo_2.jpg", "Test photo 2 for filtering", True, (0, 255, 0)),   # Green
        ("test_photo_3.jpg", "Test photo 3 for filtering", False, (0, 0, 255)),  # Blue (private)
        ("test_photo_4.jpg", "Test photo 4 for filtering", True, (255, 255, 0)), # Yellow
    ]
    
    created_photos = 0
    for i, (filename, description, is_public, color) in enumerate(test_photos_data):
        # Assign photos to different users for variety
        user_index = i % len(test_users)
        username = test_users[user_index]["username"]
        
        # Get auth token
        token = auth_tokens.get(username)
        if not token:
            print(f"⚠ No token found for user {username}")
            continue
            
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create a real JPEG image
        image_data = create_test_image(200, 150, color)
        
        files = {"file": (filename, image_data, "image/jpeg")}
        data = {
            "description": description,
            "is_public": str(is_public).lower()
        }
        
        try:
            response = requests.post(
                f"{API_URL}/photos/upload",
                files=files,
                data=data,
                headers=headers
            )
            
            if response.status_code == 200:
                created_photos += 1
                result = response.json()
                photo_id = result.get('id', 'unknown')
                print(f"✓ Created photo: {filename} by {username} (ID: {photo_id})")
                print(f"  Photo details: lat={result.get('latitude', 'none')}, lon={result.get('longitude', 'none')}")
            else:
                print(f"⚠ Failed to create photo {filename}: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"⚠ Error creating photo {filename}: {e}")
    
    print(f"✓ Created {created_photos} test photos")
    return created_photos