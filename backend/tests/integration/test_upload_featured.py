"""Integration tests for the admin-gated `featured` field on authorize-upload.

`featured` promotes a photo into the map's featured set, so it must not be
self-serviceable: a non-admin sending `featured=true` is rejected with 403,
while an admin's request is accepted and persisted on the Photo row. An absent
/ false `featured` (the default) leaves ordinary uploads unaffected.

The gate lives in authorize-upload — the only point in the upload flow with a
real authenticated user identity (the worker's upload JWT carries no role).
"""
import os
import sys
import pytest
import pytest_asyncio
import httpx

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.secure_upload_utils import SecureUploadClient

API_URL = os.getenv("API_URL", "http://localhost:8055/api")


async def _login(username: str, password: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{API_URL}/auth/token", data={
            "username": username, "password": password,
        })
        if resp.status_code != 200:
            raise Exception(f"login failed for {username}: {resp.status_code} - {resp.text}")
        return resp.json()["access_token"]


async def _client_for(token: str) -> SecureUploadClient:
    """A SecureUploadClient with a freshly-registered client key for `token`'s user."""
    client = SecureUploadClient(api_url=API_URL)
    client_keys = client.generate_client_keys()
    await client.register_client_key(token, client_keys)
    return client


class TestUploadFeatured:
    @pytest.mark.asyncio
    async def test_featured_rejected_for_non_admin(self):
        """A non-admin (`test`) requesting featured=true is rejected with 403."""
        client = SecureUploadClient(api_url=API_URL)
        await client.setup_test_environment()  # provision users (test + admin)
        token = await _login("test", "StrongTestPassword123!")
        client = await _client_for(token)

        with pytest.raises(Exception) as exc_info:
            await client.authorize_upload_with_params(
                auth_token=token,
                filename="featured_nonadmin.jpg",
                file_size=1024,
                latitude=50.0,
                longitude=14.0,
                description="non-admin featured attempt",
                license='ccbysa4+osm',
                featured=True,
            )
        assert '403' in str(exc_info.value) or 'admin' in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_featured_accepted_for_admin(self):
        """An admin requesting featured=true gets an authorized photo."""
        client = SecureUploadClient(api_url=API_URL)
        await client.setup_test_environment()
        token = await _login("admin", "StrongAdminPassword123!")
        client = await _client_for(token)

        auth_data = await client.authorize_upload_with_params(
            auth_token=token,
            filename="featured_admin.jpg",
            file_size=1024,
            latitude=50.0,
            longitude=14.0,
            description="admin featured attempt",
            license='ccbysa4+osm',
            featured=True,
        )
        assert "photo_id" in auth_data
        assert "upload_jwt" in auth_data

    @pytest.mark.asyncio
    async def test_non_featured_accepted_for_non_admin(self):
        """The default (featured omitted / false) leaves non-admin uploads intact."""
        client = SecureUploadClient(api_url=API_URL)
        await client.setup_test_environment()
        token = await _login("test", "StrongTestPassword123!")
        client = await _client_for(token)

        auth_data = await client.authorize_upload_with_params(
            auth_token=token,
            filename="featured_default.jpg",
            file_size=1024,
            latitude=50.0,
            longitude=14.0,
            description="non-admin default (no featured)",
            license='ccbysa4+osm',
        )
        assert "photo_id" in auth_data
