#!/usr/bin/env python3
"""
Simple test script to verify the API is working correctly.
"""
import requests
import json
import sys
import os

API_URL = os.getenv("API_URL", "http://localhost:8055/api")

def test_debug_endpoint():
    """Test the debug endpoint"""
    print("Testing debug endpoint...")
    response = requests.get(f"{API_URL}/debug")
    print(f"Status code: {response.status_code}")
    print(f"Response: {response.json()}")
    return response.status_code == 200

def test_register_user():
    """Test user registration"""
    print("\nTesting user registration...")
    test_user = {
        "email": "test@example.com",
        "username": "testuser",
        "password": "password123"
    }
    
    response = requests.post(
        f"{API_URL}/auth/register",
        json=test_user,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"Status code: {response.status_code}")
    try:
        print(f"Response: {response.json()}")
    except:
        print(f"Response text: {response.text}")
    
    return response.status_code in (200, 201, 400)  # 400 is ok if user already exists

def test_login():
    """Test user login"""
    print("\nTesting user login...")
    login_data = {
        "username": "testuser",
        "password": "password123"
    }
    
    response = requests.post(
        f"{API_URL}/auth/token",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    
    print(f"Status code: {response.status_code}")
    try:
        print(f"Response: {response.json()}")
    except:
        print(f"Response text: {response.text}")
    
    return response.status_code == 200

def main():
    """Run all tests"""
    tests = [
        test_debug_endpoint,
        test_register_user,
        test_login
    ]
    
    success = True
    for test in tests:
        if not test():
            success = False
    
    if success:
        print("\nAll tests passed!")
        return 0
    else:
        print("\nSome tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
