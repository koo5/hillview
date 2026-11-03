"""A collection's `updated` is when its change became visible: commit time.

The harvester's incremental crawl asks for `updated > <its previous harvest's
start, less 3 s>`. A change stamped with its transaction's start (now()) but
committed seconds later is invisible to a harvest that lists collections
meanwhile, and already too old for the next one's filter, so it would never be
fetched. Here a sequence is stamped, committed 3 s later, and the listing is
asked for collections updated after a moment inside that wait.
"""
import os
import shlex
import subprocess
import threading
import time
import uuid

import requests

PANORAMAX_URL = os.getenv('PANORAMAX_URL', 'http://localhost:8058')


def pg(query):
    default = ['docker', 'exec', '-i', 'hillview_postgres', 'psql',
               '-U', os.getenv('POSTGRES_USER', 'hillview'), '-d', os.getenv('POSTGRES_DB', 'hillview')]
    command = shlex.split(os.environ['PANORAMAX_TEST_PSQL']) if 'PANORAMAX_TEST_PSQL' in os.environ else default
    result = subprocess.run(command + ['-v', 'ON_ERROR_STOP=1', '-tA'], input=query, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_a_change_committed_late_is_listed_after_a_harvest_that_started_before_the_commit():
    seq = str(uuid.uuid4())
    pg(f"INSERT INTO panoramax.sequences (id, scope, status) VALUES ('{seq}', 'p1', 'ready');")
    try:
        slow = threading.Thread(target=pg, args=(f"""
            BEGIN;
            UPDATE panoramax.sequences SET updated_at = now() WHERE id = '{seq}';
            SELECT pg_sleep(3);
            COMMIT;
        """,))
        slow.start()
        time.sleep(1.5)
        # A harvest starting now, by the database's clock, as the harvester formats it.
        inside = pg("""SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"');""")
        slow.join()

        # The stamp predates that harvest: filtering on it would lose the change.
        assert pg(f"SELECT updated_at < '{inside}' FROM panoramax.sequences WHERE id = '{seq}';") == 't'

        response = requests.get(f'{PANORAMAX_URL}/api/collections', timeout=10, params={
            'filter': f"status IN ('deleted','ready') AND updated > '{inside}'", 'limit': 1000})
        assert response.status_code == 200, response.text
        assert seq in {c['id'] for c in response.json()['collections']}

        served = requests.get(f'{PANORAMAX_URL}/api/collections/{seq}', timeout=10)
        assert served.status_code == 200, served.text
        assert served.json()['updated'] > inside.replace('Z', '+00:00')
    finally:
        pg(f"DELETE FROM panoramax.sequences WHERE id = '{seq}';")


def test_health_requires_commit_timestamps():
    assert pg('SHOW track_commit_timestamp;') == 'on'
    response = requests.get(f'{PANORAMAX_URL}/api/health', timeout=10)
    assert response.status_code == 200, response.text


def test_only_served_fields_bump_the_sequence():
    # Items serve no title or description, so editing them must not make the
    # harvester re-fetch the collection; a bearing edit, which they serve, must.
    # Its own scope and sharing off keep the stack's running sequencer away:
    # the photo is no candidate, and the pass reads only its scope's members.
    owner, photo, seq = (str(uuid.uuid4()) for _ in range(3))
    pg(f"""
        INSERT INTO users (id,username,email,is_active,is_test,is_verified,role,auto_upload_enabled,panoramax_contributor)
        VALUES ('{owner}','pano_bump_{owner}','{owner}@example.invalid',true,false,true,'USER',false,true);
        INSERT INTO photos (id,owner_id,filename,original_filename,geometry,compass_angle,captured_at,
            uploaded_at,record_created_ts,width,height,is_public,processing_status,sizes,detected_objects,
            legal_rights,featured,deleted,version,panoramax_owner_share,panoramax_moderator_approved)
        VALUES ('{photo}','{owner}','bump.jpg','bump.jpg',ST_SetSRID(ST_MakePoint(14.5,50.1),4326),0,
            '2024-06-21 10:00',now(),now(),160,120,true,'completed','{{}}'::json,'{{"objects": []}}'::json,
            'full1',false,false,1,false,true);
        INSERT INTO panoramax.sequences (id, scope, status, owner_id) VALUES ('{seq}', 'bump-test', 'ready', '{owner}');
        INSERT INTO panoramax.sequence_photos (photo_id, sequence_id, rank) VALUES ('{photo}', '{seq}', 1);
    """)
    stamp = lambda: pg(f"SELECT updated_at FROM panoramax.sequences WHERE id = '{seq}';")
    try:
        before = stamp()
        pg(f"UPDATE photos SET title = 'Retitled', description = 'Described' WHERE id = '{photo}';")
        assert stamp() == before
        pg(f"UPDATE photos SET compass_angle = 90 WHERE id = '{photo}';")
        assert stamp() > before
    finally:
        pg(f"BEGIN; DELETE FROM photos WHERE id = '{photo}'; DELETE FROM panoramax.sequences WHERE id = '{seq}'; "
           f"DELETE FROM users WHERE id = '{owner}'; COMMIT;")
