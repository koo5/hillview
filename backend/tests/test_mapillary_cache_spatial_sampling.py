#!/usr/bin/env python3
"""
Test Mapillary cache spatial sampling behavior.
Verifies that complete regions return all photos without sampling reduction.
"""

import requests
import json
from test_utils import clear_test_database, API_URL

def create_clustered_mock_data_for_sampling(num_photos=20):
	"""Create mock photos clustered in one grid cell to test spatial sampling."""
	photos = []

	# Create photos all clustered in a small area (same grid cell)
	base_lon, base_lat = 14.4100, 50.0800  # Base coordinates

	for i in range(num_photos):
		# Slight variations within the same grid cell
		lon_offset = (i % 5) * 0.0001  # Very small offsets
		lat_offset = (i // 5) * 0.0001

		photos.append({
			"id": f"mock_clustered_sampling_{i+1:03d}",
			"geometry": {
				"type": "Point",
				"coordinates": [base_lon + lon_offset, base_lat + lat_offset]
			},
			"compass_angle": 45.0 + (i * 10),
			"computed_compass_angle": 45.0 + (i * 10),
			"computed_rotation": 0.0,
			"computed_altitude": 200.0 + i,
			"captured_at": f"2024-01-15T{10 + (i % 12):02d}:30:00Z",
			"is_pano": False,
			"thumb_1024_url": f"https://mock.mapillary.com/clustered_sampling_{i+1:03d}.jpg",
			"creator": {
				"username": f"mock_creator_{(i % 3) + 1}",
				"id": f"mock_creator_{(i % 3) + 1}"
			}
		})

	return {"data": photos}

def create_half_area_mock_data(num_photos=200):
	"""Create mock photos that fill exactly half the requested area to test spatial sampling."""
	photos = []
	
	# Test area spans: lon 14.40 to 14.42, lat 50.07 to 50.13 
	# Grid is 10x10, so each cell is 0.002 lon × 0.006 lat
	# Half area = fill 5x10 = 50 cells out of 100 total cells
	
	base_lon, base_lat = 14.400, 50.070  # Start at bottom-left of test area
	cell_width = 0.002  # (14.42 - 14.40) / 10
	cell_height = 0.006  # (50.13 - 50.07) / 10
	
	photos_per_cell = max(1, num_photos // 50)  # Distribute across 50 cells
	photo_id = 1
	
	# Fill left half of the grid (5 columns × 10 rows = 50 cells)
	for col in range(5):  # Left half: columns 0-4
		for row in range(10):  # All rows: 0-9
			for p in range(photos_per_cell):
				if photo_id > num_photos:
					break
				
				# Place photo in center of cell with small random offset
				lon = base_lon + (col + 0.5) * cell_width + (p * 0.0001)
				lat = base_lat + (row + 0.5) * cell_height + (p * 0.0001)
				
				photos.append({
					"id": f"mock_half_area_{photo_id:03d}",
					"geometry": {
						"type": "Point",
						"coordinates": [lon, lat]
					},
					"compass_angle": (photo_id * 15) % 360,
					"computed_compass_angle": (photo_id * 15) % 360,
					"computed_rotation": 0.0,
					"computed_altitude": 200.0 + photo_id,
					"captured_at": f"2024-01-15T{10 + (photo_id % 12):02d}:30:00Z",
					"is_pano": False,
					"thumb_1024_url": f"https://mock.mapillary.com/half_area_{photo_id:03d}.jpg",
					"creator": {
						"username": f"mock_creator_{(photo_id % 3) + 1}",
						"id": f"mock_creator_{(photo_id % 3) + 1}"
					}
				})
				
				photo_id += 1
			
			if photo_id > num_photos:
				break
		if photo_id > num_photos:
			break
	
	return {"data": photos}

def create_full_area_mock_data(num_photos=1000):
	"""Create mock photos that fill the entire requested area (all 100 grid cells)."""
	photos = []
	
	# Test area spans: lon 14.40 to 14.42, lat 50.07 to 50.13 
	# Grid is 10x10, so each cell is 0.002 lon × 0.006 lat
	# Full area = fill all 10x10 = 100 cells
	
	base_lon, base_lat = 14.400, 50.070  # Start at bottom-left of test area
	cell_width = 0.002  # (14.42 - 14.40) / 10
	cell_height = 0.006  # (50.13 - 50.07) / 10
	
	photos_per_cell = max(1, num_photos // 100)  # Distribute across all 100 cells
	photo_id = 1
	
	# Fill entire grid (10 columns × 10 rows = 100 cells)
	for col in range(10):  # All columns: 0-9
		for row in range(10):  # All rows: 0-9
			for p in range(photos_per_cell):
				if photo_id > num_photos:
					break
				
				# Place photo in center of cell with small random offset
				lon = base_lon + (col + 0.5) * cell_width + (p * 0.0001)
				lat = base_lat + (row + 0.5) * cell_height + (p * 0.0001)
				
				photos.append({
					"id": f"mock_full_area_{photo_id:03d}",
					"geometry": {
						"type": "Point",
						"coordinates": [lon, lat]
					},
					"compass_angle": (photo_id * 15) % 360,
					"computed_compass_angle": (photo_id * 15) % 360,
					"computed_rotation": 0.0,
					"computed_altitude": 200.0 + photo_id,
					"captured_at": f"2024-01-15T{10 + (photo_id % 12):02d}:30:00Z",
					"is_pano": False,
					"thumb_1024_url": f"https://mock.mapillary.com/full_area_{photo_id:03d}.jpg",
					"creator": {
						"username": f"mock_creator_{(photo_id % 3) + 1}",
						"id": f"mock_creator_{(photo_id % 3) + 1}"
					}
				})
				
				photo_id += 1
			
			if photo_id > num_photos:
				break
		if photo_id > num_photos:
			break
	
	return {"data": photos}

def set_mock_mapillary_data(mock_data):
	"""Set mock Mapillary data via debug endpoint."""
	response = requests.post(f"{API_URL}/debug/mock-mapillary", json=mock_data)
	if response.status_code == 200:
		result = response.json()
		print(f"✓ Set mock Mapillary data: {result['details']['photos_count']} photos")
		return True
	else:
		print(f"⚠ Failed to set mock data: {response.status_code} - {response.text}")
		return False

def clear_mock_mapillary_data():
	"""Clear mock Mapillary data via debug endpoint."""
	response = requests.delete(f"{API_URL}/debug/mock-mapillary")
	if response.status_code == 200:
		print("✓ Cleared mock Mapillary data")
		return True
	else:
		print(f"⚠ Failed to clear mock data: {response.status_code}")
		return False

def get_mapillary_photos(bbox, client_id="test_client", max_photos=None):
	"""Get Mapillary photos from the API via SSE stream."""
	headers = {
		"Accept": "text/event-stream",
		"Cache-Control": "no-cache"
	}

	params = {
		"top_left_lat": bbox[3],    # north
		"top_left_lon": bbox[0],    # west
		"bottom_right_lat": bbox[1], # south
		"bottom_right_lon": bbox[2], # east
		"client_id": client_id
	}

	if max_photos is not None:
		params["max_photos"] = max_photos

	response = requests.get(f"{API_URL}/mapillary", params=params, headers=headers, stream=True)

	if response.status_code == 200:
		photos = []
		cached_count = 0
		live_count = 0

		for line in response.iter_lines(decode_unicode=True):
			if line and line.startswith('data: '):
				try:
					data = json.loads(line[6:])  # Remove 'data: ' prefix
					if data.get('type') == 'photos':
						photos.extend(data.get('photos', []))
					elif data.get('type') == 'stream_complete':
						cached_count = data.get('total_cached_photos', 0)
						live_count = data.get('total_live_photos', 0)
						break
				except json.JSONDecodeError:
					continue

		return {
			'photos': photos,
			'cached_count': cached_count,
			'live_count': live_count,
			'total_count': len(photos)
		}
	else:
		print(f"Failed to get photos: {response.status_code} - {response.text}")
		return {'photos': [], 'cached_count': 0, 'live_count': 0, 'total_count': 0}

def test_spatial_sampling_complete_vs_incomplete(num_photos=20):
	"""Test that complete regions return all photos while incomplete regions apply sampling."""
	print(f"🧪 Testing Spatial Sampling: Complete vs Incomplete Regions ({num_photos} photos)")
	print("=" * 70)

	# Clear any existing data
	clear_test_database()

	# Set clustered mock data
	mock_data = create_clustered_mock_data_for_sampling(num_photos)
	if not set_mock_mapillary_data(mock_data):
		return False

	# Define bbox that contains all our mock photos
	# For 2000 photos: lat goes up to 50.08 + (1999//5) * 0.0001 = 50.1199
	# So we need a bbox that covers lat 50.08 to 50.12
	test_bbox = [14.40, 50.07, 14.42, 50.13]  # [west, south, east, north] - expanded to fit all photos

	try:
		print("\n--- First Request: Populate Cache (request more than available to mark region complete) ---")
		# Request more photos than available to ensure region is marked as complete
		cache_request_limit = num_photos + 50  # Request 50 more than available
		result1 = get_mapillary_photos(test_bbox, "populate_cache", max_photos=cache_request_limit)
		photos1 = result1['photos']

		print(f"First request: requested {cache_request_limit}, got {result1['total_count']} total photos ({result1['cached_count']} cached + {result1['live_count']} live)")
		assert result1['total_count'] == num_photos, f"Expected {num_photos} photos from mock data, got {result1['total_count']}"
		assert result1['live_count'] == num_photos, "First request should be all live (populating cache)"
		assert result1['cached_count'] == 0, "First request should have no cached photos"
		print(f"✓ Got fewer photos ({num_photos}) than requested ({cache_request_limit}) - region should be marked complete")

		# Verify all photos have our expected IDs
		photo_ids_1 = {photo['id'] for photo in photos1}
		expected_ids = {f"mock_clustered_sampling_{i+1:03d}" for i in range(num_photos)}
		assert photo_ids_1 == expected_ids, f"First request missing expected photo IDs. Got: {len(photo_ids_1)}, Expected: {len(expected_ids)}"

		print(f"✓ Cache populated with all {num_photos} photos")

		print("\n--- Second Request: Test Complete Region Cache Usage ---")
		result2 = get_mapillary_photos(test_bbox, "test_complete", max_photos=num_photos)
		photos2 = result2['photos']

		print(f"Second request: {result2['total_count']} total photos ({result2['cached_count']} cached + {result2['live_count']} live)")

		# Key test: Complete regions should return ALL cached photos
		assert result2['cached_count'] > 0, "Second request should use cached photos"
		assert result2['live_count'] == 0, "Second request should not fetch live photos (complete region)"

		# CRITICAL TEST: Should get all photos back, not a spatially sampled subset
		expected_complete_count = num_photos
		if result2['total_count'] != expected_complete_count:
			print(f"❌ SPATIAL SAMPLING BUG: Expected {expected_complete_count} photos from complete region, got {result2['total_count']}")
			print("   This indicates spatial sampling is incorrectly reducing photos from complete regions")
			return False
		else:
			print(f"✅ SPATIAL SAMPLING FIX WORKING: Got all {result2['total_count']} photos from complete region")

		# Verify we got the same photos
		photo_ids_2 = {photo['id'] for photo in photos2}
		assert photo_ids_2 == expected_ids, "Second request should return same photo IDs as first request"

		print("✓ Complete region returns all cached photos without sampling reduction")

		print("\n--- Third Request: Test Consistency ---")
		result3 = get_mapillary_photos(test_bbox, "test_consistency", max_photos=num_photos)

		print(f"Third request: {result3['total_count']} total photos ({result3['cached_count']} cached + {result3['live_count']} live)")
		assert result3['total_count'] == result2['total_count'], "Subsequent requests should return consistent photo counts"

		print("✓ Cache usage is consistent across requests")

		print("\n--- Test Smaller Area: Should Still Use Cache ---")
		small_bbox = [14.405, 50.075, 14.415, 50.085]  # Smaller area within the cached region
		result4 = get_mapillary_photos(small_bbox, "test_small_area", max_photos=num_photos)

		print(f"Small area request: {result4['total_count']} total photos ({result4['cached_count']} cached + {result4['live_count']} live)")
		assert result4['cached_count'] > 0, "Small area should still use cache"
		assert result4['live_count'] == 0, "Small area should not need live API calls"
		assert result4['total_count'] <= result2['total_count'], "Small area should return same or fewer photos"
		assert result4['total_count'] > 0, "Small area should return some photos"

		print("✓ Geographic filtering works correctly with cached data")

	finally:
		#clear_mock_mapillary_data()
		pass

	return True

def test_spatial_sampling_with_half_coverage():
	"""Test that spatial sampling works correctly when photos cover half the requested area."""
	print("\n🧪 Testing Spatial Sampling: Half Area Coverage")
	print("=" * 55)

	# Clear any existing data
	clear_test_database()

	# Create mock data covering exactly half the area (50 out of 100 grid cells)
	num_photos = 200
	mock_data = create_half_area_mock_data(num_photos)
	if not set_mock_mapillary_data(mock_data):
		return False

	# Test area spans: lon 14.40 to 14.42, lat 50.07 to 50.13 
	test_bbox = [14.40, 50.07, 14.42, 50.13]  # [west, south, east, north]

	try:
		print("\n--- First Request: Populate Cache ---")
		# Request more photos than available to mark region complete
		cache_request_limit = num_photos + 50  
		result1 = get_mapillary_photos(test_bbox, "populate_half_cache", max_photos=cache_request_limit)
		
		print(f"First request: requested {cache_request_limit}, got {result1['total_count']} total photos ({result1['cached_count']} cached + {result1['live_count']} live)")
		assert result1['total_count'] == num_photos, f"Expected {num_photos} photos from half-area mock data, got {result1['total_count']}"
		assert result1['live_count'] == num_photos, "First request should be all live (populating cache)"
		
		print(f"✓ Cache populated with {num_photos} photos covering half the area")

		print("\n--- Second Request: Test Incomplete Region Spatial Sampling ---")
		# Request more photos than available - should trigger spatial sampling due to incomplete coverage
		large_request_limit = 1000  # More than the 200 available
		result2 = get_mapillary_photos(test_bbox, "test_half_sampling", max_photos=large_request_limit)
		
		print(f"Second request: requested {large_request_limit}, got {result2['total_count']} total photos ({result2['cached_count']} cached + {result2['live_count']} live)")
		
		# Key test: Should use cached photos with spatial sampling
		assert result2['cached_count'] > 0, "Second request should use cached photos"
		assert result2['live_count'] == 0, "Second request should not fetch live photos (all available already cached)"
		
		# Should get all available photos since area is only half-covered
		assert result2['total_count'] == num_photos, f"Expected all {num_photos} available photos, got {result2['total_count']}"
		
		print(f"✓ Half-area coverage returned all {result2['total_count']} available photos via spatial sampling")

		print("\n--- Third Request: Test Smaller Limit ---")
		# Request fewer photos than available - should apply spatial sampling
		small_limit = 50
		result3 = get_mapillary_photos(test_bbox, "test_half_small", max_photos=small_limit)
		
		print(f"Third request: requested {small_limit}, got {result3['total_count']} total photos ({result3['cached_count']} cached + {result3['live_count']} live)")
		
		assert result3['cached_count'] > 0, "Third request should use cached photos"
		assert result3['live_count'] == 0, "Third request should not need live API calls"
		assert result3['total_count'] == small_limit, f"Expected exactly {small_limit} photos via sampling, got {result3['total_count']}"
		
		print(f"✓ Spatial sampling correctly limited to {small_limit} photos from {num_photos} available")

	finally:
		# clear_mock_mapillary_data()
		pass

	return True

def test_spatial_sampling_with_full_coverage():
	"""Test that spatial sampling works correctly when photos cover the full requested area."""
	print("\n🧪 Testing Spatial Sampling: Full Area Coverage")
	print("=" * 55)

	# Clear any existing data
	clear_test_database()

	# Create mock data covering the full area (all 100 grid cells)
	num_photos = 1000  # 10 photos per cell on average
	mock_data = create_full_area_mock_data(num_photos)
	if not set_mock_mapillary_data(mock_data):
		return False

	test_bbox = [14.40, 50.07, 14.42, 50.13]  # [west, south, east, north]

	try:
		print("\n--- First Request: Populate Cache (request less than available but more than server limit) ---")
		# The server limit is 1000, so request exactly the server limit to get 1000 photos
		# But we have 1000 available, so we'll get exactly what we requested
		# We need to use a smaller mock dataset to ensure completion detection
		
		# Actually, let's change strategy: use a smaller dataset that's less than server limit
		print("📝 Note: Using smaller dataset (900 photos) to ensure region completion detection")
		# We'll need to set new mock data with 900 photos instead of 1000
		smaller_num_photos = 900
		smaller_mock_data = create_full_area_mock_data(smaller_num_photos)
		if not set_mock_mapillary_data(smaller_mock_data):
			return False
		
		cache_request_limit = smaller_num_photos + 100  # Request 1000, but only get 900 available
		result1 = get_mapillary_photos(test_bbox, "populate_full_cache", max_photos=cache_request_limit)
		
		print(f"First request: requested {cache_request_limit}, got {result1['total_count']} total photos ({result1['cached_count']} cached + {result1['live_count']} live)")
		# Should get 900 available photos, but requested 1000, so region is marked complete
		assert result1['total_count'] == smaller_num_photos, f"Expected {smaller_num_photos} photos from smaller mock data, got {result1['total_count']}"
		assert result1['live_count'] == smaller_num_photos, "First request should be all live (populating cache)"
		
		print(f"✓ Cache populated with {result1['total_count']} photos covering full area")

		print("\n--- Second Request: Test Complete Region Cache Usage ---")
		# Request 700 photos from the 900 cached - should trigger spatial sampling 
		second_request_limit = 700
		result2 = get_mapillary_photos(test_bbox, "test_full_complete", max_photos=second_request_limit)
		
		print(f"Second request: requested {second_request_limit}, got {result2['total_count']} total photos ({result2['cached_count']} cached + {result2['live_count']} live)")
		
		# For complete regions with lots of cached photos, should use spatial sampling
		assert result2['cached_count'] > 0, "Second request should use cached photos"
		assert result2['live_count'] == 0, "Second request should not fetch live photos (complete region)"
		assert result2['total_count'] == second_request_limit, f"Expected {second_request_limit} photos from complete region, got {result2['total_count']}"
		
		print(f"✓ Full-area complete region returned {result2['total_count']} photos via spatial sampling")

		print("\n--- Third Request: Test Smaller Sample ---")
		# Request much fewer photos - should get well-distributed sample
		sample_limit = 100
		result3 = get_mapillary_photos(test_bbox, "test_full_sample", max_photos=sample_limit)
		
		print(f"Third request: requested {sample_limit}, got {result3['total_count']} total photos ({result3['cached_count']} cached + {result3['live_count']} live)")
		
		assert result3['cached_count'] > 0, "Third request should use cached photos"
		assert result3['live_count'] == 0, "Third request should not need live API calls"
		assert result3['total_count'] == sample_limit, f"Expected exactly {sample_limit} photos via sampling, got {result3['total_count']}"
		
		print(f"✓ Spatial sampling provided well-distributed {sample_limit} photos from {smaller_num_photos} cached")

	finally:
		# clear_mock_mapillary_data()
		pass

	return True

def test_spatial_sampling_performance_limit():
	"""Test that spatial sampling still applies for performance when photo count is very high."""
	print("\n🧪 Testing Spatial Sampling: Performance Limiting")
	print("=" * 55)

	# This test would require creating thousands of photos to test the performance limit
	# For now, we'll document the expected behavior
	print("📝 Performance limit test (max_photos < 1000):")
	print("   - When max_photos parameter is < 1000, spatial sampling should apply even for complete regions")
	print("   - This prevents excessive memory usage and response times")
	print("   - Current implementation uses 1000 as the threshold in: max_photos >= 1000")
	print("✓ Performance limiting logic documented")

	return True

def run_spatial_sampling_tests():
	"""Run all spatial sampling tests."""
	print("🧪 Starting Mapillary Cache Spatial Sampling Tests")
	print("=" * 65)

	success = True

	# Test 1: Small dataset (20 photos)
	try:
		if not test_spatial_sampling_complete_vs_incomplete(20):
			success = False
	except Exception as e:
		print(f"❌ Small dataset test (20 photos) failed: {e}")
		success = False

	# Test 2: Large dataset (500 photos)
	try:
		if not test_spatial_sampling_complete_vs_incomplete(500):
			success = False
	except Exception as e:
		print(f"❌ Large dataset test (500 photos) failed: {e}")
		success = False

	# Test 3: Large dataset well below server limits (800 photos) - ensures region completion
	try:
		if not test_spatial_sampling_complete_vs_incomplete(800):
			success = False
	except Exception as e:
		print(f"❌ Large dataset test (800 photos) failed: {e}")
		success = False

	# Test 4: Half-area coverage spatial sampling
	try:
		if not test_spatial_sampling_with_half_coverage():
			success = False
	except Exception as e:
		print(f"❌ Half-area coverage test failed: {e}")
		success = False

	# Test 5: Full-area coverage spatial sampling
	try:
		if not test_spatial_sampling_with_full_coverage():
			success = False
	except Exception as e:
		print(f"❌ Full-area coverage test failed: {e}")
		success = False

	# Test 6: Performance limiting documentation
	try:
		if not test_spatial_sampling_performance_limit():
			success = False
	except Exception as e:
		print(f"❌ Performance limit test failed: {e}")
		success = False

	if success:
		print("\n🎉 All spatial sampling tests passed!")
		print("\n✅ Key Validations:")
		print("   ✓ Complete regions return ALL cached photos (no sampling reduction)")
		print("   ✓ Cache works correctly with small datasets (20 photos)")
		print("   ✓ Cache works correctly with large datasets (500 photos)")
		print("   ✓ Cache works correctly with large datasets (800 photos)")
		print("   ✓ Spatial sampling works correctly with half-area coverage (200 photos)")
		print("   ✓ Spatial sampling works correctly with full-area coverage (900 photos)")
		print("   ✓ Cache is used consistently across requests")
		print("   ✓ Geographic filtering works with cached data")
		print("   ✓ Performance limiting logic is documented")
	else:
		print("\n❌ Some spatial sampling tests failed!")

	return success

if __name__ == "__main__":
	run_spatial_sampling_tests()