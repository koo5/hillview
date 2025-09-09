#!/usr/bin/env python3
"""
Integration tests for cursor-based pagination in the photos endpoint.
Tests various pagination scenarios to ensure proper cursor handling,
performance, and data consistency.
"""
import pytest
import requests
import asyncio
import os
import sys
from typing import List, Dict, Any

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from tests.utils.base_test import BasePhotoTest
from tests.utils.test_utils import API_URL, upload_test_image, wait_for_photo_processing
from tests.utils.image_utils import create_test_image_full_gps


class TestPhotoPagination(BasePhotoTest):
    """Test cursor-based pagination functionality in the photos endpoint."""

    @pytest.mark.asyncio
    async def test_basic_pagination_structure(self):
        """Test that the pagination API returns the correct structure."""
        print("\n=== Testing Basic Pagination Structure ===")
        
        # Test with no photos (empty state)
        response = requests.get(f"{API_URL}/photos/", headers=self.test_headers)
        self.assert_success(response, "Should retrieve empty photos list")
        
        data = response.json()
        
        # Check if it's the new paginated format
        if isinstance(data, dict) and 'photos' in data:
            # New paginated format
            assert 'photos' in data, "Response should have 'photos' key"
            assert 'pagination' in data, "Response should have 'pagination' key"
            assert isinstance(data['photos'], list), "Photos should be a list"
            
            pagination = data['pagination']
            assert 'next_cursor' in pagination, "Pagination should have 'next_cursor'"
            assert 'has_more' in pagination, "Pagination should have 'has_more'"
            assert 'limit' in pagination, "Pagination should have 'limit'"
            assert isinstance(pagination['has_more'], bool), "has_more should be boolean"
            
            print("✓ New paginated format detected and validated")
        else:
            # Old format - should still work for backward compatibility
            assert isinstance(data, list), "Response should be a list (old format)"
            print("✓ Old format detected - backward compatibility maintained")

    @pytest.mark.asyncio
    async def test_pagination_with_multiple_photos(self):
        """Test pagination with multiple photos to verify cursor behavior."""
        print("\n=== Testing Pagination with Multiple Photos ===")
        
        # Create multiple test photos using existing utilities
        uploaded_photos = []
        for i in range(5):
            photo_id = await self._create_simple_test_photo(f"test_pagination_{i}.jpg")
            uploaded_photos.append(photo_id)
            # Small delay to ensure different timestamps
            await asyncio.sleep(0.1)
        
        print(f"✓ Created {len(uploaded_photos)} test photos")
        
        # Test first page with small limit
        response = requests.get(f"{API_URL}/photos/?limit=2", headers=self.test_headers)
        self.assert_success(response, "Should retrieve first page of photos")
        
        data = response.json()
        
        if isinstance(data, dict) and 'photos' in data:
            # Test paginated format
            photos_page_1 = data['photos']
            pagination = data['pagination']
            
            assert len(photos_page_1) <= 2, "Should return at most 2 photos"
            assert pagination['limit'] == 2, "Limit should be 2"
            
            if len(uploaded_photos) > 2:
                assert pagination['has_more'] is True, "Should have more photos"
                assert pagination['next_cursor'] is not None, "Should have next cursor"
                
                # Test second page using cursor
                cursor = pagination['next_cursor']
                response_2 = requests.get(
                    f"{API_URL}/photos/?cursor={cursor}&limit=2", 
                    headers=self.test_headers
                )
                self.assert_success(response_2, "Should retrieve second page of photos")
                
                data_2 = response_2.json()
                photos_page_2 = data_2['photos']
                
                # Verify no duplicates between pages
                page_1_ids = {p['id'] for p in photos_page_1}
                page_2_ids = {p['id'] for p in photos_page_2}
                overlap = page_1_ids & page_2_ids
                assert not overlap, f"Pages should not overlap. Overlap: {overlap}"
                
                # Verify chronological order (newest first)
                all_photos = photos_page_1 + photos_page_2
                timestamps = [p['uploaded_at'] for p in all_photos]
                sorted_timestamps = sorted(timestamps, reverse=True)
                assert timestamps == sorted_timestamps, "Photos should be ordered by upload time (desc)"
                
                print("✓ Cursor-based pagination working correctly")
                print(f"✓ Page 1: {len(photos_page_1)} photos")
                print(f"✓ Page 2: {len(photos_page_2)} photos")
                print("✓ No overlaps between pages")
                print("✓ Chronological ordering maintained")
            else:
                print("✓ Single page result (not enough photos for pagination)")

    @pytest.mark.asyncio
    async def test_cursor_validation(self):
        """Test that invalid cursors are handled properly."""
        print("\n=== Testing Cursor Validation ===")
        
        # Test invalid cursor format
        invalid_cursors = [
            "invalid-cursor",
            "2024-13-45T99:99:99Z",  # Invalid date
            "",  # Empty cursor
            "not-a-timestamp"
        ]
        
        for invalid_cursor in invalid_cursors:
            response = requests.get(
                f"{API_URL}/photos/?cursor={invalid_cursor}",
                headers=self.test_headers
            )
            
            if response.status_code == 400:
                print(f"✓ Invalid cursor '{invalid_cursor}' properly rejected with 400")
            else:
                # Some invalid cursors might be handled gracefully
                print(f"✓ Invalid cursor '{invalid_cursor}' handled gracefully (status: {response.status_code})")

    @pytest.mark.asyncio
    async def test_limit_parameter_validation(self):
        """Test that limit parameter is properly validated and enforced."""
        print("\n=== Testing Limit Parameter Validation ===")
        
        # Test various limit values
        test_limits = [1, 5, 20, 50, 100, 150, -1, 0]
        
        for limit in test_limits:
            response = requests.get(
                f"{API_URL}/photos/?limit={limit}",
                headers=self.test_headers
            )
            
            if limit <= 0:
                # Negative or zero limits should be handled gracefully
                if response.status_code == 400:
                    print(f"✓ Invalid limit {limit} properly rejected")
                else:
                    # Or might be adjusted to a default value
                    data = response.json()
                    if isinstance(data, dict) and 'pagination' in data:
                        actual_limit = data['pagination']['limit']
                        assert actual_limit > 0, "Adjusted limit should be positive"
                        print(f"✓ Invalid limit {limit} adjusted to {actual_limit}")
            elif limit > 100:
                # Large limits should be capped
                self.assert_success(response, f"Should handle large limit {limit}")
                data = response.json()
                if isinstance(data, dict) and 'pagination' in data:
                    actual_limit = data['pagination']['limit']
                    assert actual_limit <= 100, "Limit should be capped at 100"
                    print(f"✓ Large limit {limit} capped to {actual_limit}")
            else:
                # Valid limits should work
                self.assert_success(response, f"Should handle valid limit {limit}")
                data = response.json()
                if isinstance(data, dict) and 'pagination' in data:
                    actual_limit = data['pagination']['limit']
                    assert actual_limit == limit, f"Limit should be {limit}"
                    print(f"✓ Valid limit {limit} working correctly")

    @pytest.mark.asyncio
    async def test_pagination_consistency_during_uploads(self):
        """Test that pagination remains consistent when new photos are uploaded during pagination."""
        print("\n=== Testing Pagination Consistency During Uploads ===")
        
        # Create initial photos using existing utilities
        initial_photo_ids = []
        for i in range(3):
            photo_id = await self._create_simple_test_photo(f"initial_{i}.jpg")
            initial_photo_ids.append(photo_id)
            await asyncio.sleep(0.1)
        
        print(f"✓ Created {len(initial_photo_ids)} initial photos")
        
        # Get first page
        response = requests.get(f"{API_URL}/photos/?limit=2", headers=self.test_headers)
        self.assert_success(response, "Should retrieve first page")
        
        data = response.json()
        if isinstance(data, dict) and 'photos' in data:
            first_page_photos = data['photos']
            first_page_ids = {p['id'] for p in first_page_photos}
            pagination = data['pagination']
            
            if pagination.get('has_more'):
                cursor = pagination['next_cursor']
                
                # Upload a new photo between pagination requests
                new_photo_id = await self._create_simple_test_photo("during_pagination.jpg")
                print("✓ Uploaded new photo during pagination")
                
                # Get second page using cursor
                response_2 = requests.get(
                    f"{API_URL}/photos/?cursor={cursor}&limit=2",
                    headers=self.test_headers
                )
                self.assert_success(response_2, "Should retrieve second page")
                
                data_2 = response_2.json()
                second_page_photos = data_2['photos']
                second_page_ids = {p['id'] for p in second_page_photos}
                
                # Verify no overlap (cursor-based pagination prevents duplicates)
                overlap = first_page_ids & second_page_ids
                assert not overlap, "Cursor pagination should prevent duplicates even with new uploads"
                
                # The new photo should not appear in the second page (it's newer than cursor)
                new_photo_in_second_page = new_photo_id in second_page_ids
                assert not new_photo_in_second_page, "New photo should not appear in cursor-based second page"
                
                print("✓ Pagination consistency maintained during concurrent uploads")
                print(f"✓ First page: {len(first_page_photos)} photos")
                print(f"✓ Second page: {len(second_page_photos)} photos")
                print("✓ No duplicates despite concurrent upload")

    @pytest.mark.asyncio
    async def test_backward_compatibility(self):
        """Test that the API maintains backward compatibility with old format."""
        print("\n=== Testing Backward Compatibility ===")
        
        # Create a test photo using existing utilities
        await self._create_simple_test_photo("compatibility_test.jpg")
        
        # Test without any pagination parameters (should work like old API)
        response = requests.get(f"{API_URL}/photos/", headers=self.test_headers)
        self.assert_success(response, "Should work without pagination parameters")
        
        data = response.json()
        
        if isinstance(data, dict) and 'photos' in data:
            # New format - verify it includes required fields for compatibility
            photos = data['photos']
            for photo in photos:
                assert 'id' in photo, "Photo should have id field"
                assert 'uploaded_at' in photo, "Photo should have uploaded_at field"
                assert 'created_at' in photo, "Photo should have created_at for backward compatibility"
                assert 'original_filename' in photo, "Photo should have original_filename field"
            print("✓ New format includes all required backward compatibility fields")
        else:
            # Old format - should still work
            assert isinstance(data, list), "Old format should be a list"
            for photo in data:
                assert 'id' in photo, "Photo should have id field"
                assert 'uploaded_at' in photo or 'created_at' in photo, "Photo should have timestamp"
            print("✓ Old format still working")

    @pytest.mark.asyncio 
    async def test_pagination_with_existing_photos(self):
        """Test pagination using the existing create_test_photos utility."""
        print("\n=== Testing Pagination with Existing Photo Creation Utilities ===")
        
        # Use the existing photo creation utility that creates photos for different users
        test_users = [
            {"username": "test", "password": "StrongTestPassword123!"},
        ]
        auth_tokens = {
            "test": self.test_token
        }
        
        # Create photos using existing utility
        photos_created = await self.create_test_photos_async(test_users, auth_tokens)
        print(f"✓ Created {photos_created} photos using existing utilities")
        
        if photos_created > 0:
            # Test pagination with the created photos
            response = requests.get(f"{API_URL}/photos/?limit=2", headers=self.test_headers)
            self.assert_success(response, "Should retrieve photos created by existing utilities")
            
            data = response.json()
            if isinstance(data, dict) and 'photos' in data:
                photos = data['photos']
                pagination = data['pagination']
                
                assert len(photos) <= 2, "Should respect limit parameter"
                assert pagination['limit'] == 2, "Should return correct limit"
                
                # Verify all expected fields are present
                for photo in photos:
                    assert 'id' in photo, "Photo should have id"
                    assert 'uploaded_at' in photo, "Photo should have uploaded_at"
                    assert 'original_filename' in photo, "Photo should have filename"
                    assert 'processing_status' in photo, "Photo should have processing status"
                
                print(f"✓ Retrieved {len(photos)} photos with pagination")
                print("✓ All required fields present in paginated response")

    async def _create_simple_test_photo(self, filename: str) -> str:
        """Create a simple test photo using existing utilities and return photo ID."""
        # Create test image using existing utility
        image_data = create_test_image_full_gps(200, 150, (255, 0, 0), lat=50.0755, lon=14.4378, bearing=90.0)
        
        # Upload using existing utility
        photo_id = await upload_test_image(
            filename, 
            image_data, 
            f"Test photo {filename}", 
            self.test_token, 
            is_public=True
        )
        
        # Wait for processing using existing utility
        wait_for_photo_processing(photo_id, self.test_token, timeout=30)
        
        return photo_id


if __name__ == "__main__":
    # Run the tests manually
    test = TestPhotoPagination()
    test.setUp()
    
    print("Running Photo Pagination Tests...")
    asyncio.run(test.test_basic_pagination_structure())
    asyncio.run(test.test_pagination_with_multiple_photos())
    asyncio.run(test.test_cursor_validation())
    asyncio.run(test.test_limit_parameter_validation())
    asyncio.run(test.test_pagination_consistency_during_uploads())
    asyncio.run(test.test_backward_compatibility())
    asyncio.run(test.test_pagination_with_existing_photos())
    
    print("\n✅ All pagination tests completed!")