#!/usr/bin/env python3
"""
Photo Rating System Integration Tests.
Tests the complete rating system with actual HTTP requests.
"""
import requests
import json
import sys
import os
import pytest

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BaseAuthTest
from utils.test_utils import API_URL, recreate_test_users
from utils.auth_utils import AuthTestHelper

class TestPhotoRatingIntegration(BaseAuthTest):
    """Integration tests for photo rating functionality using proper test base class"""
    
    def setup_method(self):
        """Setup for each test method"""
        super().setup_method()
        self.test_photo_id = "test_photo_for_rating"
        self.test_source = "hillview"
    
    def test_debug_endpoint(self):
        """Test that API is responding"""
        print("\n=== Testing API Debug Endpoint ===")
        response = requests.get(f"{self.api_url}/debug")
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.json()}")
        self.assert_success(response, "API debug endpoint should respond")

    def test_set_thumbs_up_rating(self):
        """Test setting a thumbs up rating"""
        print(f"\n=== Testing Set Thumbs Up Rating ===")
        
        rating_data = {"rating": "thumbs_up"}
        response = requests.post(
            f"{self.api_url}/ratings/{self.test_source}/{self.test_photo_id}",
            json=rating_data,
            headers={**self.test_headers, "Content-Type": "application/json"}
        )
        
        print(f"Set thumbs up - Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            # Verify response structure
            assert "user_rating" in data
            assert "rating_counts" in data
            assert data["user_rating"] == "thumbs_up"
            assert isinstance(data["rating_counts"], dict)
            assert "thumbs_up" in data["rating_counts"]
            assert "thumbs_down" in data["rating_counts"]
            assert data["rating_counts"]["thumbs_up"] >= 1

    def test_get_photo_rating(self):
        """Test getting photo rating information"""
        print(f"\n=== Testing Get Photo Rating ===")
        
        response = requests.get(
            f"{API_URL}/ratings/{self.test_source}/{self.test_photo_id}",
            headers=self.test_headers
        )
        
        print(f"Get rating - Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            # Verify response structure
            assert "user_rating" in data
            assert "rating_counts" in data
            assert isinstance(data["rating_counts"], dict)

    def test_change_to_thumbs_down(self):
        """Test changing rating from thumbs up to thumbs down"""
        print(f"\n=== Testing Change to Thumbs Down ===")
        
        rating_data = {"rating": "thumbs_down"}
        response = requests.post(
            f"{API_URL}/ratings/{self.test_source}/{self.test_photo_id}",
            json=rating_data,
            headers={**self.test_headers, "Content-Type": "application/json"}
        )
        
        print(f"Change to thumbs down - Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            # Verify rating changed
            assert data["user_rating"] == "thumbs_down"
            assert data["rating_counts"]["thumbs_down"] >= 1

    def test_delete_rating(self):
        """Test deleting a photo rating"""
        print(f"\n=== Testing Delete Rating ===")
        
        response = requests.delete(
            f"{API_URL}/ratings/{self.test_source}/{self.test_photo_id}",
            headers=self.test_headers
        )
        
        print(f"Delete rating - Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            # Verify response structure
            assert "message" in data
            assert "rating_counts" in data
            assert "successfully" in data["message"].lower()

    def test_get_rating_after_delete(self):
        """Test getting rating after deletion"""
        print(f"\n=== Testing Get Rating After Delete ===")
        
        response = requests.get(
            f"{API_URL}/ratings/{self.test_source}/{self.test_photo_id}",
            headers=self.test_headers
        )
        
        print(f"Get rating after delete - Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            # Verify no user rating exists
            assert data["user_rating"] is None

    def test_invalid_photo_source(self):
        """Test rating with invalid photo source"""
        print(f"\n=== Testing Invalid Photo Source ===")
        
        rating_data = {"rating": "thumbs_up"}
        response = requests.post(
            f"{API_URL}/ratings/invalid_source/{self.test_photo_id}",
            json=rating_data,
            headers={**self.test_headers, "Content-Type": "application/json"}
        )
        
        print(f"Invalid source - Status: {response.status_code}")
        
        # Should return 400 Bad Request
        assert response.status_code == 400
        
        data = response.json()
        print(f"Error response: {json.dumps(data, indent=2)}")
        assert "Invalid photo source" in data["detail"]
        

    def test_invalid_rating_type(self):
        """Test setting invalid rating type"""
        print(f"\n=== Testing Invalid Rating Type ===")
        
        rating_data = {"rating": "invalid_rating"}
        response = requests.post(
            f"{API_URL}/ratings/{self.test_source}/{self.test_photo_id}",
            json=rating_data,
            headers={**self.test_headers, "Content-Type": "application/json"}
        )
        
        print(f"Invalid rating - Status: {response.status_code}")
        
        # Should return 400 Bad Request
        assert response.status_code == 400
        
        data = response.json()
        print(f"Error response: {json.dumps(data, indent=2)}")
        assert "Invalid rating" in data["detail"]
        

    def test_unauthorized_access(self):
        """Test rating endpoints without authentication"""
        print(f"\n=== Testing Unauthorized Access ===")
        
        # Test without auth header
        rating_data = {"rating": "thumbs_up"}
        response = requests.post(
            f"{API_URL}/ratings/{self.test_source}/{self.test_photo_id}",
            json=rating_data,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"No auth - Status: {response.status_code}")
        assert response.status_code == 401
        
        # Test GET without auth
        response = requests.get(f"{API_URL}/ratings/{self.test_source}/{self.test_photo_id}")
        print(f"Get no auth - Status: {response.status_code}")
        assert response.status_code == 401
        
        # Test DELETE without auth
        response = requests.delete(f"{API_URL}/ratings/{self.test_source}/{self.test_photo_id}")
        print(f"Delete no auth - Status: {response.status_code}")
        assert response.status_code == 401
        

    def test_mapillary_photo_rating(self):
        """Test rating a mapillary photo"""
        print(f"\n=== Testing Mapillary Photo Rating ===")
        
        mapillary_photo_id = "mapillary_test_photo_123"
        rating_data = {"rating": "thumbs_up"}
        
        response = requests.post(
            f"{API_URL}/ratings/mapillary/{mapillary_photo_id}",
            json=rating_data,
            headers={**self.test_headers, "Content-Type": "application/json"}
        )
        
        print(f"Mapillary rating - Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            # Verify rating was set
            assert data["user_rating"] == "thumbs_up"
            assert data["rating_counts"]["thumbs_up"] >= 1
            
            # Clean up - delete the rating
            delete_response = requests.delete(
                f"{API_URL}/ratings/mapillary/{mapillary_photo_id}",
                headers=self.test_headers
            )
            print(f"Cleanup delete - Status: {delete_response.status_code}")

    def run_all_tests(self):
        """Run all integration tests"""
        print("=" * 50)
        print("PHOTO RATING SYSTEM INTEGRATION TESTS")
        print("=" * 50)
        
        tests = [
            self.test_debug_endpoint,
            self.test_unauthorized_access,
            self.test_invalid_photo_source,
            self.test_invalid_rating_type,
        ]
        
        # Only run authenticated tests if we can authenticate
        if self.setup_test_user():
            authenticated_tests = [
                self.test_set_thumbs_up_rating,
                self.test_get_photo_rating,
                self.test_change_to_thumbs_down,
                self.test_delete_rating,
                self.test_get_rating_after_delete,
                self.test_mapillary_photo_rating,
            ]
            tests.extend(authenticated_tests)
        else:
            print("⚠️  Skipping authenticated tests - could not authenticate")
        
        results = []
        for test in tests:
            try:
                result = test()
                results.append((test.__name__, result))
                print(f"✅ {test.__name__}: {'PASS' if result else 'FAIL'}")
            except Exception as e:
                print(f"❌ {test.__name__}: ERROR - {e}")
                results.append((test.__name__, False))
        
        print("\n" + "=" * 50)
        print("TEST RESULTS SUMMARY")
        print("=" * 50)
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name}")
        
        print(f"\nPassed: {passed}/{total}")
        
        if passed == total:
            print("🎉 All tests passed!")
        else:
            print("⚠️  Some tests failed")
            assert False, "Some tests failed"


def main():
    """Run the integration tests"""
    test_runner = PhotoRatingIntegrationTest()
    success = test_runner.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()