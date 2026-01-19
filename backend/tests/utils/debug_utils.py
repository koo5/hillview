#!/usr/bin/env python3
"""
Debug utilities using the centralized API client.
"""

import sys
import json
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


def verify_signature(message_json: str, signature_base64: str, public_key_pem: str):
    """Verify an ECDSA signature given message JSON, signature, and public key."""
    try:
        # Import the verification function from common
        sys.path.insert(0, '.')
        from common.security_utils import verify_ecdsa_signature

        # Parse the message JSON
        message_data = json.loads(message_json)

        print("🔐 Verifying ECDSA signature...")
        print(f"   Message: {message_json[:100]}{'...' if len(message_json) > 100 else ''}")
        print(f"   Signature: {signature_base64[:50]}...")
        print(f"   Public key: {public_key_pem[:50]}...")

        # Verify the signature
        is_valid = verify_ecdsa_signature(signature_base64, public_key_pem, message_data)

        if is_valid:
            print("✅ Signature is VALID")
        else:
            print("❌ Signature is INVALID")

        return is_valid

    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON message: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def base64_to_pem(base64_key: str):
    """Convert base64-encoded public key (from Android log) to PEM format and show fingerprint."""
    try:
        sys.path.insert(0, '.')
        from common.security_utils import generate_client_key_id

        # Remove any whitespace/newlines from the base64
        base64_clean = base64_key.strip().replace('\n', '').replace(' ', '')

        # Chunk into 64-char lines (standard PEM format)
        lines = [base64_clean[i:i+64] for i in range(0, len(base64_clean), 64)]
        formatted = '\n'.join(lines)

        # Create PEM
        pem = f"-----BEGIN PUBLIC KEY-----\n{formatted}\n-----END PUBLIC KEY-----"

        print("📜 PEM format:")
        print(pem)
        print()

        # Calculate fingerprint
        fingerprint = generate_client_key_id(pem)
        print(f"🔑 Key fingerprint (key_id): {fingerprint}")

        return pem, fingerprint

    except Exception as e:
        print(f"❌ Error: {e}")
        return None, None


def upload_random_photos(count: int = 10):
    """Upload photos with randomized locations and bearings."""
    import asyncio
    import random
    from .image_utils import create_test_image_full_gps
    from .secure_upload_utils import SecureUploadClient
    from .test_utils import wait_for_photo_processing, API_URL

    async def _upload():
        print(f"📸 Uploading {count} random photos...")

        token = auth_helper.get_test_user_token("test")
        upload_client = SecureUploadClient(api_url=API_URL)

        # Center around Prague with some spread
        center_lat, center_lon = 50.08, 14.42

        created = 0
        for i in range(count):
            # Random location within ~5km of center
            lat = center_lat + random.uniform(-0.05, 0.05)
            lon = center_lon + random.uniform(-0.05, 0.05)
            bearing = random.uniform(0, 360)
            color = (random.randint(50, 255), random.randint(50, 255), random.randint(50, 255))
            filename = f"random_photo_{i+1:03d}.jpg"

            print(f"  [{i+1}/{count}] Uploading {filename}...")

            image_data = create_test_image_full_gps(400, 300, color, lat, lon, bearing)

            client_keys = upload_client.generate_client_keys()
            await upload_client.register_client_key(token, client_keys)

            auth_data = await upload_client.authorize_upload_with_params(
                token, filename, len(image_data), lat, lon,
                f"Random test photo #{i+1}",
                is_public=True, file_data=image_data
            )

            result = await upload_client.upload_to_worker(image_data, auth_data, client_keys, filename)
            photo_id = result.get('photo_id', auth_data.get('photo_id'))

            photo_data = wait_for_photo_processing(photo_id, token, timeout=30)
            if photo_data['processing_status'] == 'completed':
                created += 1
                print(f"    ✓ lat={lat:.4f}, lon={lon:.4f}, bearing={bearing:.0f}°")
            else:
                print(f"    ✗ failed: {photo_data.get('error', 'Unknown error')}")

        print(f"\n✅ Created {created}/{count} random photos")

    try:
        asyncio.run(_upload())
    except Exception as e:
        print(f"❌ Error: {e}")


def populate_photos(count: int = 4):
    """Populate the database with test Hillview photos at fixed Prague locations."""
    import asyncio
    from .image_utils import create_test_image_full_gps
    from .secure_upload_utils import SecureUploadClient
    from .test_utils import wait_for_photo_processing, API_URL

    async def _populate():
        print(f"📸 Creating {count} test Hillview photos...")

        # Get auth token for test user
        token = auth_helper.get_test_user_token("test")

        upload_client = SecureUploadClient(api_url=API_URL)

        # Test photo data: filename, color, lat, lon, bearing
        photo_configs = [
            ("prague_castle.jpg", (255, 0, 0), 50.0755, 14.4378, 45.0),      # Red - Prague Castle
            ("old_town.jpg", (0, 255, 0), 50.0865, 14.4175, 90.0),           # Green - Old Town Square
            ("wenceslas_sq.jpg", (0, 0, 255), 50.0819, 14.4362, 135.0),      # Blue - Wenceslas Square
            ("charles_bridge.jpg", (255, 255, 0), 50.0870, 14.4208, 180.0),  # Yellow - Charles Bridge
            ("vysehrad.jpg", (255, 0, 255), 50.0643, 14.4178, 225.0),        # Magenta - Vysehrad
            ("petrin.jpg", (0, 255, 255), 50.0833, 14.3950, 270.0),          # Cyan - Petrin Hill
        ]

        created = 0
        for i in range(min(count, len(photo_configs))):
            filename, color, lat, lon, bearing = photo_configs[i]

            print(f"  Uploading {filename}...")

            # Create image with full GPS data
            image_data = create_test_image_full_gps(400, 300, color, lat, lon, bearing)

            # Secure upload workflow
            client_keys = upload_client.generate_client_keys()
            await upload_client.register_client_key(token, client_keys)

            auth_data = await upload_client.authorize_upload_with_params(
                token, filename, len(image_data), lat, lon,
                f"Test photo at {filename.replace('.jpg', '').replace('_', ' ')}",
                is_public=True, file_data=image_data
            )

            result = await upload_client.upload_to_worker(image_data, auth_data, client_keys, filename)
            photo_id = result.get('photo_id', auth_data.get('photo_id'))

            # Wait for processing
            photo_data = wait_for_photo_processing(photo_id, token, timeout=30)
            if photo_data['processing_status'] == 'completed':
                created += 1
                print(f"    ✓ {filename}: lat={photo_data.get('latitude'):.4f}, lon={photo_data.get('longitude'):.4f}, bearing={photo_data.get('bearing')}°")
            else:
                print(f"    ✗ {filename} failed: {photo_data.get('error', 'Unknown error')}")

        print(f"\n✅ Created {created}/{count} test photos")

    try:
        asyncio.run(_populate())
    except Exception as e:
        print(f"❌ Error: {e}")


def main():
    """Command-line interface."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python debug_utils.py recreate              # Recreate test users")
        print("  python debug_utils.py photos                # Show user's photos")
        print("  python debug_utils.py photo <id>            # Show photo details")
        print("  python debug_utils.py cleanup               # Delete user's photos")
        print("  python debug_utils.py populate-photos       # Create test photos (fixed locations)")
        print("  python debug_utils.py populate-photos 6     # Create N test photos (max 6)")
        print("  python debug_utils.py upload-random-photos  # Upload 10 random photos")
        print("  python debug_utils.py upload-random-photos 20  # Upload N random photos")
        print("  python debug_utils.py mock-mapillary        # Set up mock Mapillary data")
        print("  python debug_utils.py clear-mapillary       # Clear mock Mapillary data")
        print("  python debug_utils.py verify-signature <message_json> <signature_base64> <public_key_pem>")
        print("                                              # Verify ECDSA signature")
        print("  python debug_utils.py base64-to-pem <base64_key>")
        print("                                              # Convert Android pubkey to PEM & show fingerprint")
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
    elif command == "populate-photos":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 4
        populate_photos(count)
    elif command == "upload-random-photos":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        upload_random_photos(count)
    elif command == "mock-mapillary":
        setup_mock_mapillary()
    elif command == "clear-mapillary":
        clear_mock_mapillary()
    elif command == "verify-signature":
        if len(sys.argv) < 5:
            print("Usage: verify-signature <message_json> <signature_base64> <public_key_pem>")
            print("  message_json: JSON string of the message data")
            print("  signature_base64: Base64-encoded ECDSA signature")
            print("  public_key_pem: PEM-formatted ECDSA P-256 public key")
            return
        verify_signature(sys.argv[2], sys.argv[3], sys.argv[4])
    elif command == "base64-to-pem":
        if len(sys.argv) < 3:
            print("Usage: base64-to-pem <base64_key>")
            print("  base64_key: Base64-encoded public key from Android log")
            print("              (the value logged by: Base64.encodeToString(publicKey.encoded, NO_WRAP))")
            return
        base64_to_pem(sys.argv[2])
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()