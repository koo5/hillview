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


    @pytest.mark.asyncio
    @pytest.mark.parametrize('intake,share,outflow', [
        ('full1', True, 'panoramax'),
        ('full1', False, 'arr'),
        ('panoramax_in', False, 'panoramax'),
        ('panoramax_in', True, 'panoramax'),
        ('ccbysa4+osm', True, 'ccbysa4+osm'),
    ])
    async def test_panoramax_upload_choice_persists(self, upload_client, auth_token, intake, share, outflow):
        auth = await upload_client.authorize_upload_with_params(
            auth_token=auth_token, filename=f'panoramax-{intake}-{share}.jpg',
            file_size=1024, latitude=50, longitude=14, description='Panoramax consent',
            license=intake, panoramax_share=share,
        )
        photo_id = auth['photo_id']
        url = f"{upload_client.api_url}/photos/public/hillview-{photo_id}"
        headers = {'Authorization': f'Bearer {auth_token}'}
        async with httpx.AsyncClient() as client:
            try:
                owner = await client.get(url, headers=headers)
                assert owner.status_code == 200, owner.text
                assert owner.json()['license'] == outflow
                assert owner.json()['license_granted'] == intake
                assert owner.json()['panoramax_share'] is share
                assert 'panoramax_approved' not in owner.json()
                public = await client.get(url)
                assert public.json()['license'] == outflow
                assert 'license_granted' not in public.json()
                assert 'panoramax_share' not in public.json()
            finally:
                await client.delete(f"{upload_client.api_url}/photos/{photo_id}", headers=headers)
