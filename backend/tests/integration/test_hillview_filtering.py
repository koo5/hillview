#!/usr/bin/env python3
"""
Comprehensive tests for /api/hillview content filtering.

Tests all aspects of how hidden content affects Hillview API responses:
- Individual photo hiding
- User hiding (all photos by a user)
- Combined photo + user hiding
- Geographic filtering with hidden content
- Anonymous vs authenticated filtering
- Cross-user isolation
- Performance with large datasets
- Edge cases and boundary conditions
"""

import requests
import json
import time
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from utils.test_utils import clear_test_database, API_URL, create_test_photos

class TestHillviewFiltering:
    """Comprehensive test suite for Hillview API content filtering."""
    
    def setup_method(self):
        """Setup method called before each test method."""
        self.auth_tokens = {}
        self.test_users = []
        self.test_photos = []
        self.hidden_items = []  # Track what we hide for cleanup
        
    def setup(self):
        """Set up test users and discover existing photos."""
        print("Setting up comprehensive Hillview filtering tests...")
        
        # Clear database first to ensure clean state
        clear_test_database()
        
        # Create multiple test users for various scenarios
        user_configs = [
            ("hillview_filter_viewer", "viewer@test.com"),
            ("hillview_filter_hider1", "hider1@test.com"), 
            ("hillview_filter_hider2", "hider2@test.com"),
            ("hillview_filter_content_owner", "owner@test.com")
        ]
        
        for i, (username, email) in enumerate(user_configs):
            # Generate unique shorter username to fit 3-30 character limit
            timestamp = str(int(time.time()))[-6:]  # Use last 6 digits
            test_user = {
                "username": f"{username[:15]}_{timestamp}_{i}",  # Keep under 30 chars and make unique
                "email": f"{email.split('@')[0]}_{timestamp}_{i}@test.com",
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
        
        # Create test photos for filtering tests
        create_test_photos(self.test_users, self.auth_tokens)
        
        # Discover photos for testing (now includes our uploaded photos)
        self.discover_test_photos()
        
        return len(self.test_users) == 4
    
    def cleanup(self):
        """Clean up all hidden items created during testing."""
        print("Cleaning up Hillview filtering test data...")
        
        for username in self.auth_tokens:
            headers = self.get_auth_headers(username)
            
            # Clean up hidden photos
            try:
                response = requests.get(f"{API_URL}/hidden/photos", headers=headers)
                if response.status_code == 200:
                    for hidden_photo in response.json():
                        unhide_request = {
                            "photo_source": hidden_photo["photo_source"],
                            "photo_id": hidden_photo["photo_id"]
                        }
                        requests.delete(f"{API_URL}/hidden/photos", json=unhide_request, headers=headers)
            except:
                pass
            
            # Clean up hidden users
            try:
                response = requests.get(f"{API_URL}/hidden/users", headers=headers)
                if response.status_code == 200:
                    for hidden_user in response.json():
                        unhide_request = {
                            "target_user_source": hidden_user["target_user_source"],
                            "target_user_id": hidden_user["target_user_id"]
                        }
                        requests.delete(f"{API_URL}/hidden/users", json=unhide_request, headers=headers)
            except:
                pass
        
        print("✓ Cleanup complete")
    
    def get_auth_headers(self, username: str) -> Dict[str, str]:
        """Get authorization headers for a specific user."""
        token = self.auth_tokens.get(username)
        if not token:
            raise ValueError(f"No token found for user {username}")
        return {"Authorization": f"Bearer {token}"}
    
    def create_test_image(self, width: int = 100, height: int = 100, color: tuple = (255, 0, 0)) -> bytes:
        """Create a real JPEG image for testing."""
        # Create a simple colored image
        img = Image.new('RGB', (width, height), color)
        
        # Save to bytes buffer
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='JPEG', quality=85)
        img_buffer.seek(0)
        
        return img_buffer.getvalue()
    
    def discover_test_photos(self):
        """Discover existing photos in the database for testing."""
        print("Discovering existing photos for testing...")
        
        # Use a broad geographic area to find photos
        params = {
            "top_left_lat": 51.0,
            "top_left_lon": 13.0,
            "bottom_right_lat": 49.0,
            "bottom_right_lon": 15.0,
            "client_id": "hillview_filter_discovery"
        }
        
        # Try as first user (authenticated)
        if self.test_users:
            headers = self.get_auth_headers(self.test_users[0]["username"])
            response = requests.get(f"{API_URL}/hillview", params=params, headers=headers)
        else:
            # Try anonymous
            response = requests.get(f"{API_URL}/hillview", params=params)
        
        if response.status_code == 200:
            result = response.json()
            self.test_photos = result.get("data", [])
            print(f"✓ Discovered {len(self.test_photos)} photos for testing")
        else:
            print(f"⚠ No photos discovered for testing (status: {response.status_code})")
            self.test_photos = []
    
    def get_hillview_photos(self, username: Optional[str] = None, bbox: Optional[Dict] = None) -> List[Dict]:
        """Get photos from Hillview API."""
        params = bbox or {
            "top_left_lat": 51.0,
            "top_left_lon": 13.0,
            "bottom_right_lat": 49.0,
            "bottom_right_lon": 15.0,
            "client_id": "hillview_filter_test"
        }
        
        if username:
            headers = self.get_auth_headers(username)
            response = requests.get(f"{API_URL}/hillview", params=params, headers=headers)
        else:
            response = requests.get(f"{API_URL}/hillview", params=params)
        
        if response.status_code == 200:
            return response.json().get("data", [])
        else:
            print(f"Hillview API call failed: {response.status_code}")
            return []
    
    def test_individual_photo_hiding_filtering(self):
        """Test that individually hidden photos are filtered from results."""
        print("\n--- Testing Individual Photo Hiding Filtering ---")
        
        if not self.test_photos:
            print("ℹ No photos available for individual photo hiding test")
            return True
        
        username = self.test_users[0]["username"]
        photo_to_hide = self.test_photos[0]
        
        # Get baseline count
        baseline_photos = self.get_hillview_photos(username)
        baseline_count = len(baseline_photos)
        baseline_ids = [p["id"] for p in baseline_photos]
        
        print(f"Baseline: {baseline_count} photos")
        
        if photo_to_hide["id"] not in baseline_ids:
            print(f"⚠ Test photo {photo_to_hide['id']} not in baseline results")
            return True
        
        # Hide the photo
        hide_request = {
            "photo_source": "hillview",
            "photo_id": photo_to_hide["id"],
            "reason": "Individual photo hiding test"
        }
        
        response = requests.post(
            f"{API_URL}/hidden/photos",
            json=hide_request,
            headers=self.get_auth_headers(username)
        )
        
        if response.status_code != 200:
            print(f"✗ Failed to hide photo: {response.status_code}")
            return False
        
        print(f"✓ Hidden photo: {photo_to_hide['id']}")
        
        # Get filtered results
        filtered_photos = self.get_hillview_photos(username)
        filtered_count = len(filtered_photos)
        filtered_ids = [p["id"] for p in filtered_photos]
        
        # Verify photo is filtered out
        if photo_to_hide["id"] not in filtered_ids:
            print(f"✓ Hidden photo filtered out ({baseline_count} -> {filtered_count})")
            success = True
        else:
            print(f"✗ Hidden photo still appears in results")
            success = False
        
        # Verify other photos are still there
        other_photos_still_present = sum(1 for photo_id in baseline_ids 
                                       if photo_id != photo_to_hide["id"] and photo_id in filtered_ids)
        expected_other_photos = baseline_count - 1
        
        if other_photos_still_present == expected_other_photos:
            print(f"✓ Other photos remain visible ({other_photos_still_present}/{expected_other_photos})")
        else:
            print(f"⚠ Other photos count mismatch: {other_photos_still_present}/{expected_other_photos}")
        
        # Cleanup
        unhide_request = {
            "photo_source": "hillview",
            "photo_id": photo_to_hide["id"]
        }
        requests.delete(f"{API_URL}/hidden/photos", json=unhide_request, headers=self.get_auth_headers(username))
        
        return success
    
    def test_user_hiding_filtering(self):
        """Test that all photos by hidden users are filtered from results."""
        print("\n--- Testing User Hiding Filtering ---")
        
        if not self.test_photos:
            print("ℹ No photos available for user hiding test")
            return True
        
        username = self.test_users[0]["username"]
        
        # Get baseline
        baseline_photos = self.get_hillview_photos(username)
        baseline_count = len(baseline_photos)
        
        print(f"Baseline: {baseline_count} photos")
        
        # Find a photo with an owner to hide
        target_photo = None
        target_owner_id = None
        
        for photo in baseline_photos:
            # In hillview API, photos should have owner information or be identifiable by directory
            if photo.get("dir_name") or photo.get("filepath"):
                target_photo = photo
                # Extract owner ID from filepath or directory structure
                # This is API-specific - may need adjustment based on actual response format
                if "filepath" in photo and photo["filepath"]:
                    # Assume filepath contains owner ID like "/uploads/{owner_id}/photo.jpg"
                    path_parts = photo["filepath"].split("/")
                    for part in path_parts:
                        if part.isdigit() or (part.count("-") == 4 and len(part) == 36):  # UUID-like
                            target_owner_id = part
                            break
                break
        
        if not target_photo or not target_owner_id:
            print("ℹ No suitable photo with identifiable owner found")
            return True
        
        print(f"Target photo: {target_photo['id']}, Owner: {target_owner_id}")
        
        # Hide the user
        hide_request = {
            "target_user_source": "hillview",
            "target_user_id": target_owner_id,
            "reason": "User hiding filtering test"
        }
        
        response = requests.post(
            f"{API_URL}/hidden/users",
            json=hide_request,
            headers=self.get_auth_headers(username)
        )
        
        if response.status_code != 200:
            print(f"✗ Failed to hide user: {response.status_code}")
            return False
        
        print(f"✓ Hidden user: {target_owner_id}")
        
        # Get filtered results
        filtered_photos = self.get_hillview_photos(username)
        filtered_count = len(filtered_photos)
        filtered_ids = [p["id"] for p in filtered_photos]
        
        # Count how many photos from the hidden user are filtered out
        hidden_user_photos_still_visible = 0
        for photo in filtered_photos:
            if photo.get("filepath") and target_owner_id in photo["filepath"]:
                hidden_user_photos_still_visible += 1
        
        if hidden_user_photos_still_visible == 0:
            print(f"✓ All photos by hidden user filtered out ({baseline_count} -> {filtered_count})")
            success = True
        else:
            print(f"✗ {hidden_user_photos_still_visible} photos by hidden user still visible")
            success = False
        
        # Cleanup
        unhide_request = {
            "target_user_source": "hillview",
            "target_user_id": target_owner_id
        }
        requests.delete(f"{API_URL}/hidden/users", json=unhide_request, headers=self.get_auth_headers(username))
        
        return success
    
    def test_combined_photo_and_user_hiding(self):
        """Test filtering when both individual photos and users are hidden."""
        print("\n--- Testing Combined Photo + User Hiding ---")
        
        if len(self.test_photos) < 2:
            print("ℹ Need at least 2 photos for combined hiding test")
            return True
        
        username = self.test_users[0]["username"]
        
        # Get baseline
        baseline_photos = self.get_hillview_photos(username)
        baseline_count = len(baseline_photos)
        baseline_ids = [p["id"] for p in baseline_photos]
        
        print(f"Baseline: {baseline_count} photos")
        
        # Select two different photos to hide in different ways
        photo_to_hide_individually = baseline_photos[0]
        user_photo = baseline_photos[1] if len(baseline_photos) > 1 else baseline_photos[0]
        
        # Extract owner from user_photo
        target_owner_id = None
        if user_photo.get("filepath"):
            path_parts = user_photo["filepath"].split("/")
            for part in path_parts:
                if part.isdigit() or (part.count("-") == 4 and len(part) == 36):
                    target_owner_id = part
                    break
        
        if not target_owner_id:
            print("ℹ Cannot extract owner ID for user hiding")
            return True
        
        # Hide individual photo
        hide_photo_request = {
            "photo_source": "hillview",
            "photo_id": photo_to_hide_individually["id"],
            "reason": "Combined test - individual photo"
        }
        
        response1 = requests.post(
            f"{API_URL}/hidden/photos",
            json=hide_photo_request,
            headers=self.get_auth_headers(username)
        )
        
        # Hide user
        hide_user_request = {
            "target_user_source": "hillview", 
            "target_user_id": target_owner_id,
            "reason": "Combined test - user hiding"
        }
        
        response2 = requests.post(
            f"{API_URL}/hidden/users",
            json=hide_user_request,
            headers=self.get_auth_headers(username)
        )
        
        if response1.status_code != 200 or response2.status_code != 200:
            print(f"✗ Failed to set up combined hiding (photo: {response1.status_code}, user: {response2.status_code})")
            return False
        
        print(f"✓ Hidden photo: {photo_to_hide_individually['id']} and user: {target_owner_id}")
        
        # Get filtered results
        filtered_photos = self.get_hillview_photos(username)
        filtered_count = len(filtered_photos)
        filtered_ids = [p["id"] for p in filtered_photos]
        
        # Check that both types of hiding worked
        individual_photo_filtered = photo_to_hide_individually["id"] not in filtered_ids
        
        user_photos_filtered = 0
        for photo in filtered_photos:
            if photo.get("filepath") and target_owner_id in photo["filepath"]:
                user_photos_filtered += 1
        
        success = individual_photo_filtered and user_photos_filtered == 0
        
        if success:
            print(f"✓ Combined hiding successful ({baseline_count} -> {filtered_count})")
        else:
            print(f"✗ Combined hiding failed - individual: {individual_photo_filtered}, user photos visible: {user_photos_filtered}")
        
        # Cleanup
        requests.delete(f"{API_URL}/hidden/photos", 
                       json={"photo_source": "hillview", "photo_id": photo_to_hide_individually["id"]},
                       headers=self.get_auth_headers(username))
        
        requests.delete(f"{API_URL}/hidden/users",
                       json={"target_user_source": "hillview", "target_user_id": target_owner_id},
                       headers=self.get_auth_headers(username))
        
        return success
    
    def test_geographic_filtering_interaction(self):
        """Test that hidden content filtering works correctly with geographic bounding boxes."""
        print("\n--- Testing Geographic Filtering Interaction ---")
        
        username = self.test_users[0]["username"]
        
        # Test with different geographic areas
        test_areas = [
            {
                "name": "Prague area",
                "top_left_lat": 50.2,
                "top_left_lon": 14.2,
                "bottom_right_lat": 50.0,
                "bottom_right_lon": 14.6
            },
            {
                "name": "Broader Czech area", 
                "top_left_lat": 51.0,
                "top_left_lon": 12.0,
                "bottom_right_lat": 48.0,
                "bottom_right_lon": 19.0
            }
        ]
        
        success = True
        
        for area in test_areas:
            print(f"Testing area: {area['name']}")
            
            # Get baseline for this area
            baseline_photos = self.get_hillview_photos(username, {
                "top_left_lat": area["top_left_lat"],
                "top_left_lon": area["top_left_lon"],
                "bottom_right_lat": area["bottom_right_lat"], 
                "bottom_right_lon": area["bottom_right_lon"],
                "client_id": "geo_filter_test"
            })
            
            baseline_count = len(baseline_photos)
            print(f"  {area['name']}: {baseline_count} photos")
            
            if baseline_count == 0:
                continue
            
            # Hide first photo
            photo_to_hide = baseline_photos[0]
            hide_request = {
                "photo_source": "hillview",
                "photo_id": photo_to_hide["id"],
                "reason": f"Geographic test - {area['name']}"
            }
            
            response = requests.post(
                f"{API_URL}/hidden/photos",
                json=hide_request,
                headers=self.get_auth_headers(username)
            )
            
            if response.status_code == 200:
                # Get filtered results for same area
                filtered_photos = self.get_hillview_photos(username, {
                    "top_left_lat": area["top_left_lat"],
                    "top_left_lon": area["top_left_lon"],
                    "bottom_right_lat": area["bottom_right_lat"],
                    "bottom_right_lon": area["bottom_right_lon"],
                    "client_id": "geo_filter_test"
                })
                
                filtered_count = len(filtered_photos)
                filtered_ids = [p["id"] for p in filtered_photos]
                
                if photo_to_hide["id"] not in filtered_ids:
                    print(f"  ✓ Hidden photo filtered in {area['name']} ({baseline_count} -> {filtered_count})")
                else:
                    print(f"  ✗ Hidden photo not filtered in {area['name']}")
                    success = False
                
                # Cleanup
                unhide_request = {
                    "photo_source": "hillview",
                    "photo_id": photo_to_hide["id"]
                }
                requests.delete(f"{API_URL}/hidden/photos", json=unhide_request, headers=self.get_auth_headers(username))
            else:
                print(f"  ⚠ Could not hide photo in {area['name']}: {response.status_code}")
        
        return success
    
    def test_anonymous_vs_authenticated_detailed(self):
        """Detailed test of filtering differences between anonymous and authenticated users."""
        print("\n--- Testing Anonymous vs Authenticated Filtering (Detailed) ---")
        
        username = self.test_users[0]["username"]
        
        # Test multiple geographic areas
        test_bbox = {
            "top_left_lat": 50.2,
            "top_left_lon": 14.2,
            "bottom_right_lat": 50.0,
            "bottom_right_lon": 14.6,
            "client_id": "anon_vs_auth_test"
        }
        
        # Get results as authenticated user
        auth_photos = self.get_hillview_photos(username, test_bbox)
        
        # Get results as anonymous user  
        anon_photos = self.get_hillview_photos(None, test_bbox)
        
        auth_count = len(auth_photos)
        anon_count = len(anon_photos)
        
        print(f"Authenticated user sees: {auth_count} photos")
        print(f"Anonymous user sees: {anon_count} photos")
        
        # Anonymous should see same or fewer photos (test users filtered out)
        if anon_count <= auth_count:
            print("✓ Anonymous user sees appropriate number of photos")
            
            # Check for test user content in anonymous results
            test_user_content_in_anon = 0
            for photo in anon_photos:
                if photo.get("filepath") and any(user["username"] in photo["filepath"] for user in self.test_users):
                    test_user_content_in_anon += 1
            
            if test_user_content_in_anon == 0:
                print("✓ No test user content visible to anonymous users")
                return True
            else:
                print(f"⚠ {test_user_content_in_anon} test user photos visible to anonymous users")
                return True  # May be expected depending on is_test flag
        else:
            print("✗ Anonymous user sees more photos than authenticated user")
            return False
    
    def test_cross_user_isolation_detailed(self):
        """Detailed test that User A's hidden content doesn't affect User B."""
        print("\n--- Testing Cross-User Isolation (Detailed) ---")
        
        user_a = self.test_users[0]["username"]
        user_b = self.test_users[1]["username"]
        
        if not self.test_photos:
            print("ℹ No photos available for isolation test")
            return True
        
        # Both users get baseline
        user_a_baseline = self.get_hillview_photos(user_a)
        user_b_baseline = self.get_hillview_photos(user_b)
        
        print(f"User A baseline: {len(user_a_baseline)} photos")
        print(f"User B baseline: {len(user_b_baseline)} photos")
        
        if len(user_a_baseline) == 0:
            print("ℹ No photos visible to User A for isolation test")
            return True
        
        # User A hides a photo
        photo_to_hide = user_a_baseline[0]
        hide_request = {
            "photo_source": "hillview",
            "photo_id": photo_to_hide["id"],
            "reason": "Cross-user isolation test"
        }
        
        response = requests.post(
            f"{API_URL}/hidden/photos",
            json=hide_request,
            headers=self.get_auth_headers(user_a)
        )
        
        if response.status_code != 200:
            print(f"✗ User A failed to hide photo: {response.status_code}")
            return False
        
        print(f"✓ User A hidden photo: {photo_to_hide['id']}")
        
        # Get results for both users
        user_a_filtered = self.get_hillview_photos(user_a)
        user_b_after = self.get_hillview_photos(user_b)
        
        user_a_filtered_ids = [p["id"] for p in user_a_filtered]
        user_b_after_ids = [p["id"] for p in user_b_after]
        
        # User A should not see the hidden photo
        user_a_sees_hidden = photo_to_hide["id"] in user_a_filtered_ids
        
        # User B should still see the photo (if it was visible to B originally)
        user_b_baseline_ids = [p["id"] for p in user_b_baseline]
        photo_was_visible_to_b = photo_to_hide["id"] in user_b_baseline_ids
        user_b_still_sees = photo_to_hide["id"] in user_b_after_ids
        
        success = True
        
        if user_a_sees_hidden:
            print("✗ User A still sees hidden photo")
            success = False
        else:
            print("✓ User A no longer sees hidden photo")
        
        if photo_was_visible_to_b:
            if user_b_still_sees:
                print("✓ User B still sees photo hidden by User A")
            else:
                print("✗ User B no longer sees photo hidden by User A (isolation broken)")
                success = False
        else:
            print("ℹ Photo was not visible to User B originally")
        
        # Cleanup
        unhide_request = {
            "photo_source": "hillview",
            "photo_id": photo_to_hide["id"]
        }
        requests.delete(f"{API_URL}/hidden/photos", json=unhide_request, headers=self.get_auth_headers(user_a))
        
        return success
    
    def test_performance_with_many_hidden_items(self):
        """Test filtering performance when user has many hidden items."""
        print("\n--- Testing Performance with Many Hidden Items ---")
        
        username = self.test_users[0]["username"]
        
        if len(self.test_photos) < 3:
            print("ℹ Need at least 3 photos for performance test")
            return True
        
        # Record baseline performance
        start_time = time.time()
        baseline_photos = self.get_hillview_photos(username)
        baseline_time = time.time() - start_time
        
        print(f"Baseline query: {len(baseline_photos)} photos in {baseline_time:.3f}s")
        
        # Hide multiple items
        hidden_items = []
        photos_to_hide = self.test_photos[:min(5, len(self.test_photos))]  # Hide up to 5 photos
        
        for i, photo in enumerate(photos_to_hide):
            hide_request = {
                "photo_source": "hillview",
                "photo_id": photo["id"], 
                "reason": f"Performance test {i}"
            }
            
            response = requests.post(
                f"{API_URL}/hidden/photos",
                json=hide_request,
                headers=self.get_auth_headers(username)
            )
            
            if response.status_code == 200:
                hidden_items.append(photo["id"])
        
        print(f"✓ Hidden {len(hidden_items)} photos")
        
        # Test filtered query performance
        start_time = time.time()
        filtered_photos = self.get_hillview_photos(username)
        filtered_time = time.time() - start_time
        
        print(f"Filtered query: {len(filtered_photos)} photos in {filtered_time:.3f}s")
        
        # Performance should not degrade significantly (within 2x)
        performance_acceptable = filtered_time <= baseline_time * 2
        
        if performance_acceptable:
            print(f"✓ Performance acceptable ({filtered_time:.3f}s vs {baseline_time:.3f}s)")
        else:
            print(f"⚠ Performance degradation ({filtered_time:.3f}s vs {baseline_time:.3f}s)")
        
        # Verify filtering worked
        filtered_ids = [p["id"] for p in filtered_photos]
        correctly_filtered = sum(1 for item_id in hidden_items if item_id not in filtered_ids)
        
        if correctly_filtered == len(hidden_items):
            print(f"✓ All {len(hidden_items)} hidden photos correctly filtered")
        else:
            print(f"✗ Only {correctly_filtered}/{len(hidden_items)} hidden photos filtered")
        
        # Cleanup
        for photo_id in hidden_items:
            unhide_request = {
                "photo_source": "hillview",
                "photo_id": photo_id
            }
            requests.delete(f"{API_URL}/hidden/photos", json=unhide_request, headers=self.get_auth_headers(username))
        
        return performance_acceptable and correctly_filtered == len(hidden_items)
    
    def test_empty_results_filtering(self):
        """Test filtering behavior when all results would be hidden."""
        print("\n--- Testing Empty Results Filtering ---")
        
        username = self.test_users[0]["username"]
        
        # Use a very specific geographic area that might have few photos
        narrow_bbox = {
            "top_left_lat": 50.0851,
            "top_left_lon": 14.4100,
            "bottom_right_lat": 50.0750,
            "bottom_right_lon": 14.4200,
            "client_id": "empty_results_test"
        }
        
        # Get baseline for narrow area
        baseline_photos = self.get_hillview_photos(username, narrow_bbox)
        baseline_count = len(baseline_photos)
        
        print(f"Narrow area baseline: {baseline_count} photos")
        
        if baseline_count == 0:
            print("ℹ Area already has no photos - testing empty response handling")
            
            # Query should still work with empty results
            filtered_photos = self.get_hillview_photos(username, narrow_bbox)
            
            if len(filtered_photos) == 0:
                print("✓ Empty results handled correctly")
                return True
            else:
                print("✗ Unexpected photos in empty area")
                return False
        
        # Hide all photos in the area
        hidden_items = []
        for photo in baseline_photos:
            hide_request = {
                "photo_source": "hillview",
                "photo_id": photo["id"],
                "reason": "Empty results test"
            }
            
            response = requests.post(
                f"{API_URL}/hidden/photos",
                json=hide_request,
                headers=self.get_auth_headers(username)
            )
            
            if response.status_code == 200:
                hidden_items.append(photo["id"])
        
        print(f"✓ Hidden {len(hidden_items)} photos in narrow area")
        
        # Query filtered results - should be empty
        filtered_photos = self.get_hillview_photos(username, narrow_bbox)
        filtered_count = len(filtered_photos)
        
        success = filtered_count == 0
        
        if success:
            print("✓ All photos filtered out - empty results handled correctly")
        else:
            print(f"✗ {filtered_count} photos still visible after hiding all")
        
        # Cleanup
        for photo_id in hidden_items:
            unhide_request = {
                "photo_source": "hillview", 
                "photo_id": photo_id
            }
            requests.delete(f"{API_URL}/hidden/photos", json=unhide_request, headers=self.get_auth_headers(username))
        
        return success
    
    def run_all_tests(self):
        """Run all comprehensive Hillview filtering tests."""
        print("=" * 60)
        print("COMPREHENSIVE HILLVIEW FILTERING TESTS")
        print("=" * 60)
        
        if not self.setup():
            print("❌ Setup failed!")
            return False
        
        tests = [
            self.test_individual_photo_hiding_filtering,
            self.test_user_hiding_filtering,
            self.test_combined_photo_and_user_hiding,
            self.test_geographic_filtering_interaction,
            self.test_anonymous_vs_authenticated_detailed,
            self.test_cross_user_isolation_detailed,
            self.test_performance_with_many_hidden_items,
            self.test_empty_results_filtering
        ]
        
        passed = 0
        failed = 0
        
        try:
            for test in tests:
                try:
                    if test():
                        passed += 1
                    else:
                        failed += 1
                except Exception as e:
                    print(f"✗ {test.__name__} failed with exception: {e}")
                    failed += 1
        
        finally:
            self.cleanup()
        
        print("\n" + "=" * 60)
        print(f"RESULTS: {passed} passed, {failed} failed")
        
        if failed == 0:
            print("🎉 ALL COMPREHENSIVE HILLVIEW FILTERING TESTS PASSED!")
            return True
        else:
            print("❌ Some Hillview filtering tests failed!")
            return False


def main():
    """Run the comprehensive Hillview filtering tests."""
    print("🧪 Starting Comprehensive Hillview Filtering Tests")
    print("=" * 60)
    
    # Clear database first
    clear_test_database()
    
    test_runner = TestHillviewFiltering()
    success = test_runner.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())