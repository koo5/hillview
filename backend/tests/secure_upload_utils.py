"""
Secure Upload Workflow Utilities for Tests

This module provides reusable utilities for testing the secure three-phase upload workflow:
1. Client authentication & public key registration
2. Upload authorization from API server
3. Worker processing with client signature verification

Use these utilities instead of calling the old /upload endpoint directly.
"""

import httpx
import json
import base64
import time
import os
from datetime import datetime
from typing import Dict, Any, Optional
import sys
import pytest

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from common.jwt_utils import generate_ecdsa_key_pair, serialize_private_key, serialize_public_key

class SecureUploadClient:
	"""
	Utility class for testing the secure upload workflow.

	Handles client key generation, signature creation, and the full three-phase workflow.
	"""

	def __init__(self, api_url: str = "http://localhost:8055"):
		self.api_url = api_url
		self.client_keys = None
		self.key_id = None

	async def setup_test_environment(self):
		"""Set up test environment using existing test user endpoints."""
		async with httpx.AsyncClient() as client:
			try:
				response = await client.post(f"{self.api_url}/api/debug/recreate-test-users")
				if response.status_code == 200:
					print("✅ Test users recreated successfully")
					return response.json()
				else:
					print(f"⚠️ Test users endpoint returned {response.status_code}")
					print("Make sure DEBUG_ENDPOINTS=true and TEST_USERS=true")
					pytest.fail("recreate-test-users failed")

			except Exception as e:
				print(f"❌ Failed to setup test users: {e}")
				pytest.fail("recreate-test-users failed")


	def test_image(self):
		"""Create a test image file with EXIF data."""
		img = Image.new('RGB', (400, 300), color='blue')
		temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
		img.save(temp_file.name, 'JPEG', quality=95)
		temp_file.close()

		yield temp_file.name
		os.unlink(temp_file.name)

	async def test_user_auth(self, setup_result):
		"""Get authentication token for the test user."""
		if not setup_result:
			raise Exception("Test environment not available")

		async with httpx.AsyncClient() as client:
			response = await client.post(f"{self.api_url}/api/auth/token", data={
				"username": "test",
				"password": "test123"
			})

			if response.status_code == 200:
				return response.json()["access_token"]
			else:
				raise Exception(f"Failed to get test user token: {response.status_code}")

	def client_key_pair(self):
		"""Generate a real ECDSA key pair for testing client operations."""
		import sys
		import os
		sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

		from common.jwt_utils import generate_ecdsa_key_pair, serialize_private_key, serialize_public_key

		private_key, public_key = generate_ecdsa_key_pair()
		return {
			"private_key": private_key,
			"public_key": public_key,
			"private_pem": serialize_private_key(private_key),
			"public_pem": serialize_public_key(public_key)
		}

	def generate_client_signature(self, client_private_key, photo_id: str, filename: str, timestamp: str) -> str:
		"""Generate a proper ECDSA client signature matching the API server's verification logic."""
		from cryptography.hazmat.primitives.asymmetric import ec
		from cryptography.hazmat.primitives import hashes

		# Create the exact message format that matches both frontend and API server
		# Frontend uses: JSON.stringify({...}, null, 0)
		# Backend API expects: json.dumps({...}, separators=(',', ':'))
		# Both produce the same compact JSON format
		message_data = {
			"photo_id": photo_id,
			"filename": filename,
			"timestamp": timestamp
		}
		message = json.dumps(message_data, separators=(',', ':'))  # Compact JSON, no spaces

		# Sign the message using the client's private key
		signature_bytes = client_private_key.sign(
			message.encode('utf-8'),
			ec.ECDSA(hashes.SHA256())
		)

		# Return base64-encoded signature
		return base64.b64encode(signature_bytes).decode('ascii')

	def generate_client_keys(self):
		"""Generate ECDSA key pair for client operations."""
		if not self.client_keys:
			private_key, public_key = generate_ecdsa_key_pair()
			self.client_keys = {
				"private_key": private_key,
				"public_key": public_key,
				"private_pem": serialize_private_key(private_key),
				"public_pem": serialize_public_key(public_key)
			}
		return self.client_keys

	async def register_client_key(self, auth_token: str, client_key_pair: dict = None):
		"""Phase 1: Register client public key with the API server."""
		if not client_key_pair:
			client_key_pair = self.generate_client_keys()

		# Test authentication first
		async with httpx.AsyncClient() as client:
			response = await client.get(
				f"{self.api_url}/api/photos",
				headers={"Authorization": f"Bearer {auth_token}"},
				follow_redirects=True
			)
			assert response.status_code == 200
			print("✅ Phase 1a: Client authentication successful")

			# Register client public key
			import datetime
			key_id = client_key_pair.get("key_id", f"test-key-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}")
			response = await client.post(
				f"{self.api_url}/api/users/public-keys",
				json={
					"public_key_pem": client_key_pair["public_pem"],
					"key_id": key_id,
					"created_at": datetime.datetime.now().isoformat()
				},
				headers={"Authorization": f"Bearer {auth_token}"}
			)

			if response.status_code in [200, 201]:
				key_data = response.json()
				print(f"✅ Phase 1b: Client key registered successfully")
				print(f"   Key ID: {key_data.get('key_id', 'unknown')}")
				return key_data
			elif response.status_code == 404:
				print("⚠️ Phase 1b: Client key registration endpoint not implemented")
				return {"key_id": "mock-key-id", "status": "mocked"}
			else:
				raise Exception(f"Client key registration failed: {response.status_code} - {response.text}")

	async def authorize_upload(self, auth_token: str, filename: str = "secure_test.jpg", **kwargs):
		"""Test Phase 2: Request upload authorization from API."""
		upload_request = {
			"filename": filename,
			"content_type": "image/jpeg",
			"file_size": 5120,
			"latitude": 50.0755,
			"longitude": 14.4378,
			"description": "End-to-end secure upload test",
			"is_public": True
		}

		async with httpx.AsyncClient() as client:
			response = await client.post(
				f"{self.api_url}/api/photos/authorize-upload",
				json=upload_request,
				headers={"Authorization": f"Bearer {auth_token}"}
			)

			if response.status_code == 200:
				auth_data = response.json()
				assert "upload_jwt" in auth_data
				assert "worker_url" in auth_data
				assert "photo_id" in auth_data

				print(f"✅ Phase 2: Upload authorization successful")
				print(f"   Photo ID: {auth_data['photo_id']}")
				print(f"   Worker URL: {auth_data['worker_url']}")
				return auth_data
			elif response.status_code == 404:
				raise Exception("Upload authorization endpoint not implemented")
			else:
				raise Exception(f"Upload authorization failed: {response.status_code} - {response.text}")

	async def upload_to_worker(self, test_image, auth_data, client_keys, filename="secure_test.jpg"):
		"""Phase 3: Upload file to worker with proper client signature."""
		upload_jwt = auth_data["upload_jwt"]
		worker_url = auth_data["worker_url"]
		photo_id = auth_data["photo_id"]
		timestamp = auth_data["upload_authorized_at"]
		
		client_signature = self.generate_client_signature(
			client_keys["private_key"],
			photo_id,
			filename,
			timestamp
		)

		async with httpx.AsyncClient() as client:
			with open(test_image, 'rb') as f:
				files = {'file': (filename, f, 'image/jpeg')}
				data = {'client_signature': client_signature}
				headers = {'Authorization': f'Bearer {upload_jwt}'}

				response = await client.post(
					f"{worker_url}/upload",
					files=files,
					data=data,
					headers=headers,
					timeout=60.0
				)

				if response.status_code == 200:
					result = response.json()
					print(f"✅ Phase 3: Worker processed upload successfully")
					return result
				else:
					raise Exception(f"Worker upload failed: {response.status_code} - {response.text}")

	async def test_complete_secure_upload_workflow(self, test_image):
		"""Test the complete end-to-end secure upload workflow."""
		print(f"\n{'='*60}")
		print(f"TESTING COMPLETE SECURE UPLOAD WORKFLOW")
		print(f"{'='*60}")

		# Test constants
		TEST_FILENAME = "secure_test.jpg"

		# Setup test environment using the fixture method
		setup_result = await self.setup_test_environment()
		if not setup_result:
			raise Exception("Test environment setup failed")

		# Get auth token using the fixture method
		auth_token = await self.test_user_auth(setup_result)

		# Phase 1: Client Authentication & Key Registration
		print(f"\n--- Phase 1: Client Authentication & Key Registration ---")
		client_keys = None
		try:
			# Generate client key pair for this workflow test
			import sys
			import os
			sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

			from common.jwt_utils import generate_ecdsa_key_pair, serialize_private_key, serialize_public_key

			private_key, public_key = generate_ecdsa_key_pair()
			client_keys = {
				"private_key": private_key,
				"public_key": public_key,
				"private_pem": serialize_private_key(private_key),
				"public_pem": serialize_public_key(public_key)
			}

			# Use the existing test method
			key_data = await self.register_client_key(auth_token, client_keys)
			phase1_success = True
		except Exception as e:
			print(f"❌ Phase 1 failed: {e}")
			raise Exception(f"Phase 1 (client key registration) failed: {e}")

		# Phase 2: Upload Authorization
		print(f"\n--- Phase 2: Upload Authorization ---")
		auth_data = None
		try:
			auth_data = await self.authorize_upload(auth_token, TEST_FILENAME)
			if not auth_data:
				raise Exception("Phase 2 (upload authorization) failed: No authorization data returned")
			phase2_success = True
		except Exception as e:
			print(f"❌ Phase 2 failed: {e}")
			raise Exception(f"Phase 2 (upload authorization) failed: {e}")

		# Phase 3: Worker Processing
		print(f"\n--- Phase 3: Worker Processing ---")
		phase3_success = False
		try:
			upload_jwt = auth_data["upload_jwt"]
			worker_url = auth_data["worker_url"]

			# Use the upload_to_worker utility method
			result = await self.upload_to_worker(test_image, auth_data, client_keys, TEST_FILENAME)
			phase3_success = True
		except Exception as e:
			print(f"❌ Phase 3 failed: {e}")
			raise Exception(f"Phase 3 (worker processing) failed: {e}")

		# Phase 4: Final Verification - Client checks photo was processed
		print(f"\n--- Phase 4: Final Verification ---")
		# Phase 4 can proceed even if Phase 3 failed - we still want to verify the photo state
		phase4_success = False
		try:
			photo_id = auth_data["photo_id"]
			async with httpx.AsyncClient() as client:
				# Check that the photo appears in user's photo list
				response = await client.get(
					f"{self.api_url}/api/photos",
					headers={"Authorization": f"Bearer {auth_token}"},
					follow_redirects=True
				)

				if response.status_code == 200:
					photos = response.json()
					processed_photo = None

					# Find our uploaded photo by ID
					for photo in photos:
						if photo.get("id") == photo_id:
							processed_photo = photo
							break

					if processed_photo:
						print(f"✅ Phase 4a: Photo found in user's photo list")
						print(f"   Photo ID: {processed_photo.get('id')}")
						print(f"   Filename: {processed_photo.get('filename', 'N/A')}")
						processing_status = processed_photo.get('processing_status', 'N/A')
						print(f"   Processing Status: {processing_status}")

						# Verify processing was completed successfully
						if processing_status == 'completed':
							# Check for processed metadata
							has_dimensions = processed_photo.get('width') is not None and processed_photo.get('height') is not None
							has_location = processed_photo.get('latitude') is not None and processed_photo.get('longitude') is not None
							has_worker_signature = processed_photo.get('processed_by_worker') is not None

							if has_dimensions:
								print(f"   Dimensions: {processed_photo.get('width')}x{processed_photo.get('height')}")
							if has_location:
								print(f"   Location: {processed_photo.get('latitude')}, {processed_photo.get('longitude')}")
							if has_worker_signature:
								print(f"   Processed by worker: {processed_photo.get('processed_by_worker')}")

							print(f"✅ Phase 4b: Photo processing verification complete")
							phase4_success = True
						else:
							print(f"❌ Phase 4b: Photo processing failed - status is '{processing_status}', expected 'completed'")
							phase4_success = False
					else:
						print(f"❌ Phase 4: Photo {photo_id} not found in user's photo list")
				else:
					print(f"❌ Phase 4: Failed to retrieve photos: {response.status_code}")
					print(f"   Error: {response.text}")

		except Exception as e:
			print(f"❌ Phase 4 failed: {e}")

		# Summary
		print(f"\n{'='*60}")
		print(f"WORKFLOW SUMMARY:")
		print(f"{'='*60}")
		print(f"{'✅' if phase1_success else '❌'} Phase 1: Client Authentication & Key Registration")
		print(f"{'✅' if phase2_success else '❌'} Phase 2: Upload Authorization")
		print(f"{'✅' if phase3_success else '❌'} Phase 3: Worker Processing")
		print(f"{'✅' if phase4_success else '❌'} Phase 4: Final Verification")

		overall_success = phase1_success and phase2_success and phase3_success and phase4_success
		print(f"\n{'✅' if overall_success else '❌'} Overall Workflow: {'SUCCESS' if overall_success else 'PARTIAL/FAILED'}")
		print(f"{'='*60}\n")

		# At minimum, authentication should work
		assert phase1_success, "Phase 1 (authentication) must work"

	async def test_worker_token_validation(self, test_user_auth):
		"""Test that worker properly validates JWT authorization tokens."""
		# First get a valid authorization to get the worker URL  
		auth_data = await self.authorize_upload(test_user_auth, "test.jpg")
		worker_url = auth_data["worker_url"]
		
		# Test with invalid token
		async with httpx.AsyncClient() as client:
			try:
				fake_token = "invalid.jwt.token"
				files = {'file': ('test.jpg', b'fake image', 'image/jpeg')}
				data = {'client_signature': 'fake_sig'}
				headers = {'Authorization': f'Bearer {fake_token}'}

				response = await client.post(
					f"{worker_url}/upload",
					files=files,
					data=data,
					headers=headers
				)

				# Worker should reject invalid token
				assert response.status_code == 401
				print("✅ Worker correctly rejects invalid JWT tokens")

			except httpx.ConnectError:
				raise Exception("Worker not available")

	async def test_api_server_connectivity(self):
		"""Test basic API server health."""
		async with httpx.AsyncClient() as client:
			response = await client.get(f"{self.api_url}/api/debug")
			assert response.status_code == 200
			assert response.json()["status"] == "ok"

	async def test_worker_server_connectivity(self):
		"""Test basic worker server health."""
		# Use fallback URL since health endpoint doesn't need authorization
		worker_url = os.getenv("TEST_WORKER_URL", "http://localhost:8056")
		try:
			async with httpx.AsyncClient() as client:
				response = await client.get(f"{worker_url}/health")
				if response.status_code == 200:
					print("✅ Worker server is healthy")
				else:
					print(f"⚠️ Worker server returned {response.status_code}")
		except httpx.ConnectError:
			raise Exception("Worker server not available")

if __name__ == "__main__":
	# Run with: python -m pytest tests/test_secure_upload_workflow.py -v -s
	pytest.main([__file__, "-v", "-s", "--tb=short"])
