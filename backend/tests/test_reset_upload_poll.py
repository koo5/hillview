#!/usr/bin/env python3
"""
Test that resets test users, logs in as test user, uploads a photo, 
and repeatedly polls the hillview endpoint until the photo shows up.
"""
import pytest
import requests
import time
import sys
import os
from PIL import Image
import io
import tempfile

# Add the backend directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

BASE_URL = "http://localhost:8055"

class TestResetUploadPoll:
    """Test complete workflow: reset test users -> login -> upload -> poll until photo appears"""
    
    def setup_method(self):
        """Setup for each test method"""
        self.test_user_credentials = {
            "username": "test",
            "password": "test123"
        }
        # Multiple test locations within Prague bounding box
        self.test_photo_locations = [
            {"latitude": 50.05, "longitude": 14.4, "bearing": 90, "altitude": 200, "description": "Prague Castle area"},
            {"latitude": 50.08, "longitude": 14.42, "bearing": 180, "altitude": 250, "description": "Old Town Square"},
            {"latitude": 50.06, "longitude": 14.38, "bearing": 270, "altitude": 180, "description": "Charles Bridge"},
            {"latitude": 50.07, "longitude": 14.45, "bearing": 45, "altitude": 220, "description": "Wenceslas Square"},
            {"latitude": 50.04, "longitude": 14.41, "bearing": 315, "altitude": 190, "description": "Petrin Hill"}
        ]
        
    def create_test_image_with_gps(self, location_data: dict, color: str = 'red') -> bytes:
        """Create a minimal test JPEG image with GPS EXIF data using exiftool"""
        from PIL import Image
        
        # Create a simple 100x100 image with specified color
        img = Image.new('RGB', (100, 100), color=color)
        
        # Save to temporary file first
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
            img.save(temp_file, 'JPEG')
            temp_path = temp_file.name
        
        try:
            # Use exiftool to add GPS data (matching the project's approach)
            import subprocess
            
            # Add GPS coordinates and bearing using exiftool
            cmd = [
                'exiftool',
                '-overwrite_original',
                f'-GPS:GPSLatitude={location_data["latitude"]}',
                '-GPS:GPSLatitudeRef=N',
                f'-GPS:GPSLongitude={location_data["longitude"]}', 
                '-GPS:GPSLongitudeRef=E',
                f'-GPS:GPSImgDirection={location_data["bearing"]}',  # Bearing/compass angle
                f'-GPS:GPSAltitude={location_data["altitude"]}',
                temp_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Warning: exiftool failed: {result.stderr}")
                # Fall back to image without GPS data
            
            # Read the file back
            with open(temp_path, 'rb') as f:
                image_data = f.read()
                
            return image_data
            
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except:
                pass
    
    def create_simple_test_image(self) -> bytes:
        """Create a simple test image without GPS data as fallback"""
        from PIL import Image
        
        # Create a simple 100x100 red image
        img = Image.new('RGB', (100, 100), color='red')
        
        # Save to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, 'JPEG')
        img_bytes.seek(0)
        return img_bytes.getvalue()
    
    def reset_test_users(self):
        """Reset test users using the debug endpoint"""
        print("Resetting test users using debug endpoint...")
        
        response = requests.post(f"{BASE_URL}/api/debug/recreate-test-users")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Test users reset successfully: {result}")
            details = result.get("details", {}) or {}
            photos_deleted = details.get("photos_deleted", 0)
            users_deleted = details.get("users_deleted", 0)
            users_created = details.get("users_created", 0)
            print(f"   - {photos_deleted} photos deleted")
            print(f"   - {users_deleted} old users deleted") 
            print(f"   - {users_created} new users created")
        else:
            print(f"⚠️  Test user reset failed: {response.status_code} - {response.text}")
            # This might fail if TEST_USERS is not enabled, but we can continue
            
        print("Test user reset complete")
    
    def login_test_user(self) -> str:
        """Login as test user and return access token"""
        print("Logging in as test user...")
        
        response = requests.post(
            f"{BASE_URL}/api/auth/token",
            data=self.test_user_credentials,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        assert response.status_code == 200, f"Login failed: {response.status_code} - {response.text}"
        
        token_data = response.json()
        assert "access_token" in token_data, "No access token in response"
        
        print("✅ Login successful")
        return token_data["access_token"]
    
    def upload_test_photo(self, token: str, location_data: dict, cycle_num: int = 1) -> dict:
        """Upload a test photo with specific location data and return upload response"""
        print(f"Uploading test photo #{cycle_num} ({location_data['description']})...")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create different colored images for each cycle
        colors = ['red', 'blue', 'green', 'yellow', 'purple']
        color = colors[cycle_num - 1] if cycle_num <= len(colors) else 'red'
        
        # Try to create test image with GPS data, fall back to simple image
        try:
            image_data = self.create_test_image_with_gps(location_data, color)
            print(f"   Created {color} test image with GPS data: {location_data['latitude']}, {location_data['longitude']}")
        except Exception as e:
            print(f"   Failed to create GPS image, using simple image: {e}")
            image_data = self.create_simple_test_image()
        
        files = {
            "file": (f"test_photo_{cycle_num}.jpg", image_data, "image/jpeg")
        }
        data = {
            "description": f"Test photo #{cycle_num}: {location_data['description']}",
            "is_public": "true"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/photos/upload",
            headers=headers,
            files=files,
            data=data
        )
        
        assert response.status_code == 200, f"Upload failed: {response.status_code} - {response.text}"
        
        upload_result = response.json()
        assert "photo_id" in upload_result, "No photo_id in upload response"
        
        print(f"✅ Photo #{cycle_num} uploaded successfully: {upload_result['photo_id']}")
        return upload_result
    
    def wait_for_photo_processing(self, token: str, photo_id: str, timeout: int = 240) -> bool:
        """Wait for photo to be processed by checking its status (photo processing needs 3+ minutes)"""
        print(f"Waiting for photo {photo_id} to be processed (this can take 3+ minutes)...")
        
        headers = {"Authorization": f"Bearer {token}"}
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            response = requests.get(
                f"{BASE_URL}/api/photos/{photo_id}",
                headers=headers
            )
            
            if response.status_code == 200:
                photo_data = response.json()
                status = photo_data.get("processing_status", "unknown")
                elapsed = int(time.time() - start_time)
                print(f"   Photo processing status: {status} (elapsed: {elapsed}s)")
                
                if status == "completed":
                    print("✅ Photo processing completed!")
                    # Show photo details
                    lat = photo_data.get("latitude")
                    lon = photo_data.get("longitude") 
                    bearing = photo_data.get("compass_angle")
                    print(f"   Photo coordinates: lat={lat}, lon={lon}, bearing={bearing}")
                    return True
                elif status == "failed":
                    print("❌ Photo processing failed!")
                    return False
            else:
                print(f"   Failed to get photo status: {response.status_code}")
            
            # Wait 10 seconds between checks since processing takes 3+ minutes
            time.sleep(10)
        
        print(f"⏰ Timeout waiting for photo processing after {timeout} seconds")
        return False
    
    def poll_hillview_endpoint(self, token: str, photo_id: str, expected_location: dict, max_attempts: int = 20) -> dict:
        """Poll the hillview endpoint until the uploaded photo appears and verify its data"""
        print("Polling hillview endpoint for uploaded photo...")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Define bounding box around Prague coordinates where our test photo should appear
        bbox_params = {
            'top_left_lat': 50.1,
            'top_left_lon': 14.3,
            'bottom_right_lat': 50.0,
            'bottom_right_lon': 14.5,
            'client_id': 'test_client_reset_upload_poll'
        }
        
        for attempt in range(max_attempts):
            print(f"   Polling attempt {attempt + 1}/{max_attempts}")
            
            response = requests.get(
                f"{BASE_URL}/api/hillview",
                params=bbox_params,
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                photos = data.get('data', [])
                total_count = data.get('total_count', 0)
                
                print(f"   Found {total_count} photos in hillview endpoint")
                
                # Check if our uploaded photo is in the results
                for photo in photos:
                    if photo.get('id') == photo_id:
                        print(f"✅ SUCCESS: Found uploaded photo {photo_id} in hillview endpoint!")
                        
                        # Verify the photo data matches expected location
                        coords = photo.get('geometry', {}).get('coordinates', [])
                        actual_lat = coords[1] if len(coords) > 1 else None
                        actual_lon = coords[0] if len(coords) > 0 else None
                        actual_bearing = photo.get('compass_angle')
                        actual_altitude = photo.get('computed_altitude')
                        
                        print(f"   📍 Expected: lat={expected_location['latitude']}, lon={expected_location['longitude']}, bearing={expected_location['bearing']}, alt={expected_location['altitude']}")
                        print(f"   📍 Actual:   lat={actual_lat}, lon={actual_lon}, bearing={actual_bearing}, alt={actual_altitude}")
                        
                        # Verify coordinates match (with small tolerance for floating point)
                        lat_match = abs(actual_lat - expected_location['latitude']) < 0.001 if actual_lat else False
                        lon_match = abs(actual_lon - expected_location['longitude']) < 0.001 if actual_lon else False
                        bearing_match = abs(actual_bearing - expected_location['bearing']) < 1 if actual_bearing else False
                        altitude_match = abs(actual_altitude - expected_location['altitude']) < 1 if actual_altitude else False
                        
                        if lat_match and lon_match and bearing_match and altitude_match:
                            print(f"   ✅ All GPS data matches expected values!")
                        else:
                            print(f"   ⚠️  GPS data mismatch: lat={lat_match}, lon={lon_match}, bearing={bearing_match}, alt={altitude_match}")
                        
                        return {
                            'success': True,
                            'photo': photo,
                            'data_verified': lat_match and lon_match and bearing_match and altitude_match,
                            'coordinates_match': lat_match and lon_match,
                            'bearing_match': bearing_match,
                            'altitude_match': altitude_match
                        }
                
                print(f"   Photo {photo_id} not yet visible in hillview endpoint")
                # Show first few photos for debugging
                if photos:
                    print("   Currently visible photos:")
                    for i, photo in enumerate(photos[:3]):
                        coords = photo.get('geometry', {}).get('coordinates', [])
                        print(f"     {i+1}. ID: {photo.get('id')}, coords: {coords}")
            else:
                print(f"   Failed to query hillview endpoint: {response.status_code} - {response.text}")
            
            # Wait before next attempt
            if attempt < max_attempts - 1:
                time.sleep(5)
        
        print(f"❌ FAILED: Photo {photo_id} did not appear in hillview endpoint after {max_attempts} attempts")
        return {'success': False, 'photo': None, 'data_verified': False}
    
    def test_complete_workflow(self):
        """Test the complete workflow with 5 upload-poll cycles"""
        print("\n" + "="*80)
        print("🚀 Starting complete workflow test with 5 upload-poll cycles")
        print("="*80)
        
        try:
            # Step 1: Reset test users
            self.reset_test_users()
            
            # Step 2: Login as test user
            token = self.login_test_user()
            
            uploaded_photos = []
            verification_results = []
            
            # Step 3-5: Repeat upload-poll cycle 5 times
            for cycle in range(1, 6):
                print(f"\n{'='*60}")
                print(f"🔄 CYCLE {cycle}/5: {self.test_photo_locations[cycle-1]['description']}")
                print(f"{'='*60}")
                
                location_data = self.test_photo_locations[cycle-1]
                
                # Upload photo with specific location data
                upload_result = self.upload_test_photo(token, location_data, cycle)
                photo_id = upload_result["photo_id"]
                uploaded_photos.append({
                    'cycle': cycle,
                    'photo_id': photo_id,
                    'location': location_data
                })
                
                # Wait for photo processing to complete
                processing_success = self.wait_for_photo_processing(token, photo_id)
                assert processing_success, f"Photo processing failed for cycle {cycle}"
                
                # Poll hillview endpoint and verify data
                polling_result = self.poll_hillview_endpoint(token, photo_id, location_data)
                assert polling_result['success'], f"Photo did not appear in hillview endpoint for cycle {cycle}"
                
                verification_results.append({
                    'cycle': cycle,
                    'photo_id': photo_id,
                    'location': location_data,
                    'verification': polling_result
                })
                
                print(f"✅ Cycle {cycle} completed successfully!")
            
            # Final verification: Check that all 5 photos are visible in the dataset
            print(f"\n{'='*60}")
            print("🔍 FINAL VERIFICATION: Checking all photos in dataset")
            print(f"{'='*60}")
            
            headers = {"Authorization": f"Bearer {token}"}
            bbox_params = {
                'top_left_lat': 50.1,
                'top_left_lon': 14.3,
                'bottom_right_lat': 50.0,
                'bottom_right_lon': 14.5,
                'client_id': 'test_client_final_verification'
            }
            
            response = requests.get(f"{BASE_URL}/api/hillview", params=bbox_params, headers=headers)
            assert response.status_code == 200, "Final verification failed"
            
            data = response.json()
            all_photos = data.get('data', [])
            total_count = data.get('total_count', 0)
            
            print(f"📊 Total photos in dataset: {total_count}")
            print(f"📊 Expected photos: {len(uploaded_photos)}")
            
            # Check each uploaded photo is in the final dataset
            found_photos = []
            for uploaded in uploaded_photos:
                photo_found = False
                for photo in all_photos:
                    if photo.get('id') == uploaded['photo_id']:
                        found_photos.append(uploaded)
                        photo_found = True
                        break
                
                if photo_found:
                    print(f"   ✅ Photo {uploaded['cycle']}: {uploaded['location']['description']} - FOUND")
                else:
                    print(f"   ❌ Photo {uploaded['cycle']}: {uploaded['location']['description']} - MISSING")
                    assert False, f"Photo from cycle {uploaded['cycle']} not found in final dataset"
            
            # Summary of verification results
            print(f"\n{'='*60}")
            print("📋 VERIFICATION SUMMARY")
            print(f"{'='*60}")
            
            all_data_verified = True
            for result in verification_results:
                cycle = result['cycle']
                location = result['location']['description']
                verified = result['verification']['data_verified']
                coords_match = result['verification']['coordinates_match']
                bearing_match = result['verification']['bearing_match']
                altitude_match = result['verification']['altitude_match']
                
                status = "✅ VERIFIED" if verified else "⚠️  PARTIAL"
                print(f"   Photo {cycle} ({location}): {status}")
                print(f"      📍 Coordinates: {'✅' if coords_match else '❌'}")
                print(f"      🧭 Bearing: {'✅' if bearing_match else '❌'}")
                print(f"      🏔️  Altitude: {'✅' if altitude_match else '❌'}")
                
                if not verified:
                    all_data_verified = False
            
            print(f"\n{'='*80}")
            if all_data_verified:
                print("🎉 ALL 5 UPLOAD-POLL CYCLES COMPLETED SUCCESSFULLY!")
                print("🎉 ALL GPS DATA VERIFIED CORRECTLY!")
            else:
                print("✅ ALL 5 UPLOAD-POLL CYCLES COMPLETED!")
                print("⚠️  Some GPS data verification issues found (see details above)")
            print(f"📊 Final dataset contains {len(found_photos)}/{len(uploaded_photos)} uploaded photos")
            print("="*80)
            
        except Exception as e:
            print(f"\n💥 WORKFLOW TEST FAILED: {str(e)}")
            raise
    
    def test_hillview_endpoint_basic(self):
        """Basic test of hillview endpoint functionality"""
        print("\n🔍 Testing basic hillview endpoint functionality...")
        
        # Test without authentication first
        params = {
            'top_left_lat': 50.1,
            'top_left_lon': 14.3,
            'bottom_right_lat': 50.0,
            'bottom_right_lon': 14.5,
            'client_id': 'test_client_basic'
        }
        
        response = requests.get(f"{BASE_URL}/api/hillview", params=params)
        assert response.status_code == 200, f"Hillview endpoint failed: {response.status_code}"
        
        data = response.json()
        assert "data" in data, "Response missing 'data' field"
        assert "total_count" in data, "Response missing 'total_count' field"
        assert "bbox" in data, "Response missing 'bbox' field"
        
        print(f"✅ Hillview endpoint working - found {data['total_count']} photos")

    def test_reset_only(self):
        """Test just the reset functionality"""
        print("\n🔄 Testing reset functionality only...")
        self.reset_test_users()
        print("✅ Reset test completed")

    def test_login_only(self):
        """Test just the login functionality"""
        print("\n🔐 Testing login functionality only...")
        token = self.login_test_user()
        assert len(token) > 0, "Token should not be empty"
        print("✅ Login test completed")


if __name__ == "__main__":
    # Run the 5-cycle upload-poll workflow test
    test_instance = TestResetUploadPoll()
    test_instance.setup_method()
    
    try:
        # Run the multi-cycle workflow test
        test_instance.test_complete_workflow()
        
        print("\n🎉 Multi-cycle workflow test completed successfully!")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 Multi-cycle workflow test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)