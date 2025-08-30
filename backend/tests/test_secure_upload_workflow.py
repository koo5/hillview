"""
Integration test for the complete secure upload workflow.
Tests the real three-phase cryptographic flow using actual JWT tokens.
"""

import pytest
import os
import tempfile
from PIL import Image
from secure_upload_utils import SecureUploadClient

class TestSecureUploadWorkflow:
	"""Integration tests for the real secure upload workflow using SecureUploadClient utility."""

	@pytest.fixture
	def upload_client(self):
		"""Create SecureUploadClient instance for testing."""
		return SecureUploadClient(api_url=os.getenv("TEST_API_URL", "http://localhost:8055"))

	@pytest.fixture
	def test_image(self):
		"""Create a test image file with EXIF data."""
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
			key_result = await upload_client.register_client_key(test_user_auth)
			print("✅ Phase 1: Client key registered successfully")
			print(f"   Key ID: {key_result}")
			return {"key_id": key_result}
		except Exception as e:
			pytest.fail(f"Phase 1 failed: {e}")

	@pytest.mark.asyncio
	async def test_phase2_upload_authorization(self, test_user_auth, upload_client, filename="secure_test.jpg"):
		"""Test Phase 2: Request upload authorization from API using utility."""
		try:
			auth_data = await upload_client.authorize_upload(test_user_auth, filename)
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
		await upload_client.register_client_key(test_user_auth, client_keys)
		auth_data = await upload_client.authorize_upload(test_user_auth, "secure_test.jpg")
		
		# Use utility method to upload to worker
		result = await upload_client.upload_to_worker(test_image, auth_data, client_keys, "secure_test.jpg")
		print(f"✅ Phase 3: Worker processed upload successfully")
		print(f"   Photo ID: {result.get('photo_id', 'unknown')}")
		return result

	@pytest.mark.asyncio
	async def test_complete_secure_upload_workflow(self, test_image, upload_client):
		"""Test the complete end-to-end secure upload workflow using SecureUploadClient."""
		await upload_client.test_complete_secure_upload_workflow(test_image)

	@pytest.mark.asyncio
	async def test_worker_token_validation(self, test_user_auth, upload_client):
		"""Test that worker properly validates JWT authorization tokens using utility."""
		await upload_client.test_worker_token_validation(test_user_auth)

	@pytest.mark.asyncio
	async def test_api_server_connectivity(self, upload_client):
		"""Test basic API server health using utility."""
		await upload_client.test_api_server_connectivity()

	@pytest.mark.asyncio
	async def test_worker_server_connectivity(self, upload_client):
		"""Test basic worker server health using utility."""
		await upload_client.test_worker_server_connectivity()

if __name__ == "__main__":
	# Run with: python -m pytest tests/test_secure_upload_workflow.py -v -s
	pytest.main([__file__, "-v", "-s", "--tb=short"])
