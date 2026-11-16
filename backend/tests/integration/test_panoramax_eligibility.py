"""Exercise the federation's actual PostgreSQL predicate, without inserting photos.

CTEs supply fixture rows while PostgreSQL uses the migrated public table types.
The local Docker PostGIS database is the same one the integration stack uses.
"""
import json
import os
import shlex
import subprocess

import pytest

from panoramax.app.eligibility import ELIGIBLE_PHOTO_WHERE


@pytest.mark.parametrize('patch,user_patch,expected', [
    ({}, {}, True),
    ({'legal_rights': 'panoramax_in'}, {}, True),
    ({'legal_rights': 'ccbysa4+osm'}, {}, False),
    ({'panoramax_owner_share': False}, {}, False),
    ({'panoramax_moderator_approved': False}, {}, False),
    ({}, {'panoramax_contributor': False}, False),
    ({'detected_objects': {'objects': [], 'model_name': 'detector'}}, {}, True),
    ({'detected_objects': {'objects': [{'blurred': False, 'confidence': 0.9}]}}, {}, True),
    ({'detected_objects': {'objects': [{'blurred': True, 'confidence': 0.1}]}}, {}, False),
    ({'detected_objects': {'manual': True, 'objects': []}}, {}, False),
    ({'detected_objects': {'manual': True, 'objects': [{'blurred': True}]}}, {}, False),
    ({'detected_objects': None}, {}, False),
    # Records the gates cannot read fail them instead of raising: a raise
    # would fail every sequencer pass, since the gates run on every photo.
    ({'detected_objects': {'objects': None}}, {}, False),
    ({'detected_objects': {'objects': {}}}, {}, False),
    ({'detected_objects': {'objects': [5]}}, {}, False),
    ({'detected_objects': {'objects': [{'blurred': 'yes'}]}}, {}, False),
    ({'detected_objects': {'manual': 'maybe', 'objects': []}}, {}, False),
    ({'detected_objects': {'manual': False, 'objects': []}}, {}, True),
    ({'detected_objects': {'manual': None}}, {}, True),
    ({'__json_null__': True}, {}, False),
    ({'deleted': True}, {}, False),
    ({'is_public': False}, {}, False),
    ({'processing_status': 'authorized'}, {}, False),
    ({'geometry': None}, {}, False),
    # Positions the grid projection cannot place.
    ({'geometry': 'SRID=4326;POINT(0 91)'}, {}, False),
    ({'geometry': 'SRID=4326;POINT(181 0)'}, {}, False),
    ({'geometry': 'SRID=4326;POINT EMPTY'}, {}, False),
    ({'geometry': 'SRID=4326;POINT(180 -90)'}, {}, True),
    ({'effective_at': None}, {}, False),
    # Without a capture time effective_at is the upload time: it would be
    # published as the Panoramax datetime and order an upload batch as a walk.
    ({'captured_at': None}, {}, False),
    ({'sizes': None}, {}, False),
    # The receiver's own error bar: the selection places one photo per
    # few-metre cell. Unknown passes — nothing before 2026-09-13 carries a radius.
    ({'location_accuracy_m': 5.0}, {}, True),
    ({'location_accuracy_m': 5.1}, {}, False),
    ({'location_accuracy_m': 21.3}, {}, False),
    ({'location_accuracy_m': None}, {}, True),
    # Judged blurry stays out; unjudged (curated wide sources, unmeasured uploads) passes.
    ({'blurry': True}, {}, False),
    ({'blurry': False}, {}, True),
    ({'blurry': None}, {}, True),
    # A bearing is required; NaN would pass IS NOT NULL.
    ({'compass_angle': None}, {}, False),
    ({'compass_angle': 'NaN'}, {}, False),
    ({'compass_angle': 'Infinity'}, {}, False),
    ({'compass_angle': 0.0}, {}, True),
    # Measured level, GPano conventions: |pitch| <= 20, |roll| <= 10.
    # Unmeasured fails, unlike the blur verdict and the location radius.
    ({'pitch': 20.0}, {}, True),
    ({'pitch': -20.0}, {}, True),
    ({'pitch': 20.1}, {}, False),
    ({'pitch': -20.1}, {}, False),
    ({'pitch': None}, {}, False),
    ({'pitch': 'NaN'}, {}, False),
    ({'roll': 10.0}, {}, True),
    ({'roll': -10.0}, {}, True),
    ({'roll': 10.1}, {}, False),
    ({'roll': -10.1}, {}, False),
    ({'roll': None}, {}, False),
    # Car mode is exempt from both, measured or not, but still needs a bearing.
    ({'bearing_source': 'gps-kalman', 'pitch': None, 'roll': None}, {}, True),
    ({'bearing_source': 'gps-kalman', 'pitch': -45.0, 'roll': 30.0}, {}, True),
    ({'bearing_source': 'gps-kalman', 'compass_angle': None}, {}, False),
    ({'bearing_source': 'map', 'pitch': None}, {}, False),
    # Without a source, a measured level photo passes and an unmeasured one fails.
    ({'bearing_source': None}, {}, True),
    ({'bearing_source': None, 'pitch': None}, {}, False),
    # An analysis listing no signage is required: "no signage" is only a
    # finding once the analyzer has looked, so unanalyzed stays out. A
    # document the gates cannot read fails them instead of raising.
    ({'analysis': {'features': []}}, {}, True),
    ({'analysis': {'features': ['street', 'building']}}, {}, True),
    ({'analysis': {'features': ['signage']}}, {}, False),
    ({'analysis': {'features': ['street', 'signage', 'building']}}, {}, False),
    ({'analysis': None}, {}, False),
    ({'__analysis_json_null__': True}, {}, False),
    ({'analysis': {}}, {}, False),
    ({'analysis': {'features': None}}, {}, False),
    ({'analysis': {'features': 'signage'}}, {}, False),
    ({'analysis': {'features': {'signage': False}}}, {}, False),
    ({}, {'is_active': False}, False),
    # Test users are federated like anyone: the automated suites rely on it.
    ({}, {'is_test': True}, True),
])
def test_federation_eligibility(patch, user_patch, expected):
    photo = dict(id='eligibility-fixture', owner_id='owner', legal_rights='full1',
                 panoramax_owner_share=True, panoramax_moderator_approved=True,
                 detected_objects={'objects': [{'blurred': False, 'confidence': 0.1}]},
                 deleted=False, is_public=True, processing_status='completed',
                 geometry='SRID=4326;POINT(14 50)', captured_at='2026-10-28T12:00:00',
                 effective_at='2026-10-28T12:00:00Z', sizes={},
                 analysis={'features': ['landscape', 'hill']},
                 compass_angle=90.0, pitch=-4.0, roll=1.5, bearing_source='android-compass-true')
    user = dict(id='owner', is_active=True, is_test=False, panoramax_contributor=True)
    json_null = patch.get('__json_null__', False)
    analysis_json_null = patch.get('__analysis_json_null__', False)
    photo.update({k: v for k, v in patch.items() if not k.startswith('__')})
    user.update(user_patch)

    def literal(value):
        return "'" + json.dumps(value).replace("'", "''") + "'::json"

    predicate = ELIGIBLE_PHOTO_WHERE.replace(':scope_legal_rights', "ARRAY['full1','panoramax_in']")
    if json_null:
        predicate = predicate.replace('p.detected_objects', "'null'::json")
    if analysis_json_null:
        predicate = predicate.replace('p.analysis', "'null'::jsonb")
    query = f"""
        WITH photo_ratings AS (SELECT NULL::text photo_source, NULL::text photo_id, NULL::text rating WHERE false),
             flagged_photos AS (SELECT NULL::text photo_source, NULL::text photo_id, false resolved WHERE false)
        SELECT count(*) FROM json_populate_record(NULL::public.photos, {literal(photo)}) p
        JOIN json_populate_record(NULL::public.users, {literal(user)}) u ON u.id = p.owner_id
        WHERE {predicate};
    """
    assert psql(query) == ('1' if expected else '0')


@pytest.mark.parametrize('user_comment,expected', [
    ('{"location_accuracy_m": 21.3}', '21.3'),
    ('{"location_accuracy_m": "4.5"}', '4.5'),
    # The capture table's "unknown" sentinel, never a real radius.
    ('{"location_accuracy_m": 0}', ''),
    ('{"location_accuracy_m": -1}', ''),
    ('{"location_accuracy_m": "NaN"}', ''),
    ('{"location_accuracy_m": "Infinity"}', ''),
    ('{"location_accuracy_m": "far"}', ''),
    ('{"location_accuracy_m": null}', ''),
    ('{"attitude": {}}', ''),
    # Another camera's free text, and text that only looks like JSON: a cast
    # that raised here would fail every query reading the column.
    ('Canon EOS 5DS R', ''),
    ('{not json', ''),
    # A NUL-padded comment: exiftool's JSON escapes NUL as \u0000, which a
    # json value keeps and ->> cannot turn into text.
    ('Canon\u0000\u0000', ''),
    (None, ''),
])
def test_location_accuracy_column(user_comment, expected):
    exif = {'data': {'UserComment': user_comment}} if user_comment is not None else {'data': {}}
    literal = "'" + json.dumps(exif).replace("'", "''") + "'::json"
    assert psql(f'SELECT photo_location_accuracy_m({literal});') == expected


@pytest.mark.parametrize('user_comment,expected', [
    ('{"bearing_source": "gps-kalman"}', 'gps-kalman'),
    ('{"bearing_source": "android-compass-true", "location_accuracy_m": 3.2}', 'android-compass-true'),
    # Capped: the longest real label is 73 characters.
    ('{"bearing_source": "' + 'x' * 200 + '"}', 'x' * 128),
    ('{"bearing_source": 5}', ''),
    ('{"bearing_source": null}', ''),
    ('{"bearing_source": {"kind": "gps-kalman"}}', ''),
    ('{"bearing_source": "a\\u0000b"}', ''),
    ('{}', ''),
    ('"gps-kalman"', ''),
    ('Canon EOS 5DS R', ''),
    ('{not json', ''),
    ('Canon\u0000\u0000', ''),
    (None, ''),
])
def test_bearing_source_column(user_comment, expected):
    exif = {'data': {'UserComment': user_comment}} if user_comment is not None else {'data': {}}
    literal = "'" + json.dumps(exif).replace("'", "''") + "'::json"
    assert psql(f'SELECT photo_bearing_source({literal});') == expected


def psql(query):
    default = ['docker', 'exec', '-i', 'hillview_postgres', 'psql',
               '-U', os.getenv('POSTGRES_USER', 'hillview'), '-d', os.getenv('POSTGRES_DB', 'hillview')]
    command = shlex.split(os.environ['PANORAMAX_TEST_PSQL']) if 'PANORAMAX_TEST_PSQL' in os.environ else default
    result = subprocess.run(command + ['-v', 'ON_ERROR_STOP=1', '-tA'], input=query, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()
