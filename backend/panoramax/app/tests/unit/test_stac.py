"""Serialization tests: asset fallback chains against real worker size layouts,
tombstone shape, datetime formatting (microseconds + numeric offset — the
meta-catalog's jsonb_date() rejects 'Z')."""
import json
from datetime import datetime, timezone

from stac import collection_json, fmt_dt, item_json, media_type, pick_assets, provider_name, with_query

# Worker layouts (photo_processor.create_optimized_sizes): JSON object keys are
# strings after persistence. Fast mode has no 640.
FULL_SIZES = {
	'full': {'url': 'https://pics/full.webp', 'width': 4000, 'height': 3000},
	'320': {'url': 'https://pics/320.webp', 'width': 320, 'height': 240},
	'640': {'url': 'https://pics/640.webp', 'width': 640, 'height': 480},
	'1200': {'url': 'https://pics/1200.webp', 'width': 1200, 'height': 900},
	'2048': {'url': 'https://pics/2048.webp', 'width': 2048, 'height': 1536},
	'3072': {'url': 'https://pics/3072.webp', 'width': 3072, 'height': 2304},
	'320_crop': {'url': 'https://pics/320c.webp', 'width': 320, 'height': 240},
	'1200_crop': {'url': 'https://pics/1200c.webp', 'width': 1200, 'height': 630},
	'640_llm': {'url': 'https://pics/640llm.webp', 'width': 640, 'height': 480},
}
FAST_SIZES = {
	'full': {'url': 'https://pics/full.webp', 'width': 4000, 'height': 3000},
	'320': {'url': 'https://pics/320.webp', 'width': 320, 'height': 240},
	'1200': {'url': 'https://pics/1200.webp', 'width': 1200, 'height': 900},
	'2048': {'url': 'https://pics/2048.webp', 'width': 2048, 'height': 1536},
}


class TestPickAssets:
	def test_full_layout(self):
		a = pick_assets(FULL_SIZES)
		assert a['hd']['href'] == 'https://pics/full.webp'
		assert a['sd']['href'] == 'https://pics/2048.webp'
		assert a['thumb']['href'] == 'https://pics/640.webp'
		assert all(v['type'] == 'image/webp' for v in a.values())
		assert a['hd']['roles'] == ['data']
		assert a['sd']['roles'] == ['visual']
		assert a['thumb']['roles'] == ['thumbnail']

	def test_fast_mode_thumb_falls_back_to_320(self):
		a = pick_assets(FAST_SIZES)
		assert a['thumb']['href'] == 'https://pics/320.webp'
		assert a['sd']['href'] == 'https://pics/2048.webp'

	def test_crop_and_llm_variants_never_used(self):
		a = pick_assets(FULL_SIZES)
		hrefs = json.dumps(a)
		assert 'crop' not in hrefs and 'llm' not in hrefs

	def test_narrow_source_only_full_and_320(self):
		sizes = {k: FULL_SIZES[k] for k in ('full', '320')}
		a = pick_assets(sizes)
		assert a['hd']['href'] == 'https://pics/full.webp'
		assert a['sd']['href'] == 'https://pics/320.webp'
		assert a['thumb']['href'] == 'https://pics/320.webp'

	def test_no_full_uses_largest_numeric_as_hd(self):
		sizes = {k: FULL_SIZES[k] for k in ('320', '2048')}
		assert pick_assets(sizes)['hd']['href'] == 'https://pics/2048.webp'

	def test_json_string_input(self):
		assert pick_assets(json.dumps(FULL_SIZES))['hd']['href'] == 'https://pics/full.webp'

	def test_unusable_inputs(self):
		assert pick_assets({}) is None
		assert pick_assets(None) is None
		assert pick_assets('not json') is None
		assert pick_assets({'full': {'path': 'x'}}) is None  # no url

	def test_width_height_carried(self):
		a = pick_assets(FULL_SIZES)
		assert (a['thumb']['width'], a['thumb']['height']) == (640, 480)


class TestFmtDt:
	def test_naive_is_utc_with_offset(self):
		assert fmt_dt(datetime(2026, 7, 1, 12, 0, 5)) == '2026-07-01T12:00:05.000000+00:00'

	def test_aware_converted_to_utc(self):
		dt = datetime(2026, 7, 1, 14, 0, tzinfo=timezone.utc)
		assert fmt_dt(dt) == '2026-07-01T14:00:00.000000+00:00'

	def test_none(self):
		assert fmt_dt(None) is None


class TestProviderName:
	def test_prefers_username(self):
		assert provider_name('alice', 'uuid-1') == 'alice'

	def test_fallback_is_never_null(self):
		# providers.name is NOT NULL in the catalog
		assert provider_name(None, 'abcdef12-3456') == 'user-abcdef12'
		assert provider_name(None, None) == 'unknown'


BASE_ITEM_KWARGS = dict(
	photo_id='11111111-2222-3333-4444-555555555555',
	seq_id='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
	rank=3,
	lon=14.42, lat=50.09,
	effective_at=datetime(2026, 7, 1, 10, 30),
	uploaded_at=datetime(2026, 7, 2, 8, 0, tzinfo=timezone.utc),
	compass_angle=283.6,
	width=4000, height=3000,
	original_filename='IMG_1234.jpg',
	title='A hill', description='A view of a hill',
	sizes=FULL_SIZES,
	username='alice', owner_id='99999999-8888-7777-6666-555555555555',
	license_id='CC-BY-SA-4.0',
	base_url='https://panoramax.hillview.cz',
)


class TestItemJson:
	def test_core_fields(self):
		item = item_json(**BASE_ITEM_KWARGS)
		assert item['type'] == 'Feature'
		assert item['id'] == BASE_ITEM_KWARGS['photo_id']
		assert item['collection'] == BASE_ITEM_KWARGS['seq_id']
		assert item['geometry'] == {'type': 'Point', 'coordinates': [14.42, 50.09]}
		assert item['bbox'] == [14.42, 50.09, 14.42, 50.09]

	def test_properties(self):
		p = item_json(**BASE_ITEM_KWARGS)['properties']
		assert p['datetime'] == '2026-07-01T10:30:00.000000+00:00'
		assert p['created'] == '2026-07-02T08:00:00.000000+00:00'
		assert p['geovisio:rank_in_collection'] == 3
		assert p['view:azimuth'] == 284
		assert p['license'] == 'CC-BY-SA-4.0'
		assert p['geovisio:producer'] == 'alice'
		assert p['original_file:name'] == 'IMG_1234.jpg'

	def test_azimuth_wraps_and_optional(self):
		item = item_json(**{**BASE_ITEM_KWARGS, 'compass_angle': 359.7})
		assert item['properties']['view:azimuth'] == 0
		item = item_json(**{**BASE_ITEM_KWARGS, 'compass_angle': None})
		assert 'view:azimuth' not in item['properties']

	def test_provider_id_present(self):
		providers = item_json(**BASE_ITEM_KWARGS)['providers']
		assert providers == [{
			'name': 'alice', 'roles': ['producer'],
			'id': BASE_ITEM_KWARGS['owner_id'],
		}]

	def test_unservable_sizes_returns_none(self):
		assert item_json(**{**BASE_ITEM_KWARGS, 'sizes': {}}) is None

	def test_self_link_under_collection(self):
		links = {l['rel']: l['href'] for l in item_json(**BASE_ITEM_KWARGS)['links']}
		assert links['self'].endswith(
			'/api/collections/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/items/11111111-2222-3333-4444-555555555555')


BASE_COLLECTION_KWARGS = dict(
	seq_id='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
	status='ready',
	owner_id='99999999-8888-7777-6666-555555555555',
	username='alice',
	created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
	updated_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
	item_count=12,
	bbox=[14.4, 50.0, 14.5, 50.1],
	min_dt=datetime(2026, 7, 1, 10, 0),
	max_dt=datetime(2026, 7, 1, 11, 0),
	license_id='CC-BY-SA-4.0',
	license_url='https://creativecommons.org/licenses/by-sa/4.0/',
	base_url='https://panoramax.hillview.cz',
)


class TestCollectionJson:
	def test_ready_collection(self):
		c = collection_json(**BASE_COLLECTION_KWARGS)
		assert c['type'] == 'Collection'
		assert c['geovisio:status'] == 'ready'
		assert c['license'] == 'CC-BY-SA-4.0'
		assert c['stats:items'] == {'count': 12}
		assert c['extent']['spatial']['bbox'] == [[14.4, 50.0, 14.5, 50.1]]
		assert c['extent']['temporal']['interval'] == [['2026-07-01T10:00:00.000000+00:00', '2026-07-01T11:00:00.000000+00:00']]
		assert c['providers'][0]['id'] == BASE_COLLECTION_KWARGS['owner_id']
		assert c['created'] == '2026-07-01T00:00:00.000000+00:00'
		assert c['updated'] == '2026-07-03T00:00:00.000000+00:00'

	def test_self_link(self):
		c = collection_json(**BASE_COLLECTION_KWARGS)
		links = {l['rel']: l['href'] for l in c['links']}
		# the harvester fetches items via "<self>/items"
		assert links['self'] == 'https://panoramax.hillview.cz/api/collections/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
		assert links['items'] == links['self'] + '/items'

	def test_tombstone(self):
		c = collection_json(**{
			**BASE_COLLECTION_KWARGS,
			'status': 'deleted', 'item_count': 0, 'bbox': None,
			'min_dt': None, 'max_dt': None, 'owner_id': None, 'username': None,
		})
		assert c['geovisio:status'] == 'deleted'
		assert c['id'] == BASE_COLLECTION_KWARGS['seq_id']
		assert c['updated'] == '2026-07-03T00:00:00.000000+00:00'
		# tombstones still parse as a Collection (id/type/stac_version/extent)
		assert c['type'] == 'Collection'
		assert 'extent' in c
		# but must not leak owner info
		assert 'providers' not in c


class TestWithQuery:
	# The listings' self links: base URL + path + the client's raw query, so a
	# stripped vhost prefix (/geovisio on the dev boxes) survives.
	def test_query_kept_verbatim(self):
		href = 'https://hv.example/geovisio/api/collections'
		query = "limit=1&filter=status%20IN%20('deleted','ready')"
		assert with_query(href, query) == f'{href}?{query}'

	def test_no_query_no_question_mark(self):
		assert with_query('https://hv.example/geovisio/api/collections', '') == 'https://hv.example/geovisio/api/collections'


class TestMediaType:
	def test_by_suffix(self):
		assert media_type('https://pics/opt/640/a.webp') == 'image/webp'
		assert media_type('https://pics4.t3.storage.dev/opt/1024/a.jpg') == 'image/jpeg'
		assert media_type('https://pics/a.JPEG') == 'image/jpeg'
		assert media_type('https://pics/a.png') == 'image/png'

	def test_query_and_unknown(self):
		assert media_type('https://pics/a.jpg?v=2') == 'image/jpeg'
		assert media_type('https://pics/a') is None
		assert media_type('https://pics/a.tiff') is None

	def test_assets_declare_each_files_own_type(self):
		# A JPEG original with WebP derivatives, as on older photos.
		sizes = {**FULL_SIZES, 'full': {'url': 'https://pics/full.jpg', 'width': 4000, 'height': 3000}}
		assets = pick_assets(sizes)
		assert assets['hd']['type'] == 'image/jpeg'
		assert assets['sd']['type'] == 'image/webp'
		assert assets['thumb']['type'] == 'image/webp'

	def test_unknown_suffix_gets_no_type(self):
		assets = pick_assets({'full': {'url': 'https://pics/full', 'width': 10, 'height': 10}})
		assert 'type' not in assets['hd']
