"""Integration tests for the license field on the authorize-upload endpoint.

Verifies that the `license` field in the upload authorization request is
accepted, validated, and persisted on the Photo row as `legal_rights`.
"""
import os
import sys
import pytest
import pytest_asyncio
import httpx

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.secure_upload_utils import SecureUploadClient


class TestUploadLicense:
    @pytest.fixture
    def upload_client(self):
        return SecureUploadClient(api_url=os.getenv("API_URL", "http://localhost:8055/api"))

    @pytest_asyncio.fixture
    async def auth_token(self, upload_client):
        setup_result = await upload_client.setup_test_environment()
        token = await upload_client.test_user_auth(setup_result)
        client_keys = upload_client.generate_client_keys()
        await upload_client.register_client_key(token, client_keys)
        return token

    @pytest.mark.asyncio
    async def test_valid_license_accepted(self, auth_token):
        """Sending a valid license identifier creates an authorized photo."""
        token = auth_token
        client = SecureUploadClient(api_url=os.getenv("API_URL", "http://localhost:8055/api"))
        client_keys = client.generate_client_keys()
        await client.register_client_key(token, client_keys)

        auth_data = await client.authorize_upload_with_params(
            auth_token=token,
            filename="license_valid.jpg",
            file_size=1024,
            latitude=50.0,
            longitude=14.0,
            description="valid license test",
            license='ccbysa4+osm',
        )
        assert "photo_id" in auth_data
        assert "upload_jwt" in auth_data

    @pytest.mark.asyncio
    async def test_invalid_license_rejected(self, auth_token):
        """Unknown license identifier returns 400."""
        token = auth_token
        client = SecureUploadClient(api_url=os.getenv("API_URL", "http://localhost:8055/api"))
        client_keys = client.generate_client_keys()
        await client.register_client_key(token, client_keys)

        with pytest.raises(Exception) as exc_info:
            await client.authorize_upload_with_params(
                auth_token=token,
                filename="license_invalid.jpg",
                file_size=1024,
                latitude=50.0,
                longitude=14.0,
                description="invalid license test",
                license='made-up-license',
            )
        assert '400' in str(exc_info.value) or 'Unknown license' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_license_accepted(self, auth_token):
        """Omitting license (None) is accepted — field is optional."""
        token = auth_token
        client = SecureUploadClient(api_url=os.getenv("API_URL", "http://localhost:8055/api"))
        client_keys = client.generate_client_keys()
        await client.register_client_key(token, client_keys)

        auth_data = await client.authorize_upload_with_params(
            auth_token=token,
            filename="license_none.jpg",
            file_size=1024,
            latitude=50.0,
            longitude=14.0,
            description="no license test",
            license=None,
        )
        assert "photo_id" in auth_data
