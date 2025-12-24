#!/usr/bin/env python3
"""
Simple test script to verify photo upload functionality works.
"""
import asyncio
import pytest
import requests
import os
import sys
from pathlib import Path

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BasePhotoTest
from utils.secure_upload_utils import SecureUploadClient
from utils.test_utils import API_URL
from utils.image_utils import create_test_image_full_gps

class TestUpload(BasePhotoTest):
    """Test photo upload functionality using secure upload workflow."""
    
    @pytest.mark.asyncio
    async def test_upload_endpoint(self):
        """Test the photo upload endpoint using secure upload workflow."""
        
        # Initialize test_image_path to None
        test_image_path = None
        
        print("Testing photo upload functionality with secure workflow...")
        
        try:
            # Create a test image file (simple test JPEG)
            test_image_path = "/tmp/test_photo.jpg"
            create_test_image_file(test_image_path)
            
            # Read image data
            with open(test_image_path, 'rb') as f:
                image_data = f.read()
            
            # Use secure upload workflow
            upload_client = SecureUploadClient(api_url=API_URL)
            
            # Phase 1: Generate and register client keys
            print("Phase 1: Registering client keys...")
            client_keys = upload_client.generate_client_keys()
            await upload_client.register_client_key(self.test_token, client_keys)
            print("✓ Client keys registered")
            
            # Phase 2: Authorize upload
            print("Phase 2: Authorizing upload...")
            auth_data = await upload_client.authorize_upload_with_params(
                self.test_token, "test_photo.jpg", len(image_data),
                50.0755, 14.4378,  # Prague coordinates
                "Test photo upload", True  # is_public
            )
            print("✓ Upload authorized")
            
            # Phase 3: Upload to worker
            print("Phase 3: Uploading to worker...")
            result = await upload_client.upload_to_worker(image_data, auth_data, client_keys, "test_photo.jpg")
            photo_id = result.get('photo_id', auth_data.get('photo_id', 'unknown'))
            print(f"✓ Photo upload successful! Photo ID: {photo_id}")
            
            # Wait for processing
            print("Waiting for photo processing...")
            import time
            
            for i in range(30):  # Check for up to 30 seconds
                status_response = requests.get(
                    f"{API_URL}/photos/{photo_id}",
                    headers=self.test_headers
                )
                
                if status_response.status_code == 200:
                    photo_data = status_response.json()
                    status = photo_data.get('processing_status', 'unknown')
                    print(f"Processing status: {status}")
                    
                    if status in ['completed', 'failed']:
                        if status == 'completed':
                            print("✓ Photo processing completed successfully!")
                            break
                        else:
                            pytest.fail("Photo processing failed")
                        
                time.sleep(1)
            else:
                pytest.fail("Photo processing timed out after 30 seconds")
            
            # Verify photo exists in API
            print("Verifying photo in API...")
            photo_response = requests.get(
                f"{API_URL}/photos/{photo_id}",
                headers=self.test_headers
            )
            
            self.assert_success(photo_response, "Should be able to retrieve uploaded photo")
            
            photo_info = photo_response.json()
            assert photo_info.get('id') == photo_id, "Photo ID should match"
            assert photo_info.get('processing_status') == 'completed', "Photo should be processed"
            print("✓ Photo verified in API")
            
        except Exception as e:
            pytest.fail(f"Upload test failed: {str(e)}")
        finally:
            # Cleanup test image
            if test_image_path and os.path.exists(test_image_path):
                os.unlink(test_image_path)
                print("✓ Test image file cleaned up")

def create_test_image_file(filepath):
    """Create a test JPEG image file with full GPS data including bearing."""
    # Create image with GPS coordinates AND bearing (Prague coordinates, 90° bearing)
    image_data = create_test_image_full_gps(200, 150, (255, 0, 0), lat=50.0755, lon=14.4378, bearing=90.0)
    with open(filepath, 'wb') as f:
        f.write(image_data)
    print(f"✓ Created test image file with GPS+bearing: {filepath}")

if __name__ == "__main__":
    # Run the test
    test = TestUpload()
    test.setUp()
    asyncio.run(test.test_upload_endpoint())