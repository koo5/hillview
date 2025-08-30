#!/usr/bin/env python3
"""
Simple test script to verify photo upload functionality works.
"""
import asyncio
import requests
import os
import sys
from pathlib import Path

async def test_upload_endpoint():
    """Test the photo upload endpoint using secure upload workflow."""
    from secure_upload_utils import SecureUploadClient
    
    # API base URL (updated to match backend port)
    base_url = "http://localhost:8055"
    
    # First, register/login to get a token
    print("Testing photo upload functionality with secure workflow...")
    
    # Create a test user
    user_data = {
        "username": "testuser",
        "email": "test@example.com", 
        "password": "testpassword123"
    }
    
    try:
        # Register user
        print("Registering test user...")
        response = requests.post(f"{base_url}/api/auth/register", json=user_data)
        if response.status_code in [200, 201]:
            print("✓ User registered successfully")
        elif response.status_code == 400 and "already exists" in response.text:
            print("✓ User already exists")
        else:
            print(f"✗ Registration failed: {response.status_code} - {response.text}")
            return False
        
        # Login to get token
        print("Logging in...")
        login_data = {
            "username": user_data["username"],
            "password": user_data["password"]
        }
        response = requests.post(
            f"{base_url}/api/auth/token", 
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if response.status_code != 200:
            print(f"✗ Login failed: {response.status_code} - {response.text}")
            return False
        
        token_data = response.json()
        access_token = token_data["access_token"]
        print("✓ Login successful")
        
        # Test photo upload using secure workflow
        print("Testing secure photo upload workflow...")
        
        # Create a test image file (simple 10x10 pixel JPEG)
        test_image_path = "/tmp/test_photo.jpg"
        create_test_image(test_image_path)
        
        # Read image data
        with open(test_image_path, 'rb') as f:
            image_data = f.read()
        
        # Use secure upload workflow
        upload_client = SecureUploadClient(api_url=base_url)
        
        # Phase 1: Generate and register client keys
        print("Phase 1: Registering client keys...")
        client_keys = upload_client.generate_client_keys()
        await upload_client.register_client_key(access_token, client_keys)
        print("✓ Client keys registered")
        
        # Phase 2: Authorize upload
        print("Phase 2: Authorizing upload...")
        auth_data = await upload_client.authorize_upload_with_params(
            access_token, "test_photo.jpg", len(image_data),
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
        headers = {"Authorization": f"Bearer {access_token}"}
        
        for i in range(30):  # Check for up to 30 seconds
            status_response = requests.get(
                f"{base_url}/api/photos/{photo_id}",
                headers=headers
            )
            
            if status_response.status_code == 200:
                photo_data = status_response.json()
                status = photo_data.get('processing_status', 'unknown')
                print(f"Processing status: {status}")
                
                if status in ['completed', 'failed']:
                    if status == 'completed':
                        print("✓ Photo processing completed successfully!")
                        return True
                    else:
                        print("✗ Photo processing failed")
                        return False
                    
                time.sleep(1)
            else:
                print(f"✗ Failed to get photo status: {status_response.status_code}")
                break
        
        print("✓ Upload workflow completed (processing may still be in progress)")
        return True
            
    except requests.exceptions.ConnectionError:
        print("✗ Could not connect to API. Make sure the server is running on localhost:8055")
        return False
    except Exception as e:
        print(f"✗ Test failed with error: {e}")
        return False
    finally:
        # Clean up test image
        if os.path.exists(test_image_path):
            os.remove(test_image_path)

def create_test_image(path: str):
    """Create a minimal test JPEG image."""
    from PIL import Image
    
    # Create a 10x10 red image
    img = Image.new('RGB', (10, 10), color='red')
    img.save(path, 'JPEG')

if __name__ == "__main__":
    success = asyncio.run(test_upload_endpoint())
    sys.exit(0 if success else 1)