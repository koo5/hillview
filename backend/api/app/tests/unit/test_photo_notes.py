"""Unit tests for photo notes plumbing."""
from types import SimpleNamespace
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from hillview_routes import convert_photo_to_response
from user_routes import UploadAuthorizationRequest


class TestPhotoNotes:
    def test_upload_authorization_request_accepts_notes(self):
        request = UploadAuthorizationRequest(
            filename='test.jpg',
            file_size=123,
            content_type='image/jpeg',
            file_md5='abc123',
            client_key_id='key-1',
            description='body',
            notes='place note',
        )

        assert request.notes == 'place note'

    def test_convert_photo_to_response_includes_notes(self):
        photo = SimpleNamespace(
            id='photo-1',
            compass_angle=123,
            altitude=456,
            captured_at=None,
            original_filename='test.jpg',
            sizes={},
            owner_id='user-1',
            file_md5=None,
            featured=False,
            title=None,
            description='body',
            notes='place note',
            keywords=None,
            legal_rights=None,
        )

        response = convert_photo_to_response(photo, 'alice', 14.4, 50.1)

        assert response['notes'] == 'place note'

    def test_convert_photo_to_response_omits_empty_notes(self):
        photo = SimpleNamespace(
            id='photo-1',
            compass_angle=123,
            altitude=456,
            captured_at=None,
            original_filename='test.jpg',
            sizes={},
            owner_id='user-1',
            file_md5=None,
            featured=False,
            title=None,
            description='body',
            notes='',
            keywords=None,
            legal_rights=None,
        )

        response = convert_photo_to_response(photo, 'alice', 14.4, 50.1)

        assert 'notes' not in response
