"""One federation E2E suite, using either a local or SSH collector transport.

Run from backend/ with `uv run --package hillview-tests python
panoramax/scripts/e2e_federation.py --help`, or use e2e_federation.sh to prepare
the stack. The collector needs its harvester CLI and database running.
This script creates its own account,
uploads real images, and removes its fixtures afterward. It never clears the
catalog, recreates shared test users, or stops either stack.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
import time
import uuid

BACKEND = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(BACKEND / 'tests'), str(BACKEND)]

import httpx
from utils.image_utils import create_test_image_full_gps
from utils.secure_upload_utils import SecureUploadClient, tls_verify


def command(args, **kwargs):
	try:
		return subprocess.run(args, check=True, capture_output=True, text=True, timeout=300, **kwargs).stdout
	except subprocess.CalledProcessError as e:
		print(e.stderr, file=sys.stderr, flush=True)
		raise


REMOTE_QUERY = """
import json, sys, psycopg
from psycopg.rows import dict_row
request = json.load(sys.stdin)
with psycopg.connect(sys.argv[1], row_factory=dict_row) as conn:
    rows = conn.execute(request['sql'], request['params']).fetchall()
print(json.dumps(rows, default=str))
"""


class Catalog:
	def __init__(self, args):
		self.args = args
		self.python = str(Path(args.harvester).with_name('python'))

	def remote(self, args, **kwargs):
		env = ['env']
		if self.args.ca_bundle:
			env += [f'SSL_CERT_FILE={self.args.ca_bundle}', f'REQUESTS_CA_BUNDLE={self.args.ca_bundle}']
		if self.args.catalog_ssh:
			return command(['ssh', '-o', 'BatchMode=yes', self.args.catalog_ssh, shlex.join(env + args)], **kwargs)
		return command(env + args, **kwargs)

	def query(self, sql, *params):
		return json.loads(self.remote([self.python, '-c', REMOTE_QUERY, self.args.catalog_db],
			input=json.dumps({'sql': sql, 'params': params})))

	def cli(self, *args):
		try:
			return self.remote([self.args.harvester, *args, '--db', self.args.catalog_db])
		except subprocess.CalledProcessError as e:
			print(e.stdout, e.stderr, file=sys.stderr)
			raise

	def register(self):
		rows = self.query('SELECT id,url FROM instances WHERE name=%s', self.args.instance_name)
		if rows:
			assert rows[0]['url'].rstrip('/') == self.args.panoramax_url.rstrip('/'), 'Existing instance has a different URL'
		else:
			self.cli('add-instance', self.args.instance_name, '--url', self.args.panoramax_url)
			rows = self.query('SELECT id,url FROM instances WHERE name=%s', self.args.instance_name)
		assert len(rows) == 1, 'Instance registration failed'
		self.instance_id = rows[0]['id']
		print('Registered instance:', self.args.instance_name, rows[0]['url'], flush=True)

	def harvest(self, full=False):
		start = time.monotonic()
		self.cli('harvest', self.args.instance_name, '--full-harvest' if full else '--incremental-harvest')
		rows = self.query('''SELECT h.finished_at,h.error,
			(SELECT count(*) FROM harvest_errors e WHERE e.harvest_id=h.id) AS errors
			FROM harvests h WHERE h.instance_id=%s ORDER BY h.start DESC LIMIT 1''', self.instance_id)
		assert rows and rows[0]['finished_at'] and not rows[0]['error'] and rows[0]['errors'] == 0, rows
		print(f'Harvest completed with zero errors ({time.monotonic() - start:.2f}s)', flush=True)

	def fixture_ids(self, ids):
		return {r['id'] for r in self.query('''SELECT i.id FROM items i
			JOIN collections c ON c.id=i.collection_id
			WHERE c.instance_id=%s AND i.id=ANY(%s::uuid[])''', self.instance_id, ids)}

	def fetch(self, path, params=None, key=None):
		code = """
import json,sys,time,requests
p=json.load(sys.stdin)
url=p['url']; rows=[]; pages=0; seconds=[]
while url:
    start=time.monotonic()
    response=requests.get(url,params=p['params'] if pages==0 else None,timeout=60)
    response.raise_for_status()
    data=response.json(); seconds.append(time.monotonic()-start); pages+=1
    if not p['key']:
        print(json.dumps(data)); break
    rows.extend(data[p['key']])
    url=next((link['href'] for link in data['links'] if link['rel']=='next'),None)
else:
    print(json.dumps({'rows':rows,'pages':pages,'seconds':seconds}))
"""
		return json.loads(self.remote([self.python, '-c', code], input=json.dumps({
			'url': self.args.panoramax_url + path, 'params': params, 'key': key})))

	def verify_assets_and_stac(self, photo):
		rows = self.query('SELECT collection_id FROM items WHERE id=%s', photo)
		code = """
import json,sys,requests,pystac
source=json.load(sys.stdin)
response=requests.get(source['item_url'],timeout=30)
response.raise_for_status()
item=response.json()
collection_url=next(link['href'] for link in item['links'] if link['rel']=='collection')
response=requests.get(collection_url,timeout=30)
response.raise_for_status()
pystac.Collection.from_dict(response.json()).validate()
pystac.Item.from_dict(item).validate()
for asset in item['assets'].values():
    response=requests.get(asset['href'],headers={'Origin':'https://collector.example'},timeout=30)
    response.raise_for_status()
    assert response.headers.get('Access-Control-Allow-Origin')=='*', 'Asset lacks public CORS'
    assert response.headers.get('Content-Type','').startswith('image/') and response.content, 'Asset is not an image'
print('Collection/item pass STAC validation; all image assets load from collector with public CORS')
"""
		item_url = f"{self.args.panoramax_url}/api/collections/{rows[0]['collection_id']}/items/{photo}"
		print(self.remote([self.python, '-c', code], input=json.dumps({'item_url': item_url})).strip(), flush=True)


def local_sql(sql, **variables):
	args = ['docker', 'exec', '-i', 'hillview_postgres', 'psql', '-U', os.getenv('POSTGRES_USER', 'hillview'), '-d', os.getenv('POSTGRES_DB', 'hillview'), '-tAq', '-v', 'ON_ERROR_STOP=1']
	for key, value in variables.items():
		args += ['-v', f'{key}={value}']
	return command(args, input=sql).strip()


def sequence():
	start = time.monotonic()
	code = 'import asyncio,json; from db import get_engine; from sequencer import run_once; print(json.dumps(asyncio.run(run_once(get_engine()))))'
	result = json.loads(command(['docker', 'exec', 'hillview_panoramax', 'python', '-c', code]).splitlines()[-1])
	print(f'Sequencer pass: {time.monotonic() - start:.2f}s', flush=True)
	return result


class HeavyChecks:
	"""Optional corpus tests; every collector operation uses the same Catalog."""
	def __init__(self, args, catalog):
		self.args, self.catalog = args, catalog
		self.generator = str(Path(__file__).with_name('generate_load.py'))
		self.summary_path = Path(args.work_dir) / 'load_summary.json'
		self.summary = None

	def prepare(self):
		self.summary_path.parent.mkdir(parents=True, exist_ok=True)
		if not self.args.reuse_load:
			print(command([sys.executable, self.generator, '--photos', str(self.args.load_photos),
				'--users', str(self.args.load_users), '--years', str(self.args.load_years),
				'--seed', str(self.args.load_seed), '--summary', str(self.summary_path)]).strip(), flush=True)
		self.summary = json.loads(self.summary_path.read_text())
		self.owners = json.dumps(self.summary['user_ids'])

	def sql(self, sql, **params):
		return local_sql(sql, owners=self.owners, **params)

	def verify_synthesis(self):
		owners = "IN (SELECT json_array_elements_text(:'owners'::json))"
		stats = json.loads(self.sql(f'''SELECT json_build_object(
			'sequences',(SELECT count(*) FROM panoramax.sequences WHERE status='ready' AND owner_id {owners}),
			'memberships',(SELECT count(*) FROM panoramax.sequence_photos sp JOIN panoramax.sequences s ON s.id=sp.sequence_id WHERE s.owner_id {owners}),
			'singles',(SELECT count(*) FROM (SELECT sp.sequence_id FROM panoramax.sequence_photos sp JOIN panoramax.sequences s ON s.id=sp.sequence_id WHERE s.owner_id {owners} GROUP BY 1 HAVING count(*)=1) single_sequences));'''))
		assert stats == {'sequences': self.summary['expected_sequences'], 'memberships': self.summary['selected'], 'singles': self.summary['expected_singles']}, stats
		for owner, expected in self.summary['per_user'].items():
			if not expected['is_active'] or expected['is_test']:
				assert self.sql("SELECT count(*) FROM panoramax.sequences WHERE owner_id=:'owner';", owner=owner) == '0'
		before = self.sql('SELECT now();')
		assert not any(v for k, v in sequence().items() if k.startswith(('memberships_', 'sequences_')))
		assert self.sql("SELECT count(*) FROM panoramax.sequences WHERE updated_at > :'before';", before=before) == '0'
		print('Heavy: independent sequence/membership/single counts and no-op pass verified', flush=True)

	def verify_harvest_and_paging(self):
		excluded = self.summary['excluded_sample_ids'] + self.summary['suppressed_sample_ids']
		assert not self.catalog.fixture_ids(excluded)
		count = self.catalog.query('SELECT count(*) AS n FROM items i JOIN collections c ON c.id=i.collection_id WHERE c.instance_id=%s AND c.provider_id=ANY(%s::uuid[])', self.catalog.instance_id, self.summary['user_ids'])[0]['n']
		assert count == self.summary['selected']
		cols = self.catalog.fetch('/api/collections', {'limit': 100}, 'collections')
		ids = [c['id'] for c in cols['rows']]
		assert len(ids) == len(set(ids)) == int(local_sql("SELECT count(*) FROM panoramax.sequences WHERE status='ready';"))
		assert all(c['geovisio:status'] == 'ready' for c in cols['rows'])
		big = json.loads(self.sql('''SELECT json_build_object('id',sp.sequence_id,'n',count(*)) FROM panoramax.sequence_photos sp JOIN panoramax.sequences s ON s.id=sp.sequence_id
			WHERE s.owner_id IN (SELECT json_array_elements_text(:'owners'::json)) GROUP BY sp.sequence_id ORDER BY count(*) DESC LIMIT 1;'''))
		items = self.catalog.fetch(f"/api/collections/{big['id']}/items", {'limit': 100}, 'features')
		ranks = [i['properties']['geovisio:rank_in_collection'] for i in items['rows']]
		assert len(ranks) == len(set(ranks)) == big['n'] and ranks == sorted(ranks)
		dates = [i['properties']['datetime'] for i in items['rows']]
		assert dates == sorted(dates)
		for name, page in [('collections', cols), ('largest sequence', items)]:
			print(f"Heavy: {name}, {len(page['rows'])} records / {page['pages']} pages, max {max(page['seconds']):.3f}s", flush=True)

	def verify_churn(self):
		rows = json.loads(self.sql('''SELECT json_agg(row_to_json(x)) FROM (SELECT sp.photo_id,sp.sequence_id FROM panoramax.sequence_photos sp JOIN panoramax.sequences s ON s.id=sp.sequence_id
			WHERE s.owner_id IN (SELECT json_array_elements_text(:'owners'::json)) ORDER BY random() LIMIT 200) x;'''))
		ids = [r['photo_id'] for r in rows]
		expected_sequences = {r['sequence_id'] for r in rows}
		since = self.sql("SELECT to_char(now() AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US\"+00:00\"');")
		mark = 'churn-' + uuid.uuid4().hex
		self.sql("UPDATE photos SET title=:'mark' WHERE id IN (SELECT json_array_elements_text(:'ids'::json));", mark=mark, ids=json.dumps(ids))
		cols = self.catalog.fetch('/api/collections', {'filter': f"status IN ('deleted','ready') AND updated > '{since}'", 'limit': 1000}, 'collections')
		assert {c['id'] for c in cols['rows']} == expected_sequences
		self.catalog.harvest()
		assert self.catalog.query("SELECT count(*) AS n FROM items WHERE id=ANY(%s::uuid[]) AND content->'properties'->>'title'=%s", ids, mark)[0]['n'] == len(ids)
		print(f'Heavy: {len(ids)} edits propagated through the exact changed-sequence set', flush=True)

	def verify_deactivation(self):
		owner = self.sql("SELECT id FROM users WHERE username=:'name';", name=self.summary['heaviest_user'])
		rows = json.loads(self.sql("SELECT json_agg(id ORDER BY id) FROM panoramax.sequences WHERE owner_id=:'owner' AND status='ready';", owner=owner))
		ids = set(rows)
		before_count = self.sql("SELECT count(*) FROM panoramax.sequences WHERE owner_id=:'owner';", owner=owner)
		count = self.catalog.query('SELECT count(*) AS n FROM items WHERE collection_id=ANY(%s::uuid[])', rows)[0]['n']
		since = self.sql("SELECT to_char(now() AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US\"+00:00\"');")
		try:
			self.sql("UPDATE users SET is_active=false WHERE id=:'owner';", owner=owner)
			assert not self.catalog.fetch(f'/api/collections/{rows[0]}/items')['features']
			sequence()
			assert self.sql("SELECT count(*) FROM panoramax.sequences WHERE owner_id=:'owner' AND status='ready';", owner=owner) == '0'
			cols = self.catalog.fetch('/api/collections', {'filter': f"status='deleted' AND updated > '{since}'", 'limit': 1000}, 'collections')
			assert ids == {c['id'] for c in cols['rows']}
			self.catalog.harvest()
			assert self.catalog.query('SELECT count(*) AS n FROM collections WHERE instance_id=%s AND id=ANY(%s::uuid[])', self.catalog.instance_id, rows)[0]['n'] == 0
			assert self.catalog.query('SELECT count(*) AS n FROM items WHERE collection_id=ANY(%s::uuid[])', rows)[0]['n'] == 0
		finally:
			self.sql("UPDATE users SET is_active=true WHERE id=:'owner';", owner=owner)
		sequence()
		assert set(json.loads(self.sql("SELECT json_agg(id) FROM panoramax.sequences WHERE owner_id=:'owner' AND status='ready';", owner=owner))) == ids
		assert self.sql("SELECT count(*) FROM panoramax.sequences WHERE owner_id=:'owner';", owner=owner) == before_count
		self.catalog.harvest()
		assert self.catalog.query('SELECT count(*) AS n FROM items WHERE collection_id=ANY(%s::uuid[])', rows)[0]['n'] == count
		print('Heavy: contributor deactivation, tombstones and same-ID revival verified', flush=True)

	def cleanup(self):
		if self.summary and not self.args.keep_load:
			# Publish tombstones before deleting the generated sequences themselves.
			self.sql("UPDATE users SET panoramax_contributor=false WHERE id IN (SELECT json_array_elements_text(:'owners'::json));")
			sequence()
			self.catalog.harvest()
			command([sys.executable, self.generator, '--cleanup', '--prefix', self.summary['prefix']])
			self.catalog.query('DELETE FROM providers WHERE instance_id=%s AND id=ANY(%s::uuid[]) RETURNING id', self.catalog.instance_id, self.summary['user_ids'])
			print('Heavy corpus removed and withdrawn from the collector', flush=True)


async def run(args):
	catalog = Catalog(args)
	catalog.register()
	heavy = HeavyChecks(args, catalog) if args.heavy or args.cleanup_load else None
	if args.cleanup_load:
		args.reuse_load = True
		args.keep_load = False
		heavy.prepare()
		heavy.cleanup()
		return
	username = 'pano_e2e_' + uuid.uuid4().hex[:12]
	password = secrets.token_urlsafe(24) + 'Aa1!'
	token = None
	ids = []
	upload = SecureUploadClient(api_url=args.api_url)
	async with httpx.AsyncClient(base_url=args.api_url + '/', verify=tls_verify(), timeout=60) as api:
		try:
			response = await api.post('auth/register', json={'username': username, 'password': password, 'email': username + '@example.com'})
			response.raise_for_status()
			owner = response.json()['id']
			response = await api.post('auth/token', data={'username': username, 'password': password})
			response.raise_for_status()
			token = response.json()['access_token']
			api.headers['Authorization'] = 'Bearer ' + token
			keys = upload.generate_client_keys()
			await upload.register_client_key(token, keys)
			day = (datetime.now(timezone.utc) - timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)
			# Four positions in two sessions, two repeated views (newest daytime
			# beats older daytime and newer night), another bearing in that cell,
			# an owner opt-out and an incompatible CC grant.
			fixtures = [
				(day, 0, 90, 'full1', True),
				(day + timedelta(minutes=2), 1, 90, 'panoramax_in', True),
				(day + timedelta(hours=4), 2, 90, 'full1', True),
				(day + timedelta(hours=4, minutes=2), 3, 90, 'panoramax_in', True),
				(day + timedelta(days=1, hours=12), 0, 90, 'full1', True),
				(day + timedelta(days=1), 0, 90, 'panoramax_in', True),
				(day, 0, 180, 'full1', True),
				(day, 4, 90, 'full1', False),
				(day, 5, 90, 'ccbysa4+osm', True),
			]
			for i, (at, position, bearing, grant, sharing) in enumerate(fixtures):
				lat, lon = 50.0755, 14.4378 + position * .00055
				image = create_test_image_full_gps(240, 180, (30 + 20 * i, 90, 160), lat, lon, bearing)
				filename = f'{username}_{i}.jpg'
				auth = await upload.authorize_upload_with_params(token, filename, len(image), lat, lon,
					'Isolated federation test', file_data=image, captured_at=at.isoformat(),
					license=grant, panoramax_share=sharing, title=f'Federation fixture {i}')
				ids.append(auth['photo_id'])
				await upload.upload_to_worker(image, auth, keys, filename=filename, fast=True)
			print('Uploaded nine isolated fixtures through the real worker', flush=True)
			for pid in ids:
				for _ in range(120):
					response = await api.get('photos/' + pid)
					response.raise_for_status()
					status = response.json()['processing_status']
					assert status != 'error', response.json().get('error')
					if status == 'completed': break
					await asyncio.sleep(1)
				else: raise AssertionError('Worker did not finish ' + pid)
			if heavy:
				heavy.prepare()
			print('All fixtures processed; sequencer:', sequence(), flush=True)
			if heavy:
				heavy.verify_synthesis()
			expected = {ids[i] for i in (1, 2, 3, 5, 6)}
			selected = json.loads(local_sql("SELECT coalesce(json_agg(sp.photo_id),'[]') FROM panoramax.sequence_photos sp JOIN photos p ON p.id=sp.photo_id WHERE p.owner_id=:'owner';", owner=owner))
			assert set(selected) == expected, (selected, expected)
			assert local_sql("SELECT count(*) FROM panoramax.sequences WHERE owner_id=:'owner' AND status='ready';", owner=owner) == '3'
			catalog.harvest(full=True)
			assert catalog.fixture_ids(ids) == expected
			collections = catalog.query('''SELECT c.id,c.computed_geom IS NOT NULL AS has_geometry,p.id AS provider
				FROM collections c JOIN providers p ON p.id=c.provider_id
				WHERE c.instance_id=%s AND c.provider_id=%s''', catalog.instance_id, owner)
			assert len(collections) == 3 and any(c['has_geometry'] for c in collections)
			print('Full harvest: five winners; daytime, freshness, bearing, grant and owner-consent gates verified', flush=True)
			catalog.verify_assets_and_stac(ids[1])
			first_seq = local_sql("SELECT sequence_id FROM panoramax.sequence_photos WHERE photo_id=:'photo';", photo=ids[1])
			page = catalog.fetch(f'/api/collections/{first_seq}/items', {'limit': 1}, 'features')
			assert page['pages'] == 3 and {p['id'] for p in page['rows']} == {ids[1], ids[6]}
			assert [p['properties']['geovisio:rank_in_collection'] for p in page['rows']] == [1, 2]
			if heavy:
				heavy.verify_harvest_and_paging()
				heavy.verify_churn()

			photo = ids[5]  # its own next-day session, so withdrawal also tombstones it
			seq_id = local_sql("SELECT sequence_id FROM panoramax.sequence_photos WHERE photo_id=:'photo';", photo=photo)
			response = await api.patch('photos/' + photo, json={'title': 'Federation edited title'})
			response.raise_for_status()
			catalog.harvest()
			rows = catalog.query("SELECT content->'properties'->>'title' AS title FROM items WHERE id=%s", photo)
			assert rows[0]['title'] == 'Federation edited title'
			print('Owner title edit propagated through an incremental harvest', flush=True)

			deleted_seq = local_sql("SELECT sequence_id FROM panoramax.sequence_photos WHERE photo_id=:'photo';", photo=ids[2])
			response = await api.delete('photos/' + ids[2])
			response.raise_for_status()
			assert ids[2] not in {p['id'] for p in catalog.fetch(f'/api/collections/{deleted_seq}/items')['features']}
			sequence()
			catalog.harvest()
			assert catalog.fixture_ids(ids) == expected - {ids[2]}
			assert catalog.query('SELECT id FROM deleted_items WHERE id=%s', ids[2])
			local_sql("UPDATE photos SET deleted=false WHERE id=:'photo' AND owner_id=:'owner';", photo=ids[2], owner=owner)
			sequence()
			catalog.harvest()
			assert catalog.fixture_ids(ids) == expected
			print('Photo deletion and restoration propagated to the catalog', flush=True)

			response = await api.patch('photos/' + photo, json={'panoramax_share': False})
			response.raise_for_status()
			assert not catalog.fetch(f'/api/collections/{seq_id}/items')['features'], 'Withdrawal must hide the photo before a sequencer pass'
			sequence()
			catalog.harvest()
			assert catalog.fixture_ids(ids) == (expected - {photo}) | {ids[0]}, 'Older eligible daytime view should replace the withdrawn winner'
			assert local_sql("SELECT status FROM panoramax.sequences WHERE id=:'seq';", seq=seq_id) == 'deleted'
			assert not catalog.query('SELECT id FROM collections WHERE instance_id=%s AND id=%s', catalog.instance_id, seq_id)
			assert catalog.query('SELECT id FROM deleted_items WHERE id=%s', photo)
			tombstones = catalog.fetch('/api/collections', {'filter': "status='deleted'", 'limit': 1000}, 'collections')
			assert seq_id in {c['id'] for c in tombstones['rows']}
			assert all(c['geovisio:status'] == 'ready' for c in catalog.fetch('/api/collections')['collections'])
			print('Consent withdrawal: immediate hiding, replacement winner, sequence tombstone and catalog deletion verified', flush=True)

			response = await api.patch('photos/' + photo, json={'panoramax_share': True})
			response.raise_for_status()
			sequence()
			assert local_sql("SELECT sequence_id FROM panoramax.sequence_photos WHERE photo_id=:'photo';", photo=photo) == seq_id
			catalog.harvest()
			assert catalog.fixture_ids(ids) == expected
			print('Sharing restored: same sequence identity and catalog item revived', flush=True)
			if heavy:
				heavy.verify_deactivation()
		finally:
			try:
				if heavy:
					heavy.cleanup()
			finally:
				if token:
					response = await api.delete('user/delete')
					response.raise_for_status()
					sequence()
					catalog.harvest()
					assert not catalog.fixture_ids(ids)
					catalog.query('''DELETE FROM providers p WHERE p.instance_id=%s AND p.id=%s
						AND NOT EXISTS (SELECT 1 FROM collections c WHERE c.provider_id=p.id) RETURNING p.id''', catalog.instance_id, owner)
					print('Temporary account and photos removed; catalog fixtures withdrawn', flush=True)
	print('Federation E2E PASSED', flush=True)


def main():
	p = argparse.ArgumentParser(description=__doc__)
	p.add_argument('--catalog-ssh', help='SSH destination; omit to run the collector CLI locally')
	p.add_argument('--harvester', required=True, help='Absolute stac-harvester path on the collector host')
	p.add_argument('--ca-bundle', help='Combined CA bundle on the collector host for requests and aiohttp')
	p.add_argument('--catalog-db', default='postgresql://username:password@localhost:5439/panoramax')
	p.add_argument('--instance-name', default='hillview-e2e')
	p.add_argument('--panoramax-url', required=True)
	p.add_argument('--api-url', default='http://localhost:8055/api')
	p.add_argument('--heavy', action='store_true')
	p.add_argument('--cleanup-load', action='store_true')
	p.add_argument('--keep-load', action='store_true')
	p.add_argument('--reuse-load', action='store_true', help='Reuse the heavy corpus manifest in --work-dir')
	p.add_argument('--load-photos', type=int, default=int(os.getenv('LOAD_PHOTOS', '50000')))
	p.add_argument('--load-users', type=int, default=int(os.getenv('LOAD_USERS', '40')))
	p.add_argument('--load-years', type=float, default=float(os.getenv('LOAD_YEARS', '3')))
	p.add_argument('--load-seed', type=int, default=int(os.getenv('LOAD_SEED', '1')))
	p.add_argument('--work-dir', default='/tmp/panoramax-e2e')
	asyncio.run(run(p.parse_args()))


if __name__ == '__main__':
	main()
