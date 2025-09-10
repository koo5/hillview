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

# Add backend directory to path for imports
backend_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.append(backend_dir)

from common.jwt_utils import generate_ecdsa_key_pair, serialize_private_key, serialize_public_key
from .test_utils import recreate_test_users

class SecureUploadClient:
	"""
	Utility class for testing the secure upload workflow.

	Handles client key generation, signature creation, and the full three-phase workflow.
	"""

	def __init__(self, api_url: str = None):
		self.api_url = api_url or os.getenv("API_URL", "http://localhost:8055")
		self.client_keys = None
		self.key_id = None

	async def setup_test_environment(self):
		"""Set up test environment using shared test utility."""
		return recreate_test_users()


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
			response = await client.post(f"{self.api_url}/auth/token", data={
				"username": "test",
				"password": "StrongTestPassword123!"
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

	def generate_client_signature(self, client_private_key, photo_id: str, filename: str, timestamp: int) -> str:
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
				f"{self.api_url}/photos/",
				headers={"Authorization": f"Bearer {auth_token}"},
				follow_redirects=True
			)
			if response.status_code != 200:
				print(f"❌ Phase 1a failed: {response.status_code} - {response.text}")
				raise Exception(f"Authentication test failed: {response.status_code} - {response.text}")
			print("✅ Phase 1a: Client authentication successful")

			# Register client public key
			import datetime
			import uuid
			key_id = client_key_pair.get("key_id", f"test-key-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-{str(uuid.uuid4())[:8]}")
			response = await client.post(
				f"{self.api_url}/auth/register-client-key",
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

	async def _request_upload_authorization(self, auth_token: str, upload_request: dict):
		"""Internal method to make upload authorization request and handle response."""
		async with httpx.AsyncClient() as client:
			response = await client.post(
				f"{self.api_url}/photos/authorize-upload",
				json=upload_request,
				headers={"Authorization": f"Bearer {auth_token}"}
			)

			if response.status_code == 200:
				auth_data = response.json()
				assert "upload_jwt" in auth_data
				assert "worker_url" in auth_data
				assert "photo_id" in auth_data
				return auth_data
			elif response.status_code == 404:
				raise Exception("Upload authorization endpoint not implemented")
			else:
				raise Exception(f"Upload authorization failed: {response.status_code} - {response.text}")

	async def authorize_upload(self, auth_token: str, filename: str = "secure_test.jpg", **kwargs):
		"""Test Phase 2: Request upload authorization from API."""
		# Generate MD5 hash for test data
		import hashlib
		file_md5 = hashlib.md5(f"{filename}_5120".encode()).hexdigest()
		
		upload_request = {
			"filename": filename,
			"content_type": "image/jpeg",
			"file_size": 5120,
			"file_md5": file_md5,  # Add required MD5 hash
			"latitude": 50.0755,
			"longitude": 14.4378,
			"description": "End-to-end secure upload test",
			"is_public": True
		}

		auth_data = await self._request_upload_authorization(auth_token, upload_request)
		print(f"✅ Phase 2: Upload authorization successful")
		print(f"   Photo ID: {auth_data['photo_id']}")
		print(f"   Worker URL: {auth_data['worker_url']}")
		return auth_data

	async def authorize_upload_with_params(self, auth_token: str, filename: str, file_size: int,
										   latitude: float, longitude: float, description: str,
										   is_public: bool = True, file_data: bytes = None):
		"""Request upload authorization with custom parameters."""
		# Calculate MD5 hash for the file data
		import hashlib
		if file_data:
			file_md5 = hashlib.md5(file_data).hexdigest()
		else:
			# Generate a fake MD5 for test data if no file_data provided
			file_md5 = hashlib.md5(f"{filename}_{file_size}".encode()).hexdigest()
		
		upload_request = {
			"filename": filename,
			"content_type": "image/jpeg",
			"file_size": file_size,
			"file_md5": file_md5,  # Add required MD5 hash
			"latitude": latitude,
			"longitude": longitude,
			"description": description,
			"is_public": is_public
		}

		return await self._request_upload_authorization(auth_token, upload_request)

	async def upload_to_worker(self, file_input, auth_data, client_keys, filename="secure_test.jpg"):
		"""Phase 3: Upload file to worker with proper client signature.

		Args:
			file_input: Either a file path (str) or file data (bytes)
		"""
		upload_jwt = auth_data["upload_jwt"]
		worker_url = auth_data["worker_url"]
		photo_id = auth_data["photo_id"]

		# Get timestamp - now comes as Unix timestamp directly
		timestamp = auth_data["upload_authorized_at"]

		client_signature = self.generate_client_signature(
			client_keys["private_key"],
			photo_id,
			filename,
			timestamp
		)

		async with httpx.AsyncClient() as client:
			# Handle both file paths and file data
			if isinstance(file_input, bytes):
				# File data provided directly
				files = {'file': (filename, file_input, 'image/jpeg')}
			else:
				# File path provided, read the file
				with open(file_input, 'rb') as f:
					file_data = f.read()
				files = {'file': (filename, file_data, 'image/jpeg')}

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
			response = await client.get(f"{self.api_url}/debug")
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
