#!/usr/bin/env python3
"""
Photo Rating System Integration Tests.
Tests the complete rating system with proper test infrastructure.
"""
import requests
import json
import pytest
import sys
import os

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BaseAuthTest
from utils.test_utils import API_URL, recreate_test_users
from utils.auth_utils import AuthTestHelper


class TestPhotoRatingSystem(BaseAuthTest):
    """Integration tests for photo rating functionality using proper test infrastructure"""
    
    def setup_method(self):
        """Setup for each test method"""
        super().setup_method()
        self.test_photo_id = "integration_test_photo_123"
        self.hillview_source = "hillview"
        self.mapillary_source = "mapillary"
    
    def test_api_availability(self):
        """Test that the API and rating endpoints are available"""
        print("\n=== Testing API Availability ===")
        response = requests.get(f"{self.api_url}/debug")
        self.assert_success(response, "API should be available")
        
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"
    
    def test_unauthorized_rating_access(self):
        """Test that rating endpoints require authentication"""
        print("\n=== Testing Unauthorized Access ===")
        
        # Test GET without auth
        response = requests.get(f"{self.api_url}/ratings/{self.hillview_source}/{self.test_photo_id}")
        self.assert_unauthorized(response, "GET rating should require auth")
        
        # Test POST without auth  
        rating_data = {"rating": "thumbs_up"}
        response = requests.post(
            f"{self.api_url}/ratings/{self.hillview_source}/{self.test_photo_id}",
            json=rating_data,
            headers={"Content-Type": "application/json"}
        )
        self.assert_unauthorized(response, "POST rating should require auth")
        
        # Test DELETE without auth
        response = requests.delete(f"{self.api_url}/ratings/{self.hillview_source}/{self.test_photo_id}")
        self.assert_unauthorized(response, "DELETE rating should require auth")
    
    def test_invalid_photo_source_validation(self):
        """Test validation of photo source parameter"""
        print("\n=== Testing Photo Source Validation ===")
        
        # Non-empty invalid sources should return 400 with validation error
        invalid_sources = ["invalid", "facebook", "instagram"]
        
        for invalid_source in invalid_sources:
            response = requests.post(
                f"{self.api_url}/ratings/{invalid_source}/{self.test_photo_id}",
                json={"rating": "thumbs_up"},
                headers={**self.test_headers, "Content-Type": "application/json"}
            )
            
            self.assert_bad_request(response, f"Invalid source '{invalid_source}' should be rejected")
            
            data = response.json()
            assert "Invalid photo source" in data["detail"]
        
        # Empty string source should return 404 due to FastAPI routing
        response = requests.post(
            f"{self.api_url}/ratings//{self.test_photo_id}",
            json={"rating": "thumbs_up"},
            headers={**self.test_headers, "Content-Type": "application/json"}
        )
        
        assert response.status_code == 404, f"Empty source should return 404 - Got {response.status_code}"
    
    def test_invalid_rating_type_validation(self):
        """Test validation of rating type parameter"""
        print("\n=== Testing Rating Type Validation ===")
        
        invalid_ratings = ["like", "dislike", "love", "hate", "", "neutral"]
        
        for invalid_rating in invalid_ratings:
            response = requests.post(
                f"{self.api_url}/ratings/{self.hillview_source}/{self.test_photo_id}",
                json={"rating": invalid_rating},
                headers={**self.test_headers, "Content-Type": "application/json"}
            )
            
            self.assert_bad_request(response, f"Invalid rating '{invalid_rating}' should be rejected")
            
            data = response.json()
            assert "Invalid rating" in data["detail"]
    
    def test_hillview_photo_rating_workflow(self):
        """Test complete rating workflow for Hillview photos"""
        print("\n=== Testing Hillview Photo Rating Workflow ===")
        
        # 1. Check initial state (should have no rating)
        response = requests.get(
            f"{self.api_url}/ratings/{self.hillview_source}/{self.test_photo_id}",
            headers=self.test_headers
        )
        self.assert_success(response, "Should be able to get rating info")
        
        initial_data = response.json()
        assert "user_rating" in initial_data
        assert "rating_counts" in initial_data
        assert initial_data["user_rating"] is None
        assert isinstance(initial_data["rating_counts"], dict)
        assert "thumbs_up" in initial_data["rating_counts"]
        assert "thumbs_down" in initial_data["rating_counts"]
        
        print(f"Initial state: {json.dumps(initial_data, indent=2)}")
        
        # 2. Set thumbs up rating
        response = requests.post(
            f"{self.api_url}/ratings/{self.hillview_source}/{self.test_photo_id}",
            json={"rating": "thumbs_up"},
            headers={**self.test_headers, "Content-Type": "application/json"}
        )
        self.assert_success(response, "Should be able to set thumbs up rating")
        
        thumbs_up_data = response.json()
        assert thumbs_up_data["user_rating"] == "thumbs_up"
        assert thumbs_up_data["rating_counts"]["thumbs_up"] >= 1
        
        print(f"After thumbs up: {json.dumps(thumbs_up_data, indent=2)}")
        
        # 3. Change to thumbs down rating
        response = requests.post(
            f"{self.api_url}/ratings/{self.hillview_source}/{self.test_photo_id}",
            json={"rating": "thumbs_down"},
            headers={**self.test_headers, "Content-Type": "application/json"}
        )
        self.assert_success(response, "Should be able to change to thumbs down rating")
        
        thumbs_down_data = response.json()
        assert thumbs_down_data["user_rating"] == "thumbs_down"
        assert thumbs_down_data["rating_counts"]["thumbs_down"] >= 1
        # Note: thumbs_up count might not decrease if there are other users' ratings
        
        print(f"After thumbs down: {json.dumps(thumbs_down_data, indent=2)}")
        
        # 4. Remove rating
        response = requests.delete(
            f"{self.api_url}/ratings/{self.hillview_source}/{self.test_photo_id}",
            headers=self.test_headers
        )
        self.assert_success(response, "Should be able to delete rating")
        
        delete_data = response.json()
        assert "message" in delete_data
        assert "rating_counts" in delete_data
        assert "successfully" in delete_data["message"].lower()
        
        print(f"After deletion: {json.dumps(delete_data, indent=2)}")
        
        # 5. Verify rating is removed
        response = requests.get(
            f"{self.api_url}/ratings/{self.hillview_source}/{self.test_photo_id}",
            headers=self.test_headers
        )
        self.assert_success(response, "Should be able to get rating info after deletion")
        
        final_data = response.json()
        assert final_data["user_rating"] is None
        
        print(f"Final state: {json.dumps(final_data, indent=2)}")
    
    def test_mapillary_photo_rating_workflow(self):
        """Test complete rating workflow for Mapillary photos"""
        print("\n=== Testing Mapillary Photo Rating Workflow ===")
        
        mapillary_photo_id = "mapillary_test_photo_456"
        
        # Test basic rating operations for Mapillary photos
        response = requests.post(
            f"{self.api_url}/ratings/{self.mapillary_source}/{mapillary_photo_id}",
            json={"rating": "thumbs_up"},
            headers={**self.test_headers, "Content-Type": "application/json"}
        )
        self.assert_success(response, "Should be able to rate Mapillary photos")
        
        data = response.json()
        assert data["user_rating"] == "thumbs_up"
        assert data["rating_counts"]["thumbs_up"] >= 1
        
        print(f"Mapillary rating: {json.dumps(data, indent=2)}")
        
        # Cleanup
        requests.delete(
            f"{self.api_url}/ratings/{self.mapillary_source}/{mapillary_photo_id}",
            headers=self.test_headers
        )
    
    def test_multiple_users_rating_same_photo(self):
        """Test multiple users rating the same photo"""
        print("\n=== Testing Multiple Users Rating Same Photo ===")
        
        # Clear token cache to ensure fresh tokens
        self.__class__.auth_helper.clear_token_cache()
        
        # Get tokens for different users
        test_token, admin_token = self.get_different_user_tokens()
        test_headers = self.get_auth_headers(test_token)
        admin_headers = self.get_auth_headers(admin_token)
        
        shared_photo_id = "shared_photo_for_multi_user_test"
        
        # User 1 rates thumbs up
        response = requests.post(
            f"{self.api_url}/ratings/{self.hillview_source}/{shared_photo_id}",
            json={"rating": "thumbs_up"},
            headers={**test_headers, "Content-Type": "application/json"}
        )
        self.assert_success(response, "User 1 should be able to rate")
        
        user1_data = response.json()
        assert user1_data["user_rating"] == "thumbs_up"
        user1_thumbs_up_count = user1_data["rating_counts"]["thumbs_up"]
        
        # User 2 rates thumbs down
        response = requests.post(
            f"{self.api_url}/ratings/{self.hillview_source}/{shared_photo_id}",
            json={"rating": "thumbs_down"},
            headers={**admin_headers, "Content-Type": "application/json"}
        )
        self.assert_success(response, "User 2 should be able to rate")
        
        user2_data = response.json()
        assert user2_data["user_rating"] == "thumbs_down"
        assert user2_data["rating_counts"]["thumbs_down"] >= 1
        # thumbs_up count should be same or higher (user 1's rating)
        assert user2_data["rating_counts"]["thumbs_up"] >= user1_thumbs_up_count
        
        print(f"Multi-user ratings: {json.dumps(user2_data, indent=2)}")
        
        # Verify each user sees their own rating
        response = requests.get(
            f"{self.api_url}/ratings/{self.hillview_source}/{shared_photo_id}",
            headers=test_headers
        )
        self.assert_success(response, "User 1 should see their rating")
        user1_view = response.json()
        assert user1_view["user_rating"] == "thumbs_up"
        
        response = requests.get(
            f"{self.api_url}/ratings/{self.hillview_source}/{shared_photo_id}",
            headers=admin_headers
        )
        self.assert_success(response, "User 2 should see their rating")
        user2_view = response.json()
        assert user2_view["user_rating"] == "thumbs_down"
        
        # Cleanup
        requests.delete(f"{self.api_url}/ratings/{self.hillview_source}/{shared_photo_id}", headers=test_headers)
        requests.delete(f"{self.api_url}/ratings/{self.hillview_source}/{shared_photo_id}", headers=admin_headers)
    
    def test_rating_same_photo_twice(self):
        """Test that rating the same photo twice updates the existing rating"""
        print("\n=== Testing Rating Same Photo Twice ===")
        
        duplicate_photo_id = "duplicate_rating_test_photo"
        
        # First rating
        response = requests.post(
            f"{self.api_url}/ratings/{self.hillview_source}/{duplicate_photo_id}",
            json={"rating": "thumbs_up"},
            headers={**self.test_headers, "Content-Type": "application/json"}
        )
        self.assert_success(response, "First rating should succeed")
        first_data = response.json()
        
        # Second rating (should update, not create duplicate)
        response = requests.post(
            f"{self.api_url}/ratings/{self.hillview_source}/{duplicate_photo_id}",
            json={"rating": "thumbs_down"},
            headers={**self.test_headers, "Content-Type": "application/json"}
        )
        self.assert_success(response, "Second rating should update existing")
        second_data = response.json()
        
        assert second_data["user_rating"] == "thumbs_down"
        print(f"Updated rating: {json.dumps(second_data, indent=2)}")
        
        # Cleanup
        requests.delete(f"{self.api_url}/ratings/{self.hillview_source}/{duplicate_photo_id}", headers=self.test_headers)
    
    def test_delete_nonexistent_rating(self):
        """Test deleting a rating that doesn't exist"""
        print("\n=== Testing Delete Nonexistent Rating ===")
        
        nonexistent_photo_id = "photo_with_no_rating_12345"
        
        response = requests.delete(
            f"{self.api_url}/ratings/{self.hillview_source}/{nonexistent_photo_id}",
            headers=self.test_headers
        )
        
        # Should return 404 for nonexistent rating
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
        
        print(f"Expected 404 response: {json.dumps(data, indent=2)}")
    
    def test_malformed_requests(self):
        """Test handling of malformed requests"""
        print("\n=== Testing Malformed Requests ===")
        
        # Missing rating field
        response = requests.post(
            f"{self.api_url}/ratings/{self.hillview_source}/{self.test_photo_id}",
            json={},
            headers={**self.test_headers, "Content-Type": "application/json"}
        )
        assert response.status_code in [400, 422]  # Bad request or validation error
        
        # Invalid JSON
        response = requests.post(
            f"{self.api_url}/ratings/{self.hillview_source}/{self.test_photo_id}",
            data="invalid json",
            headers={**self.test_headers, "Content-Type": "application/json"}
        )
        assert response.status_code in [400, 422]  # Bad request or validation error
        
        # Extra fields (should still work)
        response = requests.post(
            f"{self.api_url}/ratings/{self.hillview_source}/{self.test_photo_id}",
            json={"rating": "thumbs_up", "extra_field": "should_be_ignored"},
            headers={**self.test_headers, "Content-Type": "application/json"}
        )
        # This should succeed (extra fields ignored)
        if response.status_code == 200:
            # Cleanup if it worked
            requests.delete(f"{self.api_url}/ratings/{self.hillview_source}/{self.test_photo_id}", headers=self.test_headers)


def run_manual_test():
    """Manual test runner for debugging"""
    print("Running Photo Rating Integration Tests")
    print("=" * 50)
    
    # Ensure test users exist
    recreate_test_users()
    
    # Create test instance
    test = TestPhotoRatingSystem()
    test.setup_method()
    
    # Run tests manually
    test_methods = [
        test.test_api_availability,
        test.test_unauthorized_rating_access,
        test.test_invalid_photo_source_validation,
        test.test_invalid_rating_type_validation,
        test.test_hillview_photo_rating_workflow,
        test.test_mapillary_photo_rating_workflow,
        test.test_multiple_users_rating_same_photo,
        test.test_rating_same_photo_twice,
        test.test_delete_nonexistent_rating,
        test.test_malformed_requests,
    ]
    
    results = []
    for test_method in test_methods:
        try:
            test_method()
            results.append((test_method.__name__, True))
            print(f"✅ {test_method.__name__}: PASS")
        except Exception as e:
            results.append((test_method.__name__, False))
            print(f"❌ {test_method.__name__}: FAIL - {e}")
    
    # Summary
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"\nResults: {passed}/{total} tests passed")
    return passed == total


if __name__ == "__main__":
    # Run tests directly for debugging
    success = run_manual_test()
    sys.exit(0 if success else 1)