"""STAC serialization: sequences -> Collections, photos -> Items.

Shapes follow what the meta-catalog harvester actually consumes (verified
against its schema and code):
- collection/item ids are cast to UUID PK columns in the catalog;
- items get `collection` (UUID), NOT NULL GeoJSON `geometry`, and a
  `properties.datetime` postgres can parse;
- collection `providers[*].id` is cast to a UUID global PK (we use the owner's
  user id) and `name` is NOT NULL;
- tombstones are flagged by top-level `geovisio:status: "deleted"` while the
  CQL2 `status` queryable filters them — both names refer to the same state;
- ordering is `properties["geovisio:rank_in_collection"]` (int, 1-based);
- absolute asset hrefs are kept verbatim by the harvester, so we point straight
  at the existing CDN/pics WebP derivatives.
"""
import json
import math
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

STAC_VERSION = '1.0.0'


def fmt_dt(dt: datetime | None) -> str | None:
	"""ISO-8601 with microseconds and a numeric UTC offset — NEVER a 'Z'
	suffix: the meta-catalog's jsonb_date() SQL function (indexes + incremental
	crawl) parses collection created/updated with the hard-coded format
	YYYY-MM-DD"T"HH24:MI:SS.USTZH:TZM, which rejects 'Z' and needs the .US
	microseconds present. Naive datetimes in this DB are UTC by convention
	(photos.captured_at/effective_at)."""
	if dt is None:
		return None
	if dt.tzinfo is None:
		dt = dt.replace(tzinfo=timezone.utc)
	return dt.astimezone(timezone.utc).isoformat(timespec='microseconds')


# Asset media types by file suffix. Most derivatives are WebP, but older
# photos and the Tigris pool carry JPEG, and clients that select assets on
# `image/jpeg` only find those when the type says so. Not `mimetypes`: whether
# it knows .webp depends on the host's mime.types, and this image's does not.
_MEDIA_TYPES = {
	'.webp': 'image/webp',
	'.jpg': 'image/jpeg',
	'.jpeg': 'image/jpeg',
	'.png': 'image/png',
}


def media_type(url: str) -> str | None:
	"""The image media type a URL's file suffix names, or None if unknown."""
	return _MEDIA_TYPES.get(PurePosixPath(urlsplit(url).path).suffix.lower())


# Hillview's Leaflet map limits (minZoom / maxZoom in Map.svelte).
HILLVIEW_ZOOM_RANGE = (3, 23)


def hillview_map_url(
	viewer_url: str, lat: float | None = None, lon: float | None = None, zoom: float = 18,
	bearing: float | None = None, photo_id: str | None = None, zoom_view_height: float | None = None,
) -> str:
	"""A Hillview map URL in the frontend's own shape (constructPhotoMapPath in
	urlUtilsServer.ts, the share URL in urlUtils.ts): position, bearing, the
	photo, then the zoom view rectangle. That rectangle is in OpenSeadragon
	coordinates with the width normalized to 1, so the whole photo runs from
	0,0 to 1,height/width. Without a position the frontend locates the photo
	itself; with nothing at all it is the start page."""
	params: dict[str, Any] = {}
	if lat is not None and lon is not None:
		params.update(lat=round(lat, 7), lon=round(lon, 7), zoom=zoom)
	if bearing is not None:
		params['bearing'] = bearing
	if photo_id:
		params['photo'] = f'hillview-{photo_id}'
		if zoom_view_height:
			params.update(x1=0, y1=0, x2=1, y2=round(zoom_view_height, 6))
	return f'{viewer_url}/?{urlencode(params)}' if params else viewer_url


def photo_detail_url(viewer_url: str, photo_id: str) -> str:
	"""Hillview's detail page of one photo (getPhotoDetailUrl in photoUtils.ts)."""
	return f"{viewer_url}/photo/{quote(f'hillview-{photo_id}', safe='')}"


def explorer_map_view(value: str | None) -> tuple[float, float, float] | None:
	"""The Panoramax web viewer's `map=zoom/lat/lon` as (lat, lon, zoom) for
	Hillview's map, or None if absent or malformed. The viewer's MapLibre uses
	512 px tiles where Leaflet uses 256 px, so the same scale is one zoom level
	higher here."""
	try:
		zoom, lat, lon = (float(part) for part in (value or '').split('/'))
	except ValueError:
		return None
	if not (math.isfinite(zoom) and -90 <= lat <= 90 and -180 <= lon <= 180):
		return None
	low, high = HILLVIEW_ZOOM_RANGE
	return lat, lon, min(max(round(zoom) + 1, low), high)


def _numeric_variants(sizes: dict[str, Any]) -> dict[int, dict]:
	"""The plain downscale variants ('320', '2048', ...) — excludes 'full',
	'*_crop' and '*_llm' keys. JSON object keys are always strings even though
	the worker builds them as ints."""
	out = {}
	for key, info in sizes.items():
		if isinstance(info, dict) and str(key).isdigit() and info.get('url'):
			out[int(key)] = info
	return out


def pick_assets(sizes: dict[str, Any]) -> dict[str, Any] | None:
	"""Map Hillview's sizes JSON to GeoVisio's hd/sd/thumb assets.

	hd -> 'full', sd -> 2048-ish, thumb -> 640-ish. Fast-mode processing has no
	640 variant and narrow sources may lack larger ones, hence fallback chains.
	Each asset's type comes from its file suffix (`media_type`): most
	derivatives are WebP, some photos' are JPEG.
	Returns None when no usable asset exists (photo shouldn't be served then).
	"""
	if isinstance(sizes, str):
		# photos.sizes is json (not jsonb); depending on driver codec setup a
		# raw-SQL fetch may hand it over undecoded
		try:
			sizes = json.loads(sizes)
		except ValueError:
			return None
	if not isinstance(sizes, dict):
		return None
	numeric = _numeric_variants(sizes)
	full = sizes.get('full') if isinstance(sizes.get('full'), dict) else None
	if full and not full.get('url'):
		full = None

	def variant_at_most(cap: int) -> dict | None:
		widths = [w for w in numeric if w <= cap]
		return numeric[max(widths)] if widths else None

	def smallest() -> dict | None:
		return numeric[min(numeric)] if numeric else None

	hd = full or (numeric[max(numeric)] if numeric else None)
	if hd is None:
		return None
	sd = variant_at_most(2048) or smallest() or hd
	thumb = (numeric.get(640) or numeric.get(320) or smallest() or hd)

	def asset(info: dict, title: str, roles: list[str]) -> dict:
		a = {
			'href': info['url'],
			'type': media_type(info['url']),
			'title': title,
			'roles': roles,
		}
		if a['type'] is None:
			# An unknown suffix gets no type rather than a guessed one.
			del a['type']
		if info.get('width'):
			a['width'] = info['width']
		if info.get('height'):
			a['height'] = info['height']
		return a

	return {
		'hd': asset(hd, 'HD picture', ['data']),
		'sd': asset(sd, 'SD picture', ['visual']),
		'thumb': asset(thumb, 'Thumbnail', ['thumbnail']),
	}


def provider_name(username: str | None, owner_id: str | None) -> str:
	# providers.name is NOT NULL in the catalog
	if username:
		return username
	if owner_id:
		return f"user-{owner_id[:8]}"
	return 'unknown'


def with_query(href: str, query: str) -> str:
	"""A listing's `self` link: its href built from the advertised base URL,
	plus the query string exactly as the client sent it. Not request.url:
	behind a vhost that serves this API under a stripped prefix (the dev boxes'
	/geovisio) request.url has lost the prefix, while every other link is built
	from the base URL."""
	return f"{href}?{query}" if query else href


def collection_json(
	*,
	seq_id: str,
	status: str,
	owner_id: str | None,
	username: str | None,
	created_at: datetime,
	updated_at: datetime,
	item_count: int,
	bbox: list[float] | None,
	min_dt: datetime | None,
	max_dt: datetime | None,
	license_id: str,
	license_url: str,
	base_url: str,
) -> dict[str, Any]:
	self_href = f"{base_url}/api/collections/{seq_id}"
	if status == 'deleted':
		# Tombstone: served forever so the harvester's incremental diff learns
		# about the deletion. Minimal on purpose — the harvester only needs id
		# + geovisio:status + updated.
		return {
			'type': 'Collection',
			'stac_version': STAC_VERSION,
			'id': seq_id,
			'geovisio:status': 'deleted',
			'created': fmt_dt(created_at),
			'updated': fmt_dt(updated_at),
			'license': license_id,
			'extent': {
				'spatial': {'bbox': [[-180.0, -90.0, 180.0, 90.0]]},
				'temporal': {'interval': [[None, None]]},
			},
			'description': 'Deleted sequence',
			'links': [
				{'rel': 'self', 'href': self_href, 'type': 'application/json'},
			],
		}

	name = provider_name(username, owner_id)
	title = f"Photos by {name}" + (f" — {fmt_dt(min_dt)[:10]}" if min_dt else '')
	spatial_bbox = [bbox] if bbox else [[-180.0, -90.0, 180.0, 90.0]]
	return {
		'type': 'Collection',
		'stac_version': STAC_VERSION,
		'id': seq_id,
		'title': title,
		'description': f"Sequence of photos captured by {name} on Hillview",
		'geovisio:status': 'ready',
		'license': license_id,
		'created': fmt_dt(created_at),
		'updated': fmt_dt(updated_at),
		'keywords': ['pictures'],
		'providers': [
			# id is a UUID global PK in the catalog: the owner's user id.
			# Tombstoned-owner sequences (owner_id NULL) never reach this
			# branch with items, but guard anyway.
			{'name': name, 'roles': ['producer'], **({'id': owner_id} if owner_id else {})},
		],
		'extent': {
			'spatial': {'bbox': spatial_bbox},
			'temporal': {'interval': [[fmt_dt(min_dt), fmt_dt(max_dt)]]},
		},
		'stats:items': {'count': item_count},
		'links': [
			{'rel': 'self', 'href': self_href, 'type': 'application/json'},
			{'rel': 'root', 'href': f"{base_url}/api/", 'type': 'application/json'},
			{'rel': 'parent', 'href': f"{base_url}/api/", 'type': 'application/json'},
			{'rel': 'items', 'href': f"{self_href}/items", 'type': 'application/geo+json'},
			{'rel': 'license', 'href': license_url, 'title': license_id},
		],
	}


def item_json(
	*,
	photo_id: str,
	seq_id: str,
	rank: int,
	lon: float,
	lat: float,
	effective_at: datetime,
	uploaded_at: datetime | None,
	compass_angle: float | None,
	width: int | None,
	height: int | None,
	original_filename: str | None,
	title: str | None,
	description: str | None,
	sizes: dict[str, Any],
	username: str | None,
	owner_id: str | None,
	license_id: str,
	base_url: str,
) -> dict[str, Any] | None:
	assets = pick_assets(sizes)
	if assets is None:
		return None
	name = provider_name(username, owner_id)
	properties: dict[str, Any] = {
		'datetime': fmt_dt(effective_at),
		'created': fmt_dt(uploaded_at),
		'license': license_id,
		'geovisio:status': 'ready',
		'geovisio:rank_in_collection': rank,
		'geovisio:producer': name,
		# All Hillview photos are flat — no pano capture path exists.
		'pers:interior_orientation': {},
	}
	if compass_angle is not None:
		properties['view:azimuth'] = round(compass_angle) % 360
	if original_filename:
		properties['original_file:name'] = original_filename
	if title:
		properties['title'] = title
	if description:
		properties['description'] = description

	collection_href = f"{base_url}/api/collections/{seq_id}"
	return {
		'type': 'Feature',
		'stac_version': STAC_VERSION,
		'id': photo_id,
		'collection': seq_id,
		'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
		'bbox': [lon, lat, lon, lat],
		'properties': properties,
		'providers': [
			{'name': name, 'roles': ['producer'], **({'id': owner_id} if owner_id else {})},
		],
		'assets': assets,
		'links': [
			{'rel': 'self', 'href': f"{collection_href}/items/{photo_id}", 'type': 'application/geo+json'},
			{'rel': 'collection', 'href': collection_href, 'type': 'application/json'},
			{'rel': 'root', 'href': f"{base_url}/api/", 'type': 'application/json'},
		],
	}
