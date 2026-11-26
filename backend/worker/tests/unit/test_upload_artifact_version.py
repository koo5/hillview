from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import pytest

import app as worker


@pytest.mark.parametrize('version', [None, '7'])
def test_optional_worker_version_does_not_require_client_upgrade(monkeypatch, version):
    upload = AsyncMock(return_value={'success': True, 'photo_id': 'photo', 'message': 'processed'})
    monkeypatch.setattr(worker, 'upload', upload)
    monkeypatch.setattr(worker, 'validate_upload_parameters', lambda *args: ('photo', 'owner'))
    worker.app.dependency_overrides[worker.get_upload_authorization] = lambda: {'photo_id': 'photo', 'user_id': 'owner'}
    try:
        data = {'client_signature': 'signature'}
        if version is not None:data['version'] = version
        result = TestClient(worker.app).post('/upload', data=data, files={'file': ('photo.jpg', b'jpeg', 'image/jpeg')})
        assert result.status_code == 200, result.text
        assert upload.await_args.kwargs['upload_auth']['artifact_version'] == (None if version is None else int(version))
    finally:
        worker.app.dependency_overrides.pop(worker.get_upload_authorization, None)
