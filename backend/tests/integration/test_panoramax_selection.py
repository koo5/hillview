"""Real PostGIS cells and collector/API membership transitions on the dev stack."""
from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import uuid

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'panoramax' / 'app'))
from selection import CANDIDATES_SQL, Candidate, select_photos


def pg(query):
    default = ['docker', 'exec', '-i', 'hillview_postgres', 'psql',
               '-U', os.getenv('POSTGRES_USER', 'hillview'), '-d', os.getenv('POSTGRES_DB', 'hillview')]
    command = shlex.split(os.environ['PANORAMAX_TEST_PSQL']) if 'PANORAMAX_TEST_PSQL' in os.environ else default
    result = subprocess.run(command + ['-v', 'ON_ERROR_STOP=1', '-tA'], input=query, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def geometry(x=500002, y=5500002, srid=32610):
    return pg(f'SELECT ST_AsEWKT(ST_Transform(ST_SetSRID(ST_MakePoint({x}, {y}), {srid}), 4326));')


def photo(id, geom, **patch):
    row = dict(id=id, owner_id='owner', legal_rights='full1',
        panoramax_owner_share=True, panoramax_moderator_approved=True,
        detected_objects={'objects': []}, deleted=False, is_public=True,
        processing_status='completed', geometry=geom, compass_angle=0,
        captured_at='2024-06-21T19:00:00', effective_at='2024-06-21T19:00:00', sizes={})
    row.update(patch)
    return row


def candidates(rows):
    owners = [dict(id=id, is_active=True, is_test=False, panoramax_contributor=True)
              for id in sorted({row['owner_id'] for row in rows})]
    query = CANDIDATES_SQL.replace(':scope_legal_rights', "ARRAY['full1','panoramax_in']")
    result = pg(f"""
        WITH photos AS (SELECT * FROM json_populate_recordset(NULL::public.photos, {literal(json.dumps(rows))}::json)),
             users AS (SELECT * FROM json_populate_recordset(NULL::public.users, {literal(json.dumps(owners))}::json)),
             photo_ratings AS (SELECT NULL::text photo_source, NULL::text photo_id, NULL::text rating WHERE false),
             flagged_photos AS (SELECT NULL::text photo_source, NULL::text photo_id, false resolved WHERE false)
        SELECT row_to_json(candidate) FROM ({query}) candidate;
    """)
    out = []
    for line in result.splitlines():
        row = json.loads(line)
        for key in ('effective_at', 'captured_at'):
            if row[key] is not None:
                row[key] = datetime.fromisoformat(row[key])
        out.append(Candidate(**row))
    return out


def test_five_metre_cells_and_sectors_are_independent():
    rows = [photo('a', geometry()), photo('same', geometry(500004.9), owner_id='other'),
            photo('next-x', geometry(500005.1)), photo('next-y', geometry(y=5500005.1)),
            photo('east', geometry(), compass_angle=90), photo('unknown', geometry(), compass_angle=None)]
    result = candidates(rows)
    by_id = {p.id: p for p in result}
    assert (by_id['a'].grid_srid, by_id['a'].grid_x, by_id['a'].grid_y) == (32610, 100000, 1100000)
    assert by_id['same'].grid_x == by_id['a'].grid_x
    assert by_id['next-x'].grid_x == by_id['a'].grid_x + 1
    assert by_id['next-y'].grid_y == by_id['a'].grid_y + 1
    assert {p.id for p in select_photos(result)} == {'a', 'next-x', 'next-y', 'east', 'unknown'}


@pytest.mark.parametrize('longitude,latitude,srid', [
    (14, 50, 32633), (18, -34, 32734), (0, 85, 32661), (0, -85, 32761),
    (-180, 0, 32601), (180, 0, 32601), (0, 90, 32661), (0, -90, 32761),
])
def test_global_projection_coverage(longitude, latitude, srid):
    selected, = candidates([photo('p', f'SRID=4326;POINT({longitude} {latitude})')])
    assert selected.grid_srid == srid


def test_date_line_and_poles_have_canonical_cell_keys():
    for coords in [[(-180, 0), (180, 0)], [(0, 90), (120, 90)], [(0, -90), (-90, -90)]]:
        rows = [photo(str(i), f'SRID=4326;POINT({lon} {lat})') for i, (lon, lat) in enumerate(coords)]
        assert len(select_photos(candidates(rows))) == 1


def test_projection_zones_do_not_share_cell_addresses():
    result = candidates([photo('west', 'SRID=4326;POINT(5.99999 50)'),
                         photo('east', 'SRID=4326;POINT(6.00001 50)')])
    assert {p.grid_srid for p in result} == {32631, 32632}
    assert len(select_photos(result)) == 2


@pytest.mark.parametrize('geom', ['SRID=4326;POINT(0 91)', 'SRID=4326;POINT(181 0)', 'SRID=4326;POINT EMPTY'])
def test_invalid_or_empty_coordinates_cannot_abort_projection(geom):
    assert candidates([photo('bad', geom)]) == []


def run_collector():
    # Use the service's configured role in its intended runtime; never extract
    # credentials or import the API's ORM into the raw-SQL collector.
    code = """
import asyncio,json,os
os.environ['PANORAMAX_BEARING_BUCKETS']='8'
from db import get_engine
from sequencer import run_once
async def main():
    engine=get_engine()
    try: print(json.dumps(await run_once(engine)))
    finally: await engine.dispose()
asyncio.run(main())
"""
    result = subprocess.run(['docker', 'exec', '-i', 'hillview_panoramax', 'python', '-'],
        input=code, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_collector_replaces_winners_and_api_serves_only_selected_eligible_photos():
    owners = [str(uuid.uuid4()), str(uuid.uuid4())]
    names = ['old-day', 'new-day', 'night', 'east', 'next-cell', 'unknown', 'unshared', 'doodled']
    ids = {name: str(uuid.uuid4()) for name in names}
    owner_sql = ','.join(literal(id) for id in owners)
    id_sql = ','.join(literal(id) for id in ids.values())
    sizes = json.dumps({'full': {'url': 'https://example.invalid/selection.jpg', 'width': 160, 'height': 120}})
    url = os.getenv('PANORAMAX_URL', 'http://localhost:8058')

    def membership():
        rows = pg(f"SELECT photo_id || '|' || sequence_id::text FROM panoramax.sequence_photos WHERE photo_id IN ({id_sql});")
        return dict(line.split('|') for line in rows.splitlines())

    def served(mapping):
        found = set()
        for seq in set(mapping.values()):
            response = requests.get(f'{url}/api/collections/{seq}/items', timeout=10)
            assert response.status_code == 200, response.text
            found.update(p['id'] for p in response.json()['features'] if p['id'] in ids.values())
        return found

    try:
        for owner in owners:
            pg(f"""INSERT INTO users (id,username,email,is_active,is_test,is_verified,role,auto_upload_enabled,panoramax_contributor)
                VALUES ({literal(owner)}, {literal('pano_grid_'+owner)}, {literal(owner+'@example.invalid')}, true,false,true,'USER',false,true);""")
        for name, owner, at, bearing, x in [
            ('old-day', owners[0], '2024-06-21 19:00', '0', 500002),
            ('new-day', owners[1], '2025-06-21 19:00', '0', 500002),
            ('night', owners[0], '2026-06-21 07:00', '0', 500002),
            ('east', owners[0], '2024-06-21 19:00', '90', 500002),
            ('next-cell', owners[0], '2024-06-21 19:00', '0', 500007),
            ('unknown', owners[1], '2024-06-21 19:00', 'NULL', 500002),
            ('unshared', owners[0], '2027-06-21 19:00', '0', 500002),
            ('doodled', owners[0], '2028-06-21 19:00', '0', 500002),
        ]:
            detections = {'objects': [{'blurred': True}]} if name == 'doodled' else {'objects': []}
            pg(f"""INSERT INTO photos (id,owner_id,filename,original_filename,geometry,compass_angle,captured_at,
                    uploaded_at,record_created_ts,width,height,is_public,processing_status,sizes,detected_objects,
                    legal_rights,featured,deleted,version,panoramax_owner_share,panoramax_moderator_approved)
                VALUES ({literal(ids[name])},{literal(owner)},'selection.jpg','selection.jpg',
                    ST_Transform(ST_SetSRID(ST_MakePoint({x},5500002),32610),4326),{bearing},{literal(at)},
                    now(),now(),160,120,true,'completed',{literal(sizes)}::json,{literal(json.dumps(detections))}::json,
                    'full1',false,false,1,{'false' if name == 'unshared' else 'true'},true);""")
        run_collector()
        initial = membership()
        expected = {ids[n] for n in ('new-day', 'east', 'next-cell', 'unknown')}
        assert set(initial) == served(initial) == expected
        repeated = run_collector()
        assert all(repeated[key] == 0 for key in ('sequences_created', 'memberships_inserted', 'memberships_updated', 'memberships_deleted'))
        assert membership() == initial

        pg(f"UPDATE photos SET panoramax_owner_share=false WHERE id={literal(ids['new-day'])};")
        assert ids['new-day'] not in served(initial)  # immediate eligibility filter
        run_collector()
        assert set(membership()) == served(membership()) == expected - {ids['new-day']} | {ids['old-day']}
        pg(f"UPDATE photos SET panoramax_owner_share=false WHERE id={literal(ids['old-day'])};")
        run_collector()
        assert ids['night'] in membership()  # no daytime candidate: night still qualifies

        pg(f"UPDATE photos SET panoramax_owner_share=true WHERE id={literal(ids['new-day'])};")
        run_collector()
        assert membership()[ids['new-day']] == initial[ids['new-day']]  # revive the original sequence
        pg(f"UPDATE photos SET captured_at='2029-06-21 19:00' WHERE id={literal(ids['night'])};")
        run_collector()
        assert ids['night'] in membership() and ids['new-day'] not in membership()
        pg(f"UPDATE photos SET compass_angle=45 WHERE id={literal(ids['night'])};")
        run_collector()
        assert {ids['night'], ids['new-day']} <= set(membership())
        pg(f"UPDATE users SET panoramax_contributor=false WHERE id={literal(owners[0])};")
        run_collector()
        assert set(membership()) == served(membership()) == {ids['new-day'], ids['unknown']}
    finally:
        pg(f"BEGIN; DELETE FROM photos WHERE id IN ({id_sql}); "
           f"DELETE FROM panoramax.sequences WHERE owner_id IN ({owner_sql}); "
           f"DELETE FROM users WHERE id IN ({owner_sql}); COMMIT;")
