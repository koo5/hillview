#!/usr/bin/env python3
"""
Debug script to understand the filtering issue.
"""

import requests
import os

API_URL = os.getenv("API_URL", "http://localhost:8055/api")

def main():
    print("=== DEBUG FILTERING ISSUE ===")
    
    # Create a test user
    user_data = {
        "username": "debug_filter_user",
        "email": "debug_filter@test.com", 
        "password": "StrongDebugPassword123!"
    }
    
    # Register user
    response = requests.post(f"{API_URL}/auth/register", json=user_data)
    if response.status_code not in [200, 400]:
        print(f"Registration failed: {response.status_code}")
        return
    
    # Login
    login_data = {
        "username": user_data["username"],
        "password": user_data["password"]
    }
    response = requests.post(
        f"{API_URL}/auth/token",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    
    if response.status_code != 200:
        print(f"Login failed: {response.status_code}")
        return
        
    token = response.json()["access_token"]
    print(f"✓ Logged in, token: {token[:20]}...")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Query hillview photos before hiding
    params = {
        "top_left_lat": 50.1,
        "top_left_lon": 14.3,
        "bottom_right_lat": 50.0,
        "bottom_right_lon": 14.5,
        "client_id": "debug_client"
    }
    
    print(f"Sending request with headers: {headers}")
    response = requests.get(f"{API_URL}/hillview", params=params, headers=headers)
    print(f"Hillview response status: {response.status_code}")
    print(f"Hillview response content: {response.text[:200]}")
    
    # If we have photos, try to hide one
    if response.status_code == 200 and "photos" in response.text:
        # Parse the SSE response roughly
        content = response.text
        if '"id"' in content:
            # Extract first photo ID (very rough parsing)
            import re
            photo_id_match = re.search(r'"id"\s*:\s*"([^"]+)"', content)
            if photo_id_match:
                photo_id = photo_id_match.group(1)
                print(f"Found photo ID: {photo_id}")
                
                # Hide the photo
                hide_request = {
                    "photo_source": "hillview",
                    "photo_id": photo_id,
                    "reason": "Debug test"
                }
                
                hide_response = requests.post(
                    f"{API_URL}/hidden/photos",
                    json=hide_request,
                    headers=headers
                )
                
                print(f"Hide response status: {hide_response.status_code}")
                print(f"Hide response: {hide_response.json()}")
                
                # Query hidden photos to verify it was stored
                hidden_list_response = requests.get(
                    f"{API_URL}/hidden/photos",
                    headers=headers
                )
                print(f"Hidden photos list status: {hidden_list_response.status_code}")
                print(f"Hidden photos list: {hidden_list_response.json()}")
                
                # Query hillview photos again to see if filtering works
                response2 = requests.get(f"{API_URL}/hillview", params=params, headers=headers)
                print(f"Hillview after hiding status: {response2.status_code}")
                print(f"Hillview after hiding content: {response2.text[:200]}")
                
                # Check if the hidden photo still appears
                if photo_id in response2.text:
                    print(f"❌ PROBLEM: Photo {photo_id} still appears after hiding!")
                else:
                    print(f"✓ SUCCESS: Photo {photo_id} is properly filtered out!")
    
    return 0

if __name__ == "__main__":
    exit(main())