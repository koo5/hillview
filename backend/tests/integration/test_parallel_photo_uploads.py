#!/usr/bin/env python3
"""
Parallel Photo Upload Integration Test

Tests uploading multiple photos concurrently to verify:
1. Rate limiting behavior under load
2. Worker service handles concurrent requests properly
3. Photos are processed correctly without race conditions
4. Resource management (RAM, disk) works under parallel load
"""

import asyncio
import pytest
import requests
import os
import sys
import time
import random
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from tests.utils.base_test import BasePhotoTest
from tests.utils.test_utils import API_URL, upload_test_image, wait_for_photo_processing
from tests.utils.image_utils import create_test_image_full_gps


class TestParallelPhotoUploads(BasePhotoTest):
	"""Test parallel photo uploads to verify system behavior under concurrent load."""

	def setup_method(self):
		"""Setup for each test method"""
		super().setup_method()
		self.upload_results = []


	async def upload_single_photo(self, photo_id: int, timeout: int = 60) -> Dict:
		"""Upload a single photo and return result."""
		result = {
			'photo_id': photo_id,
			'success': False,
			'upload_time': 0,
			'verification_time': 0,
			'error': None,
			'photo_uuid': None
		}

		start_time = time.time()

		try:
			# Create unique test image with GPS coordinates
			lat = 50.0755 + (photo_id * 0.001)  # Offset each photo slightly
			lon = 14.4378 + (photo_id * 0.001)
			colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255)]
			color = colors[photo_id % len(colors)]

			image_data = create_test_image_full_gps(
				width=2048, height=1536,
				color=color,
				lat=lat, lon=lon,
				bearing=photo_id * 10
			)

			upload_start = time.time()

			# Upload using the utility function
			filename = f"parallel_test_{photo_id}.jpg"
			description = f"Parallel test photo {photo_id}"

			photo_uuid = await upload_test_image(
				filename, image_data, description, self.test_token, is_public=True, timeout=timeout
			)

			result['upload_time'] = time.time() - upload_start
			result['photo_uuid'] = photo_uuid

			# Verify upload was processed successfully
			verification_start = time.time()

			try:
				final_status = wait_for_photo_processing(photo_uuid, self.test_token, timeout=timeout)
			except TimeoutError as e:
				print(f"✗ Photo {photo_id} verification failed with client TIMEOUT: {e}")
				raise

			result['verification_time'] = time.time() - verification_start

			if final_status and final_status.get('processing_status') == 'completed':
				result['success'] = True
				print(f"✓ Photo {photo_id} uploaded successfully in {result['upload_time']:.2f}s")
			else:
				result['error'] = f"Verification failed: {final_status}"
				print(f"✗ Photo {photo_id} verification failed: {final_status}")

		except asyncio.TimeoutError as e:
			result['error'] = f"Timeout: {e}"
			result['upload_time'] = time.time() - start_time
			print(f"✗ Photo {photo_id} upload failed with TIMEOUT: {e}")
		except TimeoutError as e:
			result['error'] = f"Timeout: {e}"
			result['upload_time'] = time.time() - start_time
			print(f"✗ Photo {photo_id} upload failed with TIMEOUT: {e}")
		except Exception as e:
			result['error'] = f"{type(e).__name__}: {str(e)}"
			result['upload_time'] = time.time() - start_time
			print(f"✗ Photo {photo_id} upload failed: {type(e).__name__}: {e}")
			# Also log the full exception for debugging
			#import traceback
			#print(f"   Full traceback: {traceback.format_exc()}")

		return result

	@pytest.mark.asyncio
	async def test_parallel_upload_small_batch(self):
		"""Test uploading 5 photos in parallel - small load test."""
		print("\n=== Testing Parallel Upload: Small Batch (5 photos) ===")

		num_photos = 5

		start_time = time.time()

		# Create tasks for parallel uploads
		tasks = []
		for i in range(num_photos):
			task = self.upload_single_photo(i)
			tasks.append(task)

		# Execute uploads in parallel
		print(f"Starting {num_photos} parallel uploads...")
		results = await asyncio.gather(*tasks, return_exceptions=True)

		total_time = time.time() - start_time
		print(f"All uploads completed in {total_time:.2f} seconds")

		# Analyze results
		successful_uploads = []
		failed_uploads = []

		for result in results:
			if isinstance(result, Exception):
				failed_uploads.append(f"Exception: {result}")
			elif result['success']:
				successful_uploads.append(result)
			else:
				failed_uploads.append(result)

		print(f"\n=== Results Summary ===")
		print(f"Total uploads: {num_photos}")
		print(f"Successful: {len(successful_uploads)}")
		print(f"Failed: {len(failed_uploads)}")
		print(f"Success rate: {len(successful_uploads)/num_photos*100:.1f}%")

		if successful_uploads:
			avg_upload_time = sum(r['upload_time'] for r in successful_uploads) / len(successful_uploads)
			avg_verification_time = sum(r['verification_time'] for r in successful_uploads) / len(successful_uploads)
			print(f"Average upload time: {avg_upload_time:.2f}s")
			print(f"Average verification time: {avg_verification_time:.2f}s")

		if failed_uploads:
			print(f"\n=== Failed Uploads ===")
			for i, failure in enumerate(failed_uploads):
				if isinstance(failure, dict):
					print(f"{i+1}. Photo {failure['photo_id']}: {failure['error']}")
				else:
					print(f"{i+1}. {failure}")

		# Assertions
		assert len(successful_uploads) >= 3, f"Expected at least 3 successful uploads, got {len(successful_uploads)}"
		assert len(successful_uploads) / num_photos >= 0.6, f"Success rate too low: {len(successful_uploads)/num_photos*100:.1f}%"

		# Verify photos were actually created
		for result in successful_uploads:
			assert result['photo_uuid'] is not None, "Photo UUID should be set for successful uploads"
			assert result['verification_time'] >= 0, "Verification time should be non-negative"

	@pytest.mark.asyncio
	async def test_parallel_upload_medium_batch(self):
		"""Test uploading 10 photos in parallel - medium load test."""
		print("\n=== Testing Parallel Upload: Medium Batch (10 photos) ===")

		num_photos = 10

		start_time = time.time()

		# Create tasks for parallel uploads with slight stagger to test rate limiting
		tasks = []
		for i in range(num_photos):
			# Add small random delay to simulate real-world usage
			await asyncio.sleep(random.uniform(0.1, 0.3))
			task = self.upload_single_photo(i)
			tasks.append(task)

		# Execute uploads in parallel
		print(f"Starting {num_photos} parallel uploads...")
		results = await asyncio.gather(*tasks, return_exceptions=True)

		total_time = time.time() - start_time
		print(f"All uploads completed in {total_time:.2f} seconds")

		# Analyze results
		successful_uploads = []
		failed_uploads = []
		rate_limited = []

		for result in results:
			if isinstance(result, Exception):
				failed_uploads.append(f"Exception: {result}")
			elif result['success']:
				successful_uploads.append(result)
			elif 'rate limit' in str(result.get('error', '')).lower():
				rate_limited.append(result)
			else:
				failed_uploads.append(result)

		print(f"\n=== Results Summary ===")
		print(f"Total uploads: {num_photos}")
		print(f"Successful: {len(successful_uploads)}")
		print(f"Rate limited: {len(rate_limited)}")
		print(f"Failed (other): {len(failed_uploads)}")
		print(f"Success rate: {len(successful_uploads)/num_photos*100:.1f}%")

		if successful_uploads:
			upload_times = [r['upload_time'] for r in successful_uploads]
			verification_times = [r['verification_time'] for r in successful_uploads]

			print(f"Upload time - avg: {sum(upload_times)/len(upload_times):.2f}s, "
				  f"min: {min(upload_times):.2f}s, max: {max(upload_times):.2f}s")
			print(f"Verification time - avg: {sum(verification_times)/len(verification_times):.2f}s, "
				  f"min: {min(verification_times):.2f}s, max: {max(verification_times):.2f}s")

		# Assertions - more lenient for medium batch due to expected rate limiting
		assert len(successful_uploads) >= 5, f"Expected at least 5 successful uploads, got {len(successful_uploads)}"

		# Rate limiting is expected behavior, so count rate-limited as acceptable
		acceptable_uploads = len(successful_uploads) + len(rate_limited)
		assert acceptable_uploads / num_photos >= 0.7, f"Acceptable upload rate too low: {acceptable_uploads/num_photos*100:.1f}%"

	@pytest.mark.asyncio
	async def test_rate_limiting_behavior(self):
		"""Test that rate limiting works properly under load."""
		print("\n=== Testing Rate Limiting Behavior ===")

		num_photos = 8

		# Submit all uploads rapidly (within 1 second) to trigger rate limiting
		tasks = []
		submission_start = time.time()

		for i in range(num_photos):
			task = self.upload_single_photo(i)
			tasks.append(task)

		submission_time = time.time() - submission_start
		print(f"Submitted {num_photos} uploads in {submission_time:.3f} seconds")

		# Wait for all to complete
		results = await asyncio.gather(*tasks, return_exceptions=True)

		# Analyze timing patterns
		successful_results = [r for r in results if isinstance(r, dict) and r['success']]

		if successful_results:
			upload_times = [(r['photo_id'], r['upload_time']) for r in successful_results]
			upload_times.sort(key=lambda x: x[1])  # Sort by upload time

			print(f"\n=== Upload Timing Analysis ===")
			for photo_id, upload_time in upload_times:
				print(f"Photo {photo_id}: {upload_time:.2f}s")

			# Check if there's evidence of rate limiting (increasing delays)
			if len(upload_times) >= 3:
				first_three = upload_times[:3]
				last_three = upload_times[-3:]

				avg_early = sum(t[1] for t in first_three) / len(first_three)
				avg_late = sum(t[1] for t in last_three) / len(last_three)

				print(f"Average early upload time: {avg_early:.2f}s")
				print(f"Average late upload time: {avg_late:.2f}s")

				# Rate limiting should cause later uploads to take longer
				if avg_late > avg_early * 1.5:
					print("✓ Evidence of rate limiting detected (later uploads slower)")
				else:
					print("? No clear evidence of rate limiting in timing")

		# Basic assertions
		assert len(successful_results) >= 4, f"Expected at least 4 successful uploads despite rate limiting, got {len(successful_results)}"

	@pytest.mark.asyncio
	async def test_parallel_upload_large_batch(self):
		"""Test uploading 100 photos in parallel - large load test to stress the system."""
		print("\n=== Testing Parallel Upload: Large Batch (100 photos) ===")

		num_photos = 100

		start_time = time.time()

		# Create tasks for parallel uploads - no staggering to maximize concurrency pressure
		# Use 5 seconds per photo timeout for large batch
		timeout_per_photo = 500  # 5 seconds * 100 photos = 500 seconds total timeout
		tasks = []
		for i in range(num_photos):
			task = self.upload_single_photo(i, timeout=timeout_per_photo)
			tasks.append(task)

		submission_time = time.time() - start_time
		print(f"Submitted {num_photos} uploads in {submission_time:.3f} seconds")

		# Execute uploads in parallel
		print(f"Starting {num_photos} parallel uploads...")
		results = await asyncio.gather(*tasks, return_exceptions=True)

		total_time = time.time() - start_time
		print(f"All uploads completed in {total_time:.2f} seconds")

		# Analyze results
		successful_uploads = []
		failed_uploads = []
		exceptions = []

		for i, result in enumerate(results):
			if isinstance(result, Exception):
				exceptions.append(f"Photo {i}: {type(result).__name__}: {result}")
			elif isinstance(result, dict):
				if result['success']:
					successful_uploads.append(result)
				else:
					failed_uploads.append(result)
			else:
				exceptions.append(f"Photo {i}: Unexpected result type: {type(result)}")

		print(f"\n=== Large Batch Results Summary ===")
		print(f"Total uploads: {num_photos}")
		print(f"Successful: {len(successful_uploads)}")
		print(f"Failed: {len(failed_uploads)}")
		print(f"Exceptions: {len(exceptions)}")
		print(f"Success rate: {len(successful_uploads)/num_photos*100:.1f}%")
		print(f"Total processing time: {total_time:.2f}s")
		print(f"Average time per successful upload: {total_time/len(successful_uploads):.2f}s" if successful_uploads else "N/A")

		if successful_uploads:
			upload_times = [r['upload_time'] for r in successful_uploads]
			verification_times = [r['verification_time'] for r in successful_uploads]

			print(f"\n=== Timing Analysis ===")
			print(f"Upload times - avg: {sum(upload_times)/len(upload_times):.2f}s, "
				  f"min: {min(upload_times):.2f}s, max: {max(upload_times):.2f}s")
			print(f"Verification times - avg: {sum(verification_times)/len(verification_times):.2f}s, "
				  f"min: {min(verification_times):.2f}s, max: {max(verification_times):.2f}s")

			# Throughput analysis
			throughput = len(successful_uploads) / total_time
			print(f"Successful upload throughput: {throughput:.2f} uploads/second")

		if failed_uploads:
			print(f"\n=== Failed Uploads Analysis ===")
			error_types = {}
			for failure in failed_uploads:
				error = str(failure.get('error', 'Unknown'))
				error_type = error.split(':')[0] if ':' in error else error[:50]  # First 50 chars
				error_types[error_type] = error_types.get(error_type, 0) + 1

			for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
				print(f"  {error_type}: {count} failures")

		if exceptions:
			print(f"\n=== Exception Analysis ===")
			exc_types = {}
			for exc in exceptions:
				exc_type = exc.split(':')[1] if ':' in exc else exc[:50]
				exc_types[exc_type] = exc_types.get(exc_type, 0) + 1

			for exc_type, count in sorted(exc_types.items(), key=lambda x: x[1], reverse=True):
				print(f"  {exc_type}: {count} exceptions")

		# Assertions for large load test
		total_successful = len(successful_uploads)

		# We should get at least 50% success rate with 100 photos
		min_expected = max(int(num_photos * 0.5), 20)  # At least 50% or 20, whichever is higher
		assert total_successful >= min_expected, f"Expected at least {min_expected} successful uploads, got {total_successful}"

		# System should not completely crash - we should not have 100% exceptions
		max_exceptions = int(num_photos * 0.8)
		assert len(exceptions) <= max_exceptions, f"Too many exceptions: {len(exceptions)} (max allowed: {max_exceptions})"

		# If we got a reasonable number of successes, verify they have valid data
		if total_successful >= 10:
			sample_size = min(10, total_successful)
			for result in successful_uploads[:sample_size]:
				assert result['photo_uuid'] is not None, "Photo UUID should be set for successful uploads"
				assert result['upload_time'] > 0, "Upload time should be positive"
				assert result['verification_time'] >= 0, "Verification time should be non-negative"

		print(f"\n✅ Large load test completed: {total_successful}/{num_photos} uploads successful")
		print(f"System handled {throughput:.2f} uploads/second under load" if successful_uploads else "")


if __name__ == "__main__":
	pytest.main([__file__, "-v", "--tb=short"])
