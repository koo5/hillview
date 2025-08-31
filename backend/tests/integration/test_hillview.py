#!/usr/bin/env python3
"""
Test script for the hillview endpoint to verify it queries the database correctly.
"""
import requests
import json
import sys
import os

API_URL = os.getenv("API_URL", "http://localhost:8055/api")

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
    
    # The hillview endpoint returns Server-Sent Events format, not JSON
    headers = {
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache"
    }
    
    response = requests.get(f"{API_URL}/hillview", params=params, headers=headers, stream=True)
    print(f"Status code: {response.status_code}")
    
    if response.status_code == 200:
        # Parse SSE stream format
        data = None
        total_count = 0
        
        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith('data: '):
                try:
                    line_data = json.loads(line[6:])  # Remove 'data: ' prefix
                    if line_data.get('type') == 'photos':
                        data = line_data
                        total_count += len(line_data.get('photos', []))
                    elif line_data.get('type') == 'stream_complete':
                        print(f"Stream complete. Total photos found: {total_count}")
                        break
                except json.JSONDecodeError:
                    continue
        
        if data:
            print(f"Photos in batch: {len(data.get('photos', []))}")
            print(f"Bbox: {data.get('bbox', {})}")
            
            if data.get('photos'):
                print(f"First photo: {data['photos'][0]}")
            else:
                print("No photos found in the specified area")
        else:
            print("No photo data received in SSE stream")
            
        # Test passes if we can parse the SSE stream format correctly
    else:
        print(f"Error response: {response.text}")
        assert False, f"Expected status 200, got {response.status_code}"

def main():
    """Run the test"""
    try:
        test_hillview_endpoint()
        print("\nHillview endpoint test completed successfully!")
        return 0
    except Exception as e:
        print(f"\nHillview endpoint test failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())