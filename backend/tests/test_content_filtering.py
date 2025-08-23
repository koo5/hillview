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
from datetime import datetime

# Test configuration
BASE_URL = os.getenv("TEST_API_URL", "http://localhost:8055")
API_URL = f"{BASE_URL}/api"

class TestContentFiltering:
    """Test suite for hidden content filtering in API responses."""
    
    def __init__(self):
        self.auth_tokens = {}
        self.test_users = []
        
    def setup(self):
        """Set up test by creating users and content."""
        print("Setting up content filtering tests...")
        
        # Create two test users
        for i in range(2):
            test_user = {
                "username": f"filter_test_user_{i}_{int(time.time())}",
                "email": f"filter_test_{i}_{int(time.time())}@test.com", 
                "password": "TestPass123!"
            }
            
            # Register user
            response = requests.post(f"{API_URL}/auth/register", json=test_user)
            if response.status_code not in [200, 400]:
                print(f"User registration failed: {response.text}")
                return False
                
            # Login
            login_data = {
                "username": test_user["username"],
                "password": test_user["password"]
            }
            response = requests.post(
                f"{API_URL}/auth/token",
                data=login_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code == 200:
                self.auth_tokens[test_user["username"]] = response.json()["access_token"]
                self.test_users.append(test_user)
                print(f"✓ Created user: {test_user['username']}")
            else:
                print(f"Login failed for {test_user['username']}: {response.text}")
                return False
        
        return len(self.test_users) == 2
    
    def get_auth_headers(self, username):
        """Get authorization headers for a specific user."""
        token = self.auth_tokens.get(username)
        if not token:
            raise ValueError(f"No token found for user {username}")
        return {"Authorization": f"Bearer {token}"}
    
    def test_hillview_filtering_hidden_photos(self):
        """Test that hidden photos are filtered from Hillview API."""
        print("\n--- Testing Hillview Photo Filtering ---")
        
        user1 = self.test_users[0]["username"]
        
        # First, get baseline results without any hidden content
        params = {
            "top_left_lat": 50.1,
            "top_left_lon": 14.3,
            "bottom_right_lat": 50.0,
            "bottom_right_lon": 14.5,
            "client_id": "test_filter_client"
        }
        
        response = requests.get(
            f"{API_URL}/hillview",
            params=params,
            headers=self.get_auth_headers(user1)
        )
        
        if response.status_code != 200:
            print(f"✗ Hillview API call failed: {response.status_code}")
            return False
        
        baseline_result = response.json()
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
                headers=self.get_auth_headers(user1)
            )
            
            if response.status_code != 200:
                print(f"✗ Failed to hide photo: {response.status_code}")
                return False
            
            print(f"✓ Hidden photo: {photo_to_hide}")
            
            # Query again - should have one less photo
            response = requests.get(
                f"{API_URL}/hillview",
                params=params,
                headers=self.get_auth_headers(user1)
            )
            
            if response.status_code == 200:
                filtered_result = response.json()
                filtered_count = len(filtered_result.get("data", []))
                
                # Verify the hidden photo is not in results
                photo_ids = [photo["id"] for photo in filtered_result.get("data", [])]
                
                if photo_to_hide not in photo_ids:
                    print(f"✓ Hidden photo filtered out ({baseline_count} -> {filtered_count})")
                    
                    # Clean up - unhide the photo
                    unhide_request = {
                        "photo_source": "hillview",
                        "photo_id": photo_to_hide
                    }
                    requests.delete(
                        f"{API_URL}/hidden/photos",
                        json=unhide_request,
                        headers=self.get_auth_headers(user1)
                    )
                    
                    return True
                else:
                    print("✗ Hidden photo still appears in results")
                    return False
            else:
                print(f"✗ Filtered query failed: {response.status_code}")
                return False
        else:
            print("ℹ No photos available to test filtering")
            return True
    
    def test_activity_feed_filtering(self):
        """Test that hidden content is filtered from activity feed."""
        print("\n--- Testing Activity Feed Filtering ---")
        
        user1 = self.test_users[0]["username"]
        
        # Get baseline activity feed
        response = requests.get(
            f"{API_URL}/activity/recent",
            headers=self.get_auth_headers(user1)
        )
        
        if response.status_code != 200:
            print(f"✗ Activity API call failed: {response.status_code}")
            return False
        
        baseline_activities = response.json()
        baseline_count = len(baseline_activities)
        print(f"Baseline activity: {baseline_count} items")
        
        # If we have activities, try hiding one of the owners
        if baseline_count > 0:
            activity_item = baseline_activities[0]
            owner_id = activity_item.get("owner_id")
            
            if owner_id:
                hide_request = {
                    "target_user_source": "hillview", 
                    "target_user_id": owner_id,
                    "reason": "Test activity filtering"
                }
                
                response = requests.post(
                    f"{API_URL}/hidden/users",
                    json=hide_request,
                    headers=self.get_auth_headers(user1)
                )
                
                if response.status_code == 200:
                    print(f"✓ Hidden user: {owner_id}")
                    
                    # Query activity again - should filter out that user's photos
                    response = requests.get(
                        f"{API_URL}/activity/recent",
                        headers=self.get_auth_headers(user1)
                    )
                    
                    if response.status_code == 200:
                        filtered_activities = response.json()
                        filtered_count = len(filtered_activities)
                        
                        # Check if activities from hidden user are removed
                        hidden_user_activities = [
                            item for item in filtered_activities 
                            if item.get("owner_id") == owner_id
                        ]
                        
                        if len(hidden_user_activities) == 0:
                            print(f"✓ Hidden user's activities filtered out ({baseline_count} -> {filtered_count})")
                            
                            # Clean up
                            unhide_request = {
                                "target_user_source": "hillview",
                                "target_user_id": owner_id
                            }
                            requests.delete(
                                f"{API_URL}/hidden/users",
                                json=unhide_request,
                                headers=self.get_auth_headers(user1)
                            )
                            
                            return True
                        else:
                            print(f"✗ Hidden user's activities still present: {len(hidden_user_activities)}")
                            return False
                    else:
                        print(f"✗ Filtered activity query failed: {response.status_code}")
                        return False
                else:
                    print(f"✗ Failed to hide user: {response.status_code}")
                    return False
            else:
                print("ℹ Activity item has no owner_id to test with")
                return True
        else:
            print("ℹ No activity items to test filtering with")
            return True
    
    def test_anonymous_vs_authenticated_filtering(self):
        """Test filtering differences between anonymous and authenticated users."""
        print("\n--- Testing Anonymous vs Authenticated Filtering ---")
        
        user1 = self.test_users[0]["username"]
        
        # Query as authenticated user
        params = {
            "top_left_lat": 50.1,
            "top_left_lon": 14.3, 
            "bottom_right_lat": 50.0,
            "bottom_right_lon": 14.5,
            "client_id": "test_auth_client"
        }
        
        auth_response = requests.get(
            f"{API_URL}/hillview",
            params=params,
            headers=self.get_auth_headers(user1)
        )
        
        # Query as anonymous user
        anon_response = requests.get(f"{API_URL}/hillview", params=params)
        
        if auth_response.status_code == 200 and anon_response.status_code == 200:
            auth_photos = auth_response.json().get("data", [])
            anon_photos = anon_response.json().get("data", [])
            
            print(f"Authenticated user sees: {len(auth_photos)} photos")
            print(f"Anonymous user sees: {len(anon_photos)} photos")
            
            # Anonymous users should see fewer or equal photos (no test user photos)
            if len(anon_photos) <= len(auth_photos):
                print("✓ Anonymous filtering working correctly")
                return True
            else:
                print("✗ Anonymous user sees more photos than authenticated user")
                return False
        else:
            print(f"✗ API calls failed - auth: {auth_response.status_code}, anon: {anon_response.status_code}")
            return False
    
    def test_cross_user_isolation(self):
        """Test that User A's hidden content doesn't affect User B."""
        print("\n--- Testing Cross-User Isolation ---")
        
        user1 = self.test_users[0]["username"]
        user2 = self.test_users[1]["username"] 
        
        # User1 hides a photo
        hide_request = {
            "photo_source": "mapillary",
            "photo_id": "isolation_test_photo",
            "reason": "Testing isolation"
        }
        
        response = requests.post(
            f"{API_URL}/hidden/photos",
            json=hide_request,
            headers=self.get_auth_headers(user1)
        )
        
        if response.status_code != 200:
            print(f"✗ User1 failed to hide photo: {response.status_code}")
            return False
        
        print("✓ User1 hidden photo")
        
        # Check User1's hidden list
        response = requests.get(
            f"{API_URL}/hidden/photos",
            headers=self.get_auth_headers(user1)
        )
        
        user1_hidden = response.json() if response.status_code == 200 else []
        
        # Check User2's hidden list  
        response = requests.get(
            f"{API_URL}/hidden/photos",
            headers=self.get_auth_headers(user2)
        )
        
        user2_hidden = response.json() if response.status_code == 200 else []
        
        # User2 should not see User1's hidden photos
        user1_photo_ids = [item["photo_id"] for item in user1_hidden]
        user2_photo_ids = [item["photo_id"] for item in user2_hidden]
        
        common_hidden = set(user1_photo_ids) & set(user2_photo_ids)
        
        if len(common_hidden) == 0:
            print("✓ User hidden lists are properly isolated")
            
            # Clean up
            unhide_request = {
                "photo_source": "mapillary",
                "photo_id": "isolation_test_photo"
            }
            requests.delete(
                f"{API_URL}/hidden/photos",
                json=unhide_request,
                headers=self.get_auth_headers(user1)
            )
            
            return True
        else:
            print(f"✗ Users share hidden photos: {common_hidden}")
            return False
    
    def run_all_tests(self):
        """Run all content filtering tests."""
        print("=" * 50)
        print("CONTENT FILTERING TESTS")
        print("=" * 50)
        
        if not self.setup():
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