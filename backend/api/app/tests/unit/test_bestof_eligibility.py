"""Best of eligibility is a reversible, moderator-only curation setting."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from fastapi import HTTPException, Request
from sqlalchemy import create_engine, literal, literal_column, select, text

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR.parents[1]))

from common.models import Photo, PhotoModerationAudit, UserRole
from bestof_routes import ranked
import photo_routes


@pytest.fixture
def edit_context(monkeypatch):
	monkeypatch.setattr(photo_routes, 'rate_limit_photo_operations', AsyncMock())
	photo = Photo(
		id='photo', owner_id='owner', original_filename='pano.jpg', title='Panorama',
		description='Description', compass_angle=90, legal_rights='full1',
		featured=True, bestof_eligible=True, deleted=False,
	)
	result = Mock()
	result.scalars.return_value.first.return_value = photo
	db = SimpleNamespace(execute=AsyncMock(return_value=result), scalar=AsyncMock(return_value='owner'),
		add=Mock(), commit=AsyncMock())
	request = Request({'type': 'http', 'client': ('127.0.0.1', 1234), 'headers': []})
	return photo, db, request


def user(role, id_='curator'):
	return SimpleNamespace(id=id_, username=id_, role=role)


@pytest.mark.asyncio
@pytest.mark.parametrize('role', [UserRole.ADMIN, UserRole.MODERATOR])
async def test_curators_can_exclude_and_restore_without_a_reason(edit_context, role):
	photo, db, request = edit_context
	actor = user(role)
	for eligible in (False, True):
		result = await photo_routes.edit_photo(request, photo.id,
			photo_routes.PhotoEditRequest(bestof_eligible=eligible), actor, db)
		assert result['bestof_eligible'] is eligible
		assert result['changed'] == ['bestof_eligible']
		assert photo.bestof_eligible is eligible
		assert photo.featured is True
		assert photo.deleted is False
		assert photo.title == 'Panorama'
		entry = db.add.call_args.args[0]
		assert isinstance(entry, PhotoModerationAudit)
		assert entry.action == 'edit'
		assert entry.reason is None
		assert entry.extra_data['changes'] == {'bestof_eligible': {'old': not eligible, 'new': eligible}}
	assert db.commit.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('eligible', [False, True])
async def test_owner_cannot_change_eligibility_and_request_is_atomic(edit_context, eligible):
	photo, db, request = edit_context
	photo.bestof_eligible = not eligible
	with pytest.raises(HTTPException) as exc:
		await photo_routes.edit_photo(request, photo.id,
			photo_routes.PhotoEditRequest(title='Should not stick', bestof_eligible=eligible),
			user(UserRole.USER, 'owner'), db)
	assert exc.value.status_code == 403
	assert photo.bestof_eligible is not eligible
	assert photo.title == 'Panorama'
	db.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('eligible', [False, True])
async def test_owner_can_save_metadata_without_changing_eligibility(edit_context, eligible):
	photo, db, request = edit_context
	photo.bestof_eligible = eligible
	result = await photo_routes.edit_photo(request, photo.id,
		photo_routes.PhotoEditRequest(title='New title', bestof_eligible=eligible),
		user(UserRole.USER, 'owner'), db)
	assert result['changed'] == ['title']
	assert result['bestof_eligible'] is eligible
	db.add.assert_not_called()


@pytest.mark.asyncio
async def test_other_regular_users_cannot_change_eligibility(edit_context):
	photo, db, request = edit_context
	with pytest.raises(HTTPException) as exc:
		await photo_routes.edit_photo(request, photo.id,
			photo_routes.PhotoEditRequest(bestof_eligible=False), user(UserRole.USER), db)
	assert exc.value.status_code == 404
	assert photo.bestof_eligible is True
	db.commit.assert_not_awaited()


def test_shared_ranking_excludes_before_pagination_and_can_restore():
	engine = create_engine('sqlite://')
	with engine.begin() as db:
		db.execute(text('CREATE TABLE photos (id TEXT, deleted BOOLEAN, bestof_eligible BOOLEAN, score INTEGER)'))
		db.execute(text("INSERT INTO photos VALUES ('excluded', 0, 0, 100), ('replacement', 0, 1, 20), "
			"('another', 0, 1, 10), ('deleted', 1, 1, 1000), ('zero', 0, 1, 0)"))
		# Both the listing and /lastmod use this helper. These score inputs are
		# deliberately independent of eligibility; exclusion must override score.
		thumbs = select(literal(None).label('photo_id')).subquery('thumbs')
		annotations = select(literal(None).label('photo_id')).subquery('annotations')
		score = literal_column('photos.score')
		query = ranked(select(Photo.id), thumbs, annotations, score)
		assert list(db.execute(query.limit(2)).scalars()) == ['replacement', 'another']
		assert list(db.execute(query.offset(1).limit(1)).scalars()) == ['another']
		db.execute(text("UPDATE photos SET bestof_eligible = 1 WHERE id = 'excluded'"))
		assert list(db.execute(query.limit(2)).scalars()) == ['excluded', 'replacement']
	engine.dispose()


def test_migration_keeps_existing_and_new_photos_eligible_by_default():
	scripts = ScriptDirectory(str(APP_DIR / 'alembic'))
	assert len(scripts.get_heads()) == 1
	assert scripts.get_revision('037_photo_bestof_eligible') is not None
	path = APP_DIR / 'alembic/versions/037_photo_bestof_eligible.py'
	spec = importlib.util.spec_from_file_location('bestof_eligibility_migration', path)
	migration = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(migration)
	engine = create_engine('sqlite://')
	with engine.begin() as db:
		db.execute(text('CREATE TABLE photos (id TEXT)'))
		db.execute(text("INSERT INTO photos VALUES ('existing')"))
		with Operations.context(MigrationContext.configure(db)):
			migration.upgrade()
			db.execute(text("INSERT INTO photos (id) VALUES ('new')"))
			assert list(db.execute(text('SELECT bestof_eligible FROM photos')).scalars()) == [1, 1]
			migration.downgrade()
			assert list(db.execute(text('SELECT id FROM photos')).scalars()) == ['existing', 'new']
	engine.dispose()
