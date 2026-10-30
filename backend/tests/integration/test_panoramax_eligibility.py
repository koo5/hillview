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
    ({'__json_null__': True}, {}, False),
    ({'deleted': True}, {}, False),
    ({'is_public': False}, {}, False),
    ({'processing_status': 'authorized'}, {}, False),
    ({'geometry': None}, {}, False),
    ({'effective_at': None}, {}, False),
    # Without a capture time effective_at is the upload time: it would be
    # published as the Panoramax datetime and order an upload batch as a walk.
    ({'captured_at': None}, {}, False),
    ({'sizes': None}, {}, False),
    ({}, {'is_active': False}, False),
    ({}, {'is_test': True}, False),
])
def test_federation_eligibility(patch, user_patch, expected):
    photo = dict(id='eligibility-fixture', owner_id='owner', legal_rights='full1',
                 panoramax_owner_share=True, panoramax_moderator_approved=True,
                 detected_objects={'objects': [{'blurred': False, 'confidence': 0.1}]},
                 deleted=False, is_public=True, processing_status='completed',
                 geometry='SRID=4326;POINT(14 50)', captured_at='2026-10-28T12:00:00',
                 effective_at='2026-10-28T12:00:00Z', sizes={})
    user = dict(id='owner', is_active=True, is_test=False, panoramax_contributor=True)
    json_null = patch.get('__json_null__', False)
    photo.update({k: v for k, v in patch.items() if k != '__json_null__'})
    user.update(user_patch)

    def literal(value):
        return "'" + json.dumps(value).replace("'", "''") + "'::json"

    predicate = ELIGIBLE_PHOTO_WHERE.replace(':scope_legal_rights', "ARRAY['full1','panoramax_in']")
    if json_null:
        predicate = predicate.replace('p.detected_objects', "'null'::json")
    query = f"""
        WITH photo_ratings AS (SELECT NULL::text photo_source, NULL::text photo_id, NULL::text rating WHERE false),
             flagged_photos AS (SELECT NULL::text photo_source, NULL::text photo_id, false resolved WHERE false)
        SELECT count(*) FROM json_populate_record(NULL::public.photos, {literal(photo)}) p
        JOIN json_populate_record(NULL::public.users, {literal(user)}) u ON u.id = p.owner_id
        WHERE {predicate};
    """
    default = ['docker', 'exec', '-i', 'hillview_postgres', 'psql',
               '-U', os.getenv('POSTGRES_USER', 'hillview'), '-d', os.getenv('POSTGRES_DB', 'hillview')]
    command = shlex.split(os.environ['PANORAMAX_TEST_PSQL']) if 'PANORAMAX_TEST_PSQL' in os.environ else default
    result = subprocess.run(command + ['-v', 'ON_ERROR_STOP=1', '-tA'], input=query, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ('1' if expected else '0')
