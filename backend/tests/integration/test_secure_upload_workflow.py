"""
Integration test for the complete secure upload workflow.
Tests the real three-phase cryptographic flow using actual JWT tokens.
"""

import pytest
import httpx
import os
import sys
import tempfile
from PIL import Image

# Add the backend and tests directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.secure_upload_utils import SecureUploadClient

class TestSecureUploadWorkflow:
	"""Integration tests for the real secure upload workflow using SecureUploadClient utility."""

	@pytest.fixture
	def upload_client(self):
		"""Create SecureUploadClient instance for testing."""
		return SecureUploadClient(api_url=os.getenv("API_URL", "http://localhost:8055/api"))

	@pytest.fixture
	def test_image(self):
		"""Create a test image file without EXIF data."""
		img = Image.new('RGB', (400, 300), color='blue')
		temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
		img.save(temp_file.name, 'JPEG', quality=95)
		temp_file.close()

		yield temp_file.name
		os.unlink(temp_file.name)

	@pytest.fixture
	async def test_user_auth(self, upload_client):
		"""Get authentication token for the test user using utility."""
		setup_result = await upload_client.setup_test_environment()
		return await upload_client.test_user_auth(setup_result)


	@pytest.mark.asyncio
	async def test_phase1_client_key_registration(self, test_user_auth, upload_client):
		"""Test Phase 1: Client authentication and public key registration using utility."""
		try:
			auth_token = await test_user_auth
			key_result = await upload_client.register_client_key(auth_token)
			print("✅ Phase 1: Client key registered successfully")
			print(f"   Key ID: {key_result}")
			return {"key_id": key_result}
		except Exception as e:
			pytest.fail(f"Phase 1 failed: {e}")

	@pytest.mark.asyncio
	async def test_phase2_upload_authorization(self, test_user_auth, upload_client, filename="secure_test.jpg"):
		"""Test Phase 2: Request upload authorization from API using utility."""
		try:
			auth_token = await test_user_auth
			# Register client key first (required for upload authorization)
			client_keys = upload_client.generate_client_keys()
			await upload_client.register_client_key(auth_token, client_keys)
			auth_data = await upload_client.authorize_upload(auth_token, filename)
			assert "upload_jwt" in auth_data
			assert "worker_url" in auth_data
			assert "photo_id" in auth_data

			print(f"✅ Phase 2: Upload authorization successful")
			print(f"   Photo ID: {auth_data['photo_id']}")
			print(f"   Worker URL: {auth_data['worker_url']}")
			return auth_data
		except Exception as e:
			pytest.fail(f"Phase 2 failed: {e}")

	@pytest.mark.asyncio
	async def test_phase3_worker_upload_processing(self, test_image, test_user_auth, upload_client):
		"""Test Phase 3: Worker processes upload with real authorization token."""
		# Register client key and get upload authorization using utility
		client_keys = upload_client.generate_client_keys()
		auth_token = await test_user_auth
		await upload_client.register_client_key(auth_token, client_keys)
		auth_data = await upload_client.authorize_upload(auth_token, "secure_test.jpg")

		# Use utility method to upload to worker
		result = await upload_client.upload_to_worker(test_image, auth_data, client_keys, "secure_test.jpg")
		print(f"✅ Phase 3: Worker processed upload successfully")
		print(f"   Photo ID: {result.get('photo_id', 'unknown')}")
		return result

	@pytest.mark.asyncio
	async def test_worker_token_validation(self, test_user_auth, upload_client):
		"""Test that worker properly validates JWT authorization tokens using utility."""
		auth_token = await test_user_auth
		# Register client key first (required for upload authorization)
		client_keys = upload_client.generate_client_keys()
		await upload_client.register_client_key(auth_token, client_keys)
		await upload_client.test_worker_token_validation(auth_token)

	@pytest.mark.asyncio
	async def test_api_server_connectivity(self, upload_client):
		"""Test basic API server health using utility."""
		await upload_client.test_api_server_connectivity()

	@pytest.mark.asyncio
	async def test_worker_server_connectivity(self, upload_client):
		"""Test basic worker server health using utility."""
		await upload_client.test_worker_server_connectivity()

	@pytest.mark.asyncio
	async def test_complete_secure_upload_workflow(self, test_image, upload_client):
		"""Test the complete end-to-end secure upload workflow with a bad photo."""
		print(f"\n{'='*60}")
		print(f"TESTING COMPLETE SECURE UPLOAD WORKFLOW")
		print(f"{'='*60}")

		# Test constants
		TEST_FILENAME = "secure_test.jpg"

		# Setup test environment using the fixture method
		setup_result = await upload_client.setup_test_environment()
		if not setup_result:
			raise Exception("Test environment setup failed")

		# Get auth token using the fixture method
		auth_token = await upload_client.test_user_auth(setup_result)

		# Phase 1: Client Authentication & Key Registration
		print(f"\n--- Phase 1: Client Authentication & Key Registration ---")


		# Generate client key pair for this workflow test
		import sys
		import os
		sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

		from common.jwt_utils import generate_ecdsa_key_pair, serialize_private_key, serialize_public_key

		private_key, public_key = generate_ecdsa_key_pair()
		client_keys = {
			"private_key": private_key,
			"public_key": public_key,
			"private_pem": serialize_private_key(private_key),
			"public_pem": serialize_public_key(public_key)
		}

		# Use the existing test method
		key_data = await upload_client.register_client_key(auth_token, client_keys)


		# Phase 2: Upload Authorization
		print(f"\n--- Phase 2: Upload Authorization ---")
		auth_data = await upload_client.authorize_upload(auth_token, TEST_FILENAME)
		if not auth_data:
			raise Exception("Phase 2 (upload authorization) failed: No authorization data returned")

		# Phase 3: Worker Processing
		print(f"\n--- Phase 3: Worker Processing ---")
		await upload_client.upload_to_worker(test_image, auth_data, client_keys, TEST_FILENAME)

		# Phase 4: Final Verification - Client checks photo was processed
		print(f"\n--- Phase 4: Final Verification ---")

		photo_id = auth_data["photo_id"]
		async with httpx.AsyncClient() as client:
			# Check that the photo appears in user's photo list
			response = await client.get(
				f"{upload_client.api_url}/photos",
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
					processing_status = processed_photo.get('processing_status', 'N/A')
					print(f"   Processing Status: {processing_status}")
					assert processing_status == "error", "Photo processing status should be 'error'"
				else:
					pytest.fail(f"❌ Phase 4: Photo {photo_id} not found in user's photo list")
			else:
				pytest.fail(f"❌ Phase 4: Failed to fetch user's photo list: {response.status_code} {response.text}")
