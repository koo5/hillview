"""Consent and publication history remain independent of moderation gates."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, Request

from common.models import Photo, PhotoLicenseHistory, PhotoOutflowLicenseHistory, User, UserModeration, UserRole
import photo_routes
from admin_routes import PanoramaxContributorRequest, set_panoramax_contributor


@pytest.fixture
def context(monkeypatch):
    monkeypatch.setattr(photo_routes, 'rate_limit_photo_operations', AsyncMock())
    photo = Photo(id='photo', owner_id='owner', legal_rights='full1',
                  panoramax_owner_share=False, panoramax_moderator_approved=True,
                  original_filename='photo.jpg', featured=False, bestof_eligible=True)
    result = Mock()
    result.scalars.return_value.first.return_value = photo
    db = SimpleNamespace(execute=AsyncMock(return_value=result), scalar=AsyncMock(return_value='owner'),
                         add=Mock(), commit=AsyncMock())
    request = Request({'type': 'http', 'client': ('127.0.0.1', 1234), 'headers': []})
    owner = User(id='owner', username='owner', role=UserRole.USER)
    return photo, db, request, owner


@pytest.mark.asyncio
async def test_share_changes_outflow_and_records_only_publication_history(context):
    photo, db, request, owner = context
    result = await photo_routes.edit_photo(request, photo.id,
        photo_routes.PhotoEditRequest(panoramax_share=True), owner, db)
    assert result['license'] == 'panoramax'
    assert result['license_granted'] == 'full1'
    assert result['panoramax_share'] is True
    assert 'panoramax_approved' not in result
    entry, = [call.args[0] for call in db.add.call_args_list]
    assert isinstance(entry, PhotoOutflowLicenseHistory)
    assert (entry.old_license, entry.new_license, entry.cause) == ('arr', 'panoramax', 'panoramax_share')
    assert entry.actor_was_owner
    db.add.reset_mock()
    await photo_routes.edit_photo(request, photo.id,
        photo_routes.PhotoEditRequest(panoramax_share=True), owner, db)
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_grant_change_records_intake_and_outflow(context):
    photo, db, request, owner = context
    await photo_routes.edit_photo(request, photo.id,
        photo_routes.PhotoEditRequest(license='panoramax_in'), owner, db)
    rows = [call.args[0] for call in db.add.call_args_list]
    assert len(rows) == 2
    assert isinstance(rows[0], PhotoLicenseHistory)
    assert (rows[0].old_license, rows[0].new_license) == ('full1', 'panoramax_in')
    assert isinstance(rows[1], PhotoOutflowLicenseHistory)
    assert rows[1].cause == 'grant_change'


@pytest.mark.asyncio
@pytest.mark.parametrize('intake', ['panoramax_in', 'ccbysa4+osm'])
async def test_share_does_not_invent_a_publication_change_for_other_intakes(context, intake):
    photo, db, request, owner = context
    photo.legal_rights = intake
    await photo_routes.edit_photo(request, photo.id,
        photo_routes.PhotoEditRequest(panoramax_share=True), owner, db)
    assert photo.panoramax_owner_share
    db.add.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('role', [UserRole.USER, UserRole.MODERATOR, UserRole.ADMIN])
async def test_only_owner_can_set_consent_even_when_value_is_unchanged(context, role):
    photo, db, request, _ = context
    actor = User(id='other', username='other', role=role)
    with pytest.raises(HTTPException) as exc:
        await photo_routes.edit_photo(request, photo.id,
            photo_routes.PhotoEditRequest(panoramax_share=False), actor, db)
    assert exc.value.status_code == 403
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_owner_cannot_set_approval(context):
    photo, db, request, owner = context
    with pytest.raises(HTTPException) as exc:
        await photo_routes.edit_photo(request, photo.id,
            photo_routes.PhotoEditRequest(title='rejected', panoramax_approved=False), owner, db)
    assert exc.value.status_code == 403
    assert photo.title is None
    assert photo.panoramax_moderator_approved
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_moderator_approval_is_audited_without_changing_licence(context):
    photo, db, request, _ = context
    moderator = User(id='mod', username='mod', role=UserRole.MODERATOR)
    result = await photo_routes.edit_photo(request, photo.id,
        photo_routes.PhotoEditRequest(panoramax_approved=False), moderator, db)
    assert result['license'] == 'arr'
    assert result['panoramax_approved'] is False
    entry = db.add.call_args.args[0]
    assert entry.extra_data['changes'] == {'panoramax_approved': {'old': True, 'new': False}}


@pytest.mark.asyncio
async def test_contributor_change_snapshots_old_and_new_and_is_idempotent():
    target = User(id='owner', username='owner', role=UserRole.USER, panoramax_contributor=True)
    moderator = User(id='mod', username='mod', role=UserRole.MODERATOR)
    db = SimpleNamespace(get=AsyncMock(return_value=target), add=Mock(), commit=AsyncMock(), refresh=AsyncMock())
    payload = PanoramaxContributorRequest(panoramax_contributor=False, reason=' hold ')
    result = await set_panoramax_contributor(target.id, payload, moderator, db)
    assert result['panoramax_contributor'] is False
    entry = db.add.call_args.args[0]
    assert isinstance(entry, UserModeration)
    assert entry.action == 'panoramax_contributor'
    assert (entry.old_panoramax_contributor, entry.new_panoramax_contributor) == (True, False)
    assert entry.reason == 'hold'
    db.add.reset_mock()
    await set_panoramax_contributor(target.id, payload, moderator, db)
    db.add.assert_not_called()
