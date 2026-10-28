"""Execute shared filter expressions against small rows, without a service DB.

SQLite supports the JSON ->> operator used by these PostgreSQL expressions;
only the predicate columns are selected, avoiding unrelated PostGIS columns.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from common.models import Photo
from photo_filters import PhotoFilters, apply_photo_filters, build_filter_expressions, parse_photo_filters


@pytest.fixture
def photos():
	engine = create_engine('sqlite://')
	with engine.begin() as db:
		db.execute(text('CREATE TABLE photos (id TEXT, width INTEGER, analysis TEXT, featured BOOLEAN)'))
		rows = [
			('narrow', 1999, {'time_of_day': 'day'}, False),
			('boundary', 2000, {'time_of_day': 'day'}, False),
			('wide_night', 4000, {'time_of_day': 'night'}, False),
			('wide_unanalyzed', 4000, None, False),
			('narrow_unanalyzed', 1000, None, False),
			('unknown_width', None, {'time_of_day': 'day'}, False),
			('missing_analysis_field', 4000, {}, False),
			('featured_narrow', 1000, {'time_of_day': 'day'}, True),
			('featured_wide', 4000, {'time_of_day': 'day'}, True),
		]
		db.execute(text('INSERT INTO photos VALUES (:id, :width, :analysis, :featured)'), [
			{'id': id_, 'width': width, 'analysis': json.dumps(analysis) if analysis is not None else None, 'featured': featured}
			for id_, width, analysis, featured in rows
		])
		yield db
	engine.dispose()


def matches(db, filters):
	flag, priority = build_filter_expressions(filters)
	map_rows = db.execute(select(Photo.id, flag, priority)).all()
	map_matches = {id_ for id_, filtered, _ in map_rows if not filtered}
	timeline_matches = set(db.execute(apply_photo_filters(select(Photo.id), filters)).scalars())
	assert map_matches == timeline_matches
	return map_matches, {id_: rank for id_, _, rank in map_rows}


@pytest.mark.parametrize('show_unanalyzed', [True, False])
def test_width_only_ignores_analysis_status_and_checks_inclusive_boundary(photos, show_unanalyzed):
	filters = PhotoFilters.model_validate({
		'analysis': {'show_unanalyzed': show_unanalyzed}, 'properties': {'min_width': 2000},
	})
	matching, ranks = matches(photos, filters)
	assert matching == {'boundary', 'wide_night', 'wide_unanalyzed', 'missing_analysis_field', 'featured_wide'}
	assert ranks['wide_unanalyzed'] == ranks['boundary'] == 1
	assert ranks['featured_narrow'] == ranks['unknown_width'] == 3
	assert ranks['featured_wide'] == 0


@pytest.mark.parametrize('show_unanalyzed', [True, False])
def test_analysis_and_width_are_anded_without_unanalyzed_bypass(photos, show_unanalyzed):
	filters = PhotoFilters.model_validate({
		'analysis': {'time_of_day': 'day', 'show_unanalyzed': show_unanalyzed},
		'properties': {'min_width': 2000},
	})
	matching, ranks = matches(photos, filters)
	assert matching == {'boundary', 'featured_wide'} | ({'wide_unanalyzed'} if show_unanalyzed else set())
	assert ranks['narrow_unanalyzed'] == ranks['featured_narrow'] == 3
	flag, priority = build_filter_expressions(filters)
	limited = photos.execute(select(Photo.id).order_by(priority, Photo.id).limit(2)).scalars().all()
	assert limited == ['featured_wide', 'boundary']


def test_analysis_only_keeps_existing_unanalyzed_behavior(photos):
	filters = PhotoFilters.model_validate({'analysis': {'time_of_day': 'day'}})
	matching, _ = matches(photos, filters)
	assert matching == {'narrow', 'boundary', 'unknown_width', 'featured_narrow', 'featured_wide', 'wide_unanalyzed', 'narrow_unanalyzed'}


def test_empty_filters_have_no_predicate(photos):
	filters = PhotoFilters()
	assert build_filter_expressions(filters) == (None, None)
	query = select(Photo.id)
	assert apply_photo_filters(query, filters) is query


def test_parse_new_envelope_and_legacy_clients():
	assert parse_photo_filters(None, None) is None
	assert parse_photo_filters('null', 'null') is None
	assert parse_photo_filters('{"properties":{"min_width":3000}}', None).properties.min_width == 3000
	legacy = parse_photo_filters(None, '{"time_of_day":"night","show_unanalyzed":false}')
	assert legacy.analysis.time_of_day == 'night'
	assert legacy.analysis.show_unanalyzed is False
	assert legacy.properties.min_width is None


@pytest.mark.parametrize('width', [-1, 0, 1.5, True, '2000'])
def test_invalid_width_is_rejected(width):
	with pytest.raises(HTTPException) as exc:
		parse_photo_filters(json.dumps({'properties': {'min_width': width}}), None)
	assert exc.value.status_code == 400


def test_invalid_json_is_rejected():
	with pytest.raises(HTTPException) as exc:
		parse_photo_filters('{', None)
	assert exc.value.status_code == 400
