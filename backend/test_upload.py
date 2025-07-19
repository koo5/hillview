#!/usr/bin/env python3
"""
Simple test script to verify photo upload functionality works.
"""
import requests
import os
import sys
from pathlib import Path

def test_upload_endpoint():
    """Test the photo upload endpoint."""
    
    # API base URL
    base_url = "http://localhost:8089"
    
    # First, register/login to get a token
    print("Testing photo upload functionality...")
    
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
        response = requests.post(f"{base_url}/api/auth/login", data=login_data)
        
        if response.status_code != 200:
            print(f"✗ Login failed: {response.status_code} - {response.text}")
            return False
        
        token_data = response.json()
        access_token = token_data["access_token"]
        print("✓ Login successful")
        
        # Test photo upload
        print("Testing photo upload...")
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Create a test image file (simple 1x1 pixel JPEG)
        test_image_path = "/tmp/test_photo.jpg"
        create_test_image(test_image_path)
        
        files = {"file": ("test_photo.jpg", open(test_image_path, "rb"), "image/jpeg")}
        data = {
            "description": "Test photo upload",
            "is_public": "true"
        }
        
        response = requests.post(
            f"{base_url}/api/photos/upload",
            headers=headers,
            files=files,
            data=data
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Photo upload successful! Task ID: {result['task_id']}")
            
            # Check task status
            task_id = result["task_id"]
            print(f"Checking task status for {task_id}...")
            
            import time
            for i in range(10):  # Check for up to 10 seconds
                status_response = requests.get(
                    f"{base_url}/api/photos/upload/status/{task_id}",
                    headers=headers
                )
                
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    print(f"Task status: {status_data['state']} - {status_data.get('status', 'No status')}")
                    
                    if status_data['state'] in ['SUCCESS', 'FAILURE']:
                        break
                        
                    time.sleep(1)
                else:
                    print(f"✗ Failed to get task status: {status_response.status_code}")
                    break
            
            return True
        else:
            print(f"✗ Photo upload failed: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("✗ Could not connect to API. Make sure the server is running on localhost:8089")
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
    success = test_upload_endpoint()
    sys.exit(0 if success else 1)