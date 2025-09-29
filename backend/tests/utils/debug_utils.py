#!/usr/bin/env python3
"""
Debug utilities using the centralized API client.
"""

import sys
from .api_client import api_client
from .auth_utils import auth_helper


def debug_photos():
    """Debug user's photos."""
    try:
        # Get test user token
        token = auth_helper.get_test_user_token("test")

        # Get photos
        photos_data = api_client.get_photos(token)
        photos = photos_data.get('photos', [])
        counts = photos_data.get('counts', {})

        print(f"📸 Photo Summary:")
        print(f"   Total: {counts.get('total', len(photos))}")
        print(f"   Completed: {counts.get('completed', 0)}")
        print(f"   Failed: {counts.get('failed', 0)}")
        print(f"   Authorized: {counts.get('authorized', 0)}")

        # Show error photos
        error_photos = api_client.get_error_photos(token)
        if error_photos:
            print(f"\n🚨 {len(error_photos)} photos with errors:")
            for photo in error_photos:
                print(f"   {photo['id']}: {photo.get('error', 'no error message')}")
                print(f"      Filename: {photo.get('original_filename', 'unknown')}")
                print(f"      Uploaded: {photo.get('uploaded_at', 'unknown')}")

        # Show recent photos
        if photos:
            print(f"\n📋 Recent photos:")
            for photo in photos[:5]:
                status = photo.get('processing_status', 'unknown')
                filename = photo.get('original_filename', 'unknown')
                print(f"   {photo['id'][:8]}... - {status} - {filename}")

    except Exception as e:
        print(f"❌ Error: {e}")


def debug_photo_details(photo_id: str):
    """Get detailed photo info."""
    try:
        token = auth_helper.get_test_user_token("test")
        photo = api_client.get_photo_details(photo_id, token)

        print(f"📸 Photo {photo_id}:")
        print(f"   Status: {photo.get('processing_status', 'unknown')}")
        print(f"   Error: {photo.get('error', 'none')}")
        print(f"   Filename: {photo.get('original_filename', 'unknown')}")
        print(f"   Owner: {photo.get('owner_id', 'unknown')}")
        print(f"   Uploaded: {photo.get('uploaded_at', 'unknown')}")

        if photo.get('latitude') and photo.get('longitude'):
            print(f"   Location: {photo['latitude']}, {photo['longitude']}")
        if photo.get('bearing'):
            print(f"   Bearing: {photo['bearing']}°")
        if photo.get('sizes'):
            print(f"   Sizes: {list(photo['sizes'].keys())}")

    except Exception as e:
        print(f"❌ Error: {e}")


def recreate_users():
    """Recreate test users."""
    try:
        print("recreate test users..")
        result = api_client.recreate_test_users()
        print("✅ Test users recreated")
        details = result.get("details", {})
        passwords = details.get("user_passwords", {})
        for username, password in passwords.items():
            print(f"   {username}: {password}")
    except Exception as e:
        print(f"❌ Error: {e}")


def cleanup_photos():
    """Clean up user's photos."""
    try:
        token = auth_helper.get_test_user_token("test")
        count = api_client.cleanup_user_photos(token)
        print(f"🗑️ Deleted {count} photos")
    except Exception as e:
        print(f"❌ Error: {e}")


def setup_mock_mapillary():
    """Set up mock Mapillary data for browser testing."""
    import math

    try:
        # Clear database first to avoid cache/mock confusion
        print("🗑️ Clearing database (including Mapillary cache)...")
        clear_db_result = api_client.clear_database()
        print(f"✓ {clear_db_result['message']}")
        print(f"   Deleted {clear_db_result['details']['mapillary_cache_deleted']} cached photos")
        print(f"   Deleted {clear_db_result['details']['cached_regions_deleted']} cached areas")

        # Clear existing mock data
        print("🧹 Clearing existing mock data...")
        clear_result = api_client.clear_mock_mapillary_data()
        print(f"✓ {clear_result['message']}")

        # Create mock data around Prague coordinates (same as tests)
        print("📍 Creating mock Mapillary data...")
        center_lat = (50.114739147066835 + 50.114119952930224) / 2  # ~50.11443
        center_lng = (14.523099660873413 + 14.523957967758179) / 2  # ~14.5235

        base_latitude = center_lat
        base_longitude = center_lng
        photos = []

        for i in range(1, 16):  # 1 to 15 inclusive
            # Distribute photos in a circle around center
            angle = (i * 24) % 360
            distance = 0.0001 * ((i % 3) + 1)  # Very small distances
            lat_offset = distance * math.sin(angle * math.pi / 180)
            lng_offset = distance * math.cos(angle * math.pi / 180)

            photos.append({
                'id': f"mock_mapillary_{i:03d}",
                'geometry': {
                    'type': "Point",
                    'coordinates': [base_longitude + lng_offset, base_latitude + lat_offset]
                },
                'bearing': (i * 24) % 360,
                'computed_bearing': (i * 24) % 360,
                'computed_rotation': 0.0,
                'sequence_id': f"mock_sequence_{(i-1)//5 + 1}",
                'captured_at': f"2023-07-{10+i:02d}T12:00:00Z",
                'organization_id': "mock_org_001"
            })

        mock_data = {'data': photos}
        set_result = api_client.set_mock_mapillary_data(mock_data)
        print(f"✅ {set_result['message']}")
        print(f"   Mock photos: {set_result['details']['photos_count']}")

        # Show cache info and warnings
        cache_info = set_result['details']['cache_info']
        print(f"   Cached photos: {cache_info['cached_photos']}")
        print(f"   Cached areas: {cache_info['cached_areas']}")
        if cache_info.get('warning'):
            print(f"⚠️  {cache_info['warning']}")

        print(f"   Center: {center_lat:.6f}, {center_lng:.6f}")
        print()
        print("🗺️ To test in browser:")
        print("   1. Open your frontend app in browser")
        print("   2. Navigate to the map")
        print("   3. Enable Mapillary source in source buttons")
        print("   4. Pan around Prague center to see mock photos")
        print(f"   5. Good test area: lat={center_lat:.4f}, lng={center_lng:.4f}")
        print()
        print("💡 Testing tip: Mock data only works when no cached data exists.")
        print("   If you see real Mapillary photos, cached data is being used instead.")

    except Exception as e:
        print(f"❌ Error: {e}")


def clear_mock_mapillary():
    """Clear mock Mapillary data."""
    try:
        result = api_client.clear_mock_mapillary_data()
        print(f"✅ {result['message']}")
    except Exception as e:
        print(f"❌ Error: {e}")


def main():
    """Command-line interface."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python debug_utils.py recreate         # Recreate test users")
        print("  python debug_utils.py photos           # Show user's photos")
        print("  python debug_utils.py photo <id>       # Show photo details")
        print("  python debug_utils.py cleanup          # Delete user's photos")
        print("  python debug_utils.py mock-mapillary   # Set up mock Mapillary data")
        print("  python debug_utils.py clear-mapillary  # Clear mock Mapillary data")
        return

    command = sys.argv[1]

    if command == "recreate":
        recreate_users()
    elif command == "photos":
        debug_photos()
    elif command == "photo" and len(sys.argv) > 2:
        debug_photo_details(sys.argv[2])
    elif command == "cleanup":
        cleanup_photos()
    elif command == "mock-mapillary":
        setup_mock_mapillary()
    elif command == "clear-mapillary":
        clear_mock_mapillary()
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()