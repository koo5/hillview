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
        if photo.get('compass_angle'):
            print(f"   Bearing: {photo['compass_angle']}°")
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


def main():
    """Command-line interface."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python debug_utils.py recreate    # Recreate test users")
        print("  python debug_utils.py photos      # Show user's photos")
        print("  python debug_utils.py photo <id>  # Show photo details")
        print("  python debug_utils.py cleanup     # Delete user's photos")
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
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()