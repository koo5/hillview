#!/usr/bin/env python3
"""
Multi-Client Parallel Photo Upload Test

Tests realistic upload scenario where multiple clients each register
their key ONCE, then upload multiple photos in parallel.

This avoids the anti-pattern of registering a new key for every photo,
which overloads the API with concurrent DB writes.
"""

import asyncio
import pytest
import os
import sys
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BasePhotoTest
from utils.test_utils import API_URL, wait_for_photo_processing
from utils.image_utils import create_test_image_full_gps
from utils.secure_upload_utils import SecureUploadClient, generate_test_captured_at


@dataclass
class UploadResult:
	"""Result of a single photo upload."""
	client_id: int
	photo_id: int
	success: bool = False
	upload_time: float = 0.0
	verification_time: float = 0.0
	error: Optional[str] = None
	photo_uuid: Optional[str] = None


@dataclass
class ClientStats:
	"""Statistics for a single client's uploads."""
	client_id: int
	total_photos: int = 0
	successful: int = 0
	failed: int = 0
	total_time: float = 0.0
	results: List[UploadResult] = field(default_factory=list)


class SimulatedClient:
	"""A simulated upload client that registers its key once and uploads multiple photos."""

	def __init__(self, client_id: int, token: str, api_url: str = API_URL):
		self.client_id = client_id
		self.token = token
		self.api_url = api_url
		self.upload_client = SecureUploadClient(api_url=api_url)
		self.client_keys = None
		self.registered = False

	async def register(self):
		"""Register client key once."""
		if not self.registered:
			self.client_keys = self.upload_client.generate_client_keys()
			await self.upload_client.register_client_key(self.token, self.client_keys)
			self.registered = True
			print(f"  Client {self.client_id}: Key registered")

	async def upload_photo(self, photo_index: int, timeout: int = 60) -> UploadResult:
		"""Upload a single photo using pre-registered keys."""
		result = UploadResult(client_id=self.client_id, photo_id=photo_index)
		start_time = time.time()

		try:
			if not self.registered:
				raise Exception("Client key not registered")

			# Create unique test image
			# Offset coordinates by client_id and photo_index for uniqueness
			lat = 50.0755 + (self.client_id * 0.01) + (photo_index * 0.001)
			lon = 14.4378 + (self.client_id * 0.01) + (photo_index * 0.001)
			colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255)]
			color = colors[(self.client_id + photo_index) % len(colors)]

			image_data = create_test_image_full_gps(
				width=1024, height=768,  # Smaller images for faster processing
				color=color,
				lat=lat, lon=lon,
				bearing=((self.client_id * 30) + (photo_index * 10)) % 360
			)

			filename = f"client{self.client_id}_photo{photo_index}.jpg"
			description = f"Client {self.client_id} photo {photo_index}"

			upload_start = time.time()

			# Authorize upload
			auth_data = await self.upload_client.authorize_upload_with_params(
				self.token,
				filename,
				len(image_data),
				lat, lon,
				description,
				is_public=True,
				file_data=image_data,
				captured_at=generate_test_captured_at()
			)

			if auth_data.get("duplicate"):
				result.error = "Duplicate"
				result.upload_time = time.time() - upload_start
				return result

			# Upload to worker
			upload_result = await self.upload_client.upload_to_worker(
				image_data, auth_data, self.client_keys, filename, timeout=timeout
			)

			result.upload_time = time.time() - upload_start
			result.photo_uuid = upload_result.get('photo_id', auth_data.get('photo_id'))

			# Wait for processing
			verification_start = time.time()
			final_status = wait_for_photo_processing(result.photo_uuid, self.token, timeout=timeout)
			result.verification_time = time.time() - verification_start

			if final_status and final_status.get('processing_status') == 'completed':
				result.success = True
			else:
				result.error = f"Processing failed: {final_status.get('error', 'unknown')}"

		except asyncio.TimeoutError as e:
			result.error = f"Timeout: {e}"
			result.upload_time = time.time() - start_time
		except Exception as e:
			result.error = f"{type(e).__name__}: {str(e)}"
			result.upload_time = time.time() - start_time

		return result


class TestMultiClientUploads(BasePhotoTest):
	"""Test parallel photo uploads with multiple simulated clients."""

	def setup_method(self):
		"""Setup for each test method"""
		super().setup_method()

	async def run_multi_client_upload(
		self,
		num_clients: int,
		photos_per_client: int,
		max_concurrent_per_client: int = 5,
		timeout: int = 60
	) -> Dict[int, ClientStats]:
		"""
		Run uploads with multiple clients, each uploading multiple photos.

		Args:
			num_clients: Number of simulated clients
			photos_per_client: Photos each client uploads
			max_concurrent_per_client: Max concurrent uploads per client
			timeout: Timeout per photo upload
		"""
		total_photos = num_clients * photos_per_client
		print(f"\n  {num_clients} clients × {photos_per_client} photos = {total_photos} total")
		print(f"  Max {max_concurrent_per_client} concurrent uploads per client")

		# Create and register all clients first
		print("\n  Registering client keys...")
		clients = []
		for i in range(num_clients):
			client = SimulatedClient(i, self.test_token, API_URL)
			await client.register()
			clients.append(client)

		# Stats per client
		client_stats: Dict[int, ClientStats] = {
			i: ClientStats(client_id=i, total_photos=photos_per_client)
			for i in range(num_clients)
		}

		async def client_upload_batch(client: SimulatedClient):
			"""Upload all photos for a single client with concurrency limit."""
			semaphore = asyncio.Semaphore(max_concurrent_per_client)
			stats = client_stats[client.client_id]
			start_time = time.time()

			async def upload_with_semaphore(photo_idx: int):
				async with semaphore:
					return await client.upload_photo(photo_idx, timeout=timeout)

			# Create tasks for all photos this client needs to upload
			tasks = [upload_with_semaphore(i) for i in range(photos_per_client)]
			results = await asyncio.gather(*tasks, return_exceptions=True)

			stats.total_time = time.time() - start_time

			for result in results:
				if isinstance(result, Exception):
					stats.failed += 1
					stats.results.append(UploadResult(
						client_id=client.client_id,
						photo_id=-1,
						error=f"Exception: {result}"
					))
				elif result.success:
					stats.successful += 1
					stats.results.append(result)
					print(f"  ✓ C{client.client_id}P{result.photo_id} "
						  f"({result.upload_time:.1f}s + {result.verification_time:.1f}s)")
				else:
					stats.failed += 1
					stats.results.append(result)
					print(f"  ✗ C{client.client_id}P{result.photo_id}: {result.error}")

		# Run all clients in parallel
		print("\n  Uploading photos...")
		overall_start = time.time()
		await asyncio.gather(*[client_upload_batch(c) for c in clients])
		overall_time = time.time() - overall_start

		# Summary
		total_successful = sum(s.successful for s in client_stats.values())
		total_failed = sum(s.failed for s in client_stats.values())

		print("\n  === Summary ===")
		print(f"  Total: {total_photos}, Successful: {total_successful}, Failed: {total_failed}")
		print(f"  Success rate: {total_successful/total_photos*100:.1f}%")
		print(f"  Total time: {overall_time:.2f}s")
		if total_successful > 0:
			print(f"  Throughput: {total_successful/overall_time:.2f} photos/sec")

		print("\n  Per-client stats:")
		for cid, stats in client_stats.items():
			print(f"    Client {cid}: {stats.successful}/{stats.total_photos} "
				  f"in {stats.total_time:.1f}s")

		return client_stats

	@pytest.mark.asyncio
	async def test_multi_client_small(self):
		"""Test 2 clients × 3 photos = 6 total uploads."""
		print("\n=== Multi-Client Small: 2 clients × 3 photos ===")

		stats = await self.run_multi_client_upload(
			num_clients=2,
			photos_per_client=3,
			max_concurrent_per_client=3,
			timeout=60
		)

		total_successful = sum(s.successful for s in stats.values())
		assert total_successful >= 4, f"Expected at least 4 successful, got {total_successful}"

	@pytest.mark.asyncio
	async def test_multi_client_medium(self):
		"""Test 3 clients × 5 photos = 15 total uploads."""
		print("\n=== Multi-Client Medium: 3 clients × 5 photos ===")

		stats = await self.run_multi_client_upload(
			num_clients=3,
			photos_per_client=5,
			max_concurrent_per_client=3,
			timeout=120
		)

		total_successful = sum(s.successful for s in stats.values())
		assert total_successful >= 10, f"Expected at least 10 successful, got {total_successful}"

	@pytest.mark.asyncio
	async def test_multi_client_large(self):
		"""Test 5 clients × 20 photos = 100 total uploads."""
		print("\n=== Multi-Client Large: 5 clients × 20 photos ===")

		stats = await self.run_multi_client_upload(
			num_clients=5,
			photos_per_client=20,
			max_concurrent_per_client=5,
			timeout=300
		)

		total_successful = sum(s.successful for s in stats.values())
		total_photos = 100

		# Large batch should still achieve reasonable success rate
		assert total_successful >= 50, f"Expected at least 50 successful, got {total_successful}"

		# Verify some photos have valid data
		all_results = [r for s in stats.values() for r in s.results if r.success]
		sample = all_results[:10] if len(all_results) >= 10 else all_results
		for result in sample:
			assert result.photo_uuid is not None, "Photo UUID should be set"
			assert result.upload_time > 0, "Upload time should be positive"

		print(f"\n✅ Large batch test: {total_successful}/{total_photos} successful")


if __name__ == "__main__":
	pytest.main([__file__, "-v", "--tb=short"])
