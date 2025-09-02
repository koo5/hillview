#!/usr/bin/env python3
"""
Tests for hidden content filtering logic.

Tests how hidden photos and users are filtered out of API responses:
- Hillview API filtering
- Mapillary API filtering  
- Activity feed filtering
- Photo list filtering
- Integration with authentication
"""

import requests
import json
import time
import os
import sys
import pytest
import asyncio
from datetime import datetime

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BaseUserManagementTest
from utils.test_utils import query_hillview_endpoint, create_test_photos
from utils.auth_utils import auth_helper

# Test configuration
API_URL = os.getenv("API_URL", "http://localhost:8055/api")

class TestContentFiltering(BaseUserManagementTest):
    """Test suite for hidden content filtering in API responses."""
    
    def test_hillview_filtering_hidden_photos(self):
        """Test that hidden photos are filtered from Hillview API."""
        print("\n--- Testing Hillview Photo Filtering ---")
        
        # First, get baseline results without any hidden content
        params = {
            "top_left_lat": 50.1,
            "top_left_lon": 14.3,
            "bottom_right_lat": 50.0,
            "bottom_right_lon": 14.5,
            "client_id": "test_filter_client"
        }
        
        baseline_result = query_hillview_endpoint(
            token=self.test_token, 
            params=params
        )
        
        assert baseline_result is not None, "Hillview API call failed"
        
        baseline_count = len(baseline_result.get("data", []))
        print(f"Baseline: {baseline_count} photos found")
        
        # Hide a photo (using a known photo ID if available)
        if baseline_count > 0:
            photo_to_hide = baseline_result["data"][0]["id"]
            
            hide_request = {
                "photo_source": "hillview",
                "photo_id": photo_to_hide,
                "reason": "Test filtering"
            }
            
            response = requests.post(
                f"{API_URL}/hidden/photos",
                json=hide_request,
                headers=self.test_headers
            )
            
            assert response.status_code == 200, f"Failed to hide photo: {response.status_code}"
            
            print(f"✓ Hidden photo: {photo_to_hide}")
            
            # Query again - should have one less photo
            filtered_result = query_hillview_endpoint(
                token=self.test_token, 
                params=params
            )
            
            assert filtered_result is not None, "Filtered query failed"
            
            filtered_count = len(filtered_result.get("data", []))
            
            # Verify the hidden photo is not in results
            photo_ids = [photo["id"] for photo in filtered_result.get("data", [])]
            
            assert photo_to_hide not in photo_ids, "Hidden photo still appears in results"
            
            print(f"✓ Hidden photo filtered out ({baseline_count} -> {filtered_count})")
            
            # Clean up - unhide the photo
            unhide_request = {
                "photo_source": "hillview",
                "photo_id": photo_to_hide
            }
            requests.delete(
                f"{API_URL}/hidden/photos",
                json=unhide_request,
                headers=self.test_headers
            )
        else:
            print("ℹ No photos available to test filtering - test passes")
    
    def test_activity_feed_filtering(self):
        """Test that hidden content is filtered from activity feed."""
        print("\n--- Testing Activity Feed Filtering ---")
        
        # Create test data - ensure we have photos from both users for testing
        print("Creating test photos for activity feed filtering...")
        
        # Create test photos that will appear in activity feed
        photos_created = self.create_test_photos(self.test_users, self.auth_tokens)
        assert photos_created > 0, "Failed to create test photos for activity feed test"
        
        # Wait a moment for activity feed to update
        import time
        time.sleep(2)
        
        # Get baseline activity feed
        response = requests.get(
            f"{API_URL}/activity/recent",
            headers=self.test_headers
        )
        
        assert response.status_code == 200, f"Activity API call failed: {response.status_code} - {response.text}"
        
        baseline_activities = response.json()
        baseline_count = len(baseline_activities)
        print(f"Baseline activity: {baseline_count} items")
        
        # We should now have activity items from our test photos
        assert baseline_count > 0, f"Expected activity items after creating {photos_created} photos, but found {baseline_count}"
        
        # Get the owner_id from admin user (we'll hide admin's photos from test user's perspective)
        # First, get admin user's ID by checking their profile
        admin_profile_response = requests.get(
            f"{API_URL}/user/profile",
            headers=self.admin_headers
        )
        assert admin_profile_response.status_code == 200, "Failed to get admin profile"
        admin_user_id = admin_profile_response.json()["id"]
        
        # Hide admin from test user's perspective
        hide_request = {
            "target_user_source": "hillview", 
            "target_user_id": admin_user_id,
            "reason": "Test activity filtering"
        }
        
        response = requests.post(
            f"{API_URL}/hidden/users",
            json=hide_request,
            headers=self.test_headers
        )
        
        assert response.status_code == 200, f"Failed to hide user: {response.status_code} - {response.text}"
        print(f"✓ Hidden user: {admin_user_id}")
        
        # Query activity again - should filter out admin's photos
        response = requests.get(
            f"{API_URL}/activity/recent",
            headers=self.test_headers
        )
        
        assert response.status_code == 200, f"Filtered activity query failed: {response.status_code}"
        
        filtered_activities = response.json()
        filtered_count = len(filtered_activities)
        
        # Check if activities from hidden user are removed
        hidden_user_activities = [
            item for item in filtered_activities 
            if item.get("owner_id") == admin_user_id
        ]
        
        assert len(hidden_user_activities) == 0, f"Hidden user's activities still present: {len(hidden_user_activities)} (should be 0)"
        print(f"✓ Hidden user's activities filtered out ({baseline_count} -> {filtered_count})")
        
        # Clean up
        unhide_request = {
            "target_user_source": "hillview",
            "target_user_id": admin_user_id
        }
        cleanup_response = requests.delete(
            f"{API_URL}/hidden/users",
            json=unhide_request,
            headers=self.test_headers
        )
        assert cleanup_response.status_code in [200, 404], f"Cleanup failed: {cleanup_response.status_code}"
    
    def test_anonymous_vs_authenticated_filtering(self):
        """Test filtering differences between anonymous and authenticated users."""
        print("\n--- Testing Anonymous vs Authenticated Filtering ---")
        
        # Query as authenticated user
        params = {
            "top_left_lat": 50.1,
            "top_left_lon": 14.3, 
            "bottom_right_lat": 50.0,
            "bottom_right_lon": 14.5,
            "client_id": "test_auth_client"
        }
        
        auth_result = query_hillview_endpoint(
            token=self.test_token, 
            params=params
        )
        
        # Query as anonymous user
        anon_result = query_hillview_endpoint(
            token=None, 
            params=params
        )
        
        assert auth_result is not None, "Authenticated API call failed - returned None"
        assert anon_result is not None, "Anonymous API call failed - returned None"
        
        auth_photos = auth_result.get("data", [])
        anon_photos = anon_result.get("data", [])
        
        print(f"Authenticated user sees: {len(auth_photos)} photos")
        print(f"Anonymous user sees: {len(anon_photos)} photos")
        
        # Anonymous users should see fewer or equal photos (no test user photos)
        assert len(anon_photos) <= len(auth_photos), f"Anonymous user sees more photos ({len(anon_photos)}) than authenticated user ({len(auth_photos)})"
        print("✓ Anonymous filtering working correctly")
    
    def test_cross_user_isolation(self):
        """Test that User A's hidden content doesn't affect User B."""
        print("\n--- Testing Cross-User Isolation ---")
        
        # Test user hides a photo
        hide_request = {
            "photo_source": "mapillary",
            "photo_id": "isolation_test_photo",
            "reason": "Testing isolation"
        }
        
        response = requests.post(
            f"{API_URL}/hidden/photos",
            json=hide_request,
            headers=self.test_headers
        )
        
        if response.status_code != 200:
            print(f"✗ User1 failed to hide photo: {response.status_code}")
            return False
        
        print("✓ Test user hidden photo")
        
        # Check test user's hidden list
        response = requests.get(
            f"{API_URL}/hidden/photos",
            headers=self.test_headers
        )
        
        test_user_hidden = response.json() if response.status_code == 200 else []
        
        # Check admin user's hidden list  
        response = requests.get(
            f"{API_URL}/hidden/photos",
            headers=self.admin_headers
        )
        
        admin_user_hidden = response.json() if response.status_code == 200 else []
        
        # Admin should not see test user's hidden photos
        test_user_photo_ids = [item["photo_id"] for item in test_user_hidden]
        admin_user_photo_ids = [item["photo_id"] for item in admin_user_hidden]
        
        common_hidden = set(test_user_photo_ids) & set(admin_user_photo_ids)
        
        assert len(common_hidden) == 0, f"Users share hidden photos (should be isolated): {common_hidden}"
        print("✓ User hidden lists are properly isolated")
        
        # Clean up
        unhide_request = {
            "photo_source": "mapillary",
            "photo_id": "isolation_test_photo"
        }
        cleanup_response = requests.delete(
            f"{API_URL}/hidden/photos",
            json=unhide_request,
            headers=self.test_headers
        )
        assert cleanup_response.status_code in [200, 404], f"Cleanup failed: {cleanup_response.status_code} - {cleanup_response.text}"
    
    def run_all_tests(self):
        """Run all content filtering tests."""
        print("=" * 50)
        print("CONTENT FILTERING TESTS")
        print("=" * 50)
        
        if not self.setup_method():
            print("❌ Setup failed!")
            return False
        
        tests = [
            self.test_hillview_filtering_hidden_photos,
            self.test_activity_feed_filtering,
            self.test_anonymous_vs_authenticated_filtering,
            self.test_cross_user_isolation
        ]
        
        passed = 0
        failed = 0
        
        for test in tests:
            try:
                if test():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"✗ {test.__name__} failed with exception: {e}")
                failed += 1
        
        print("\n" + "=" * 50)
        print(f"RESULTS: {passed} passed, {failed} failed")
        
        if failed == 0:
            print("🎉 ALL CONTENT FILTERING TESTS PASSED!")
            return True
        else:
            print("❌ Some tests failed!")
            return False


def main():
    """Run the content filtering tests."""
    test_runner = TestContentFiltering()
    success = test_runner.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())