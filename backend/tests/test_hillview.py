#!/usr/bin/env python3
"""
Test script for the hillview endpoint to verify it queries the database correctly.
"""
import requests
import json
import sys

BASE_URL = "http://localhost:8089"

def test_hillview_endpoint():
    """Test the hillview endpoint with database queries"""
    print("Testing hillview endpoint...")
    
    # Test with Prague coordinates (approximate bounding box)
    params = {
        'top_left_lat': 50.1,
        'top_left_lon': 14.3,
        'bottom_right_lat': 50.0,
        'bottom_right_lon': 14.5,
        'client_id': 'test_client'
    }
    
    response = requests.get(f"{BASE_URL}/api/hillview", params=params)
    print(f"Status code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Total photos found: {data.get('total_count', 0)}")
        print(f"Bbox: {data.get('bbox', {})}")
        
        if data.get('data'):
            print(f"First photo: {data['data'][0]}")
        else:
            print("No photos found in the specified area")
            
        return True
    else:
        print(f"Error response: {response.text}")
        return False

def main():
    """Run the test"""
    if test_hillview_endpoint():
        print("\nHillview endpoint test completed successfully!")
        return 0
    else:
        print("\nHillview endpoint test failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())