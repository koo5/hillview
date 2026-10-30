"""Panoramax/GeoVisio-compatible read API.

Serves the three endpoints the meta-catalog harvester actually consumes —
/api/configuration (add-instance aborts without it), /api/collections (CQL2
status/updated filter + rel=next paging), /api/collections/{id}/items (limit +
rel=next) — plus the STAC landing page and single-resource routes for
completeness. Users/map/RSS/search endpoints are deliberately absent: the
catalog regenerates those itself.

Read-only over photos/users; sequences come from the panoramax schema
maintained by the in-process sequencer (sequencer.py).
"""
import asyncio
import contextlib
import logging
import uuid as uuid_mod
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text

import sequencer
import settings
from cql import FilterParseError, parse_collections_filter
from db import get_engine
from eligibility import ELIGIBLE_PHOTO_WHERE, PHOTO_ORDER_BY
from stac import (
	STAC_VERSION, collection_json, explorer_map_view, fmt_dt, hillview_map_url, item_json,
	photo_detail_url, with_query,
)

logger = logging.getLogger('panoramax.api')

app = FastAPI(
	title='Hillview Panoramax API',
	description='GeoVisio-compatible read API for the Panoramax federation',
	docs_url=None, redoc_url=None, openapi_url=None,
)

# Optional, not required by the federation. The harvester is server-side (no
# CORS), the federated viewer reads the meta-catalog rather than instances, the
# catalog's per-item rel=via link to us is a navigation (not a fetch), and our
# own hillview.cz frontend reads api.panoramax.xyz, never this endpoint. So
# nothing in the normal flow needs it; it's a zero-cost hedge for a third-party
# STAC browser or a console poking us from another origin. Harmless because
# everything here is public, anonymous and cookieless, so `*` without
# credentials exposes nothing a server-side fetch couldn't already read.
# The genuinely REQUIRED CORS is on the asset hosts named in `sizes` (the
# viewer loads photos as WebGL textures) — that lives in the pics vhosts /
# bucket config, not here.
app.add_middleware(
	CORSMiddleware,
	allow_origins=['*'],
	allow_methods=['GET', 'HEAD', 'OPTIONS'],
	allow_headers=['*'],
	max_age=86400,
)


@app.on_event('startup')
async def _startup() -> None:
	# always build the engine here, sequencer or not: it fails fast at boot on
	# an empty DATABASE_URL password instead of on the first request
	engine = get_engine()
	if settings.sequencer_enabled():
		app.state.sequencer_task = asyncio.create_task(sequencer.loop(engine))


@app.on_event('shutdown')
async def _shutdown() -> None:
	task = getattr(app.state, 'sequencer_task', None)
	if task:
		task.cancel()
		with contextlib.suppress(asyncio.CancelledError):
			await task


def _base_url() -> str:
	return settings.base_url()


def _as_uuid(value: str, status_code: int = 404) -> uuid_mod.UUID:
	"""Bind UUIDs as uuid objects (asyncpg array-type inference) and turn
	garbage input into a clean HTTP error instead of a driver DataError."""
	try:
		return uuid_mod.UUID(value)
	except (ValueError, AttributeError, TypeError):
		raise HTTPException(status_code=status_code, detail='Not a valid id')


async def _served_photo(photo_id: str):
	"""(lat, lon, bearing, width, height) of a photo this service serves, else
	None. Only served photos are looked up, so the position of anything else
	never leaves the database."""
	scope = settings.active_scope()
	async with get_engine().connect() as conn:
		return (await conn.execute(text(f"""
			SELECT ST_Y(p.geometry), ST_X(p.geometry), p.compass_angle, p.width, p.height
			FROM panoramax.sequence_photos sp
			JOIN photos p ON p.id = sp.photo_id
			JOIN users u ON u.id = p.owner_id
			WHERE p.id = :photo_id AND {ELIGIBLE_PHOTO_WHERE}
		"""), {'photo_id': photo_id, 'scope_legal_rights': list(scope.legal_rights)})).first()


async def _viewer_target(pic: str | None, focus: str | None, map_view: str | None) -> str:
	"""Where `/` sends a human, from the web viewer's own query string.

	- A photo we serve: that photo on Hillview's map at its own position and
	  bearing; with focus=pic (the explorer showed the photo large), in
	  Hillview's zoom view on the whole photo.
	- focus=meta (the explorer showed the photo's details): Hillview's detail
	  page of that photo.
	- Any other well-formed pic: that photo id at the explorer's own map
	  position. The frontend then checks it against Hillview's API with the
	  visitor's own access (verifyUrlRequestedPhoto), so the redirect adds
	  nothing the URL did not already hold.
	- No usable pic: the explorer's map position, else the start page.
	"""
	viewer = settings.viewer_url()
	try:
		photo_id = str(uuid_mod.UUID(pic)) if pic else None
	except ValueError:
		photo_id = None
	if photo_id and focus == 'meta':
		return photo_detail_url(viewer, photo_id)
	served = await _served_photo(photo_id) if photo_id else None
	if served:
		lat, lon, bearing, width, height = served
		zoom_view_height = height / width if focus == 'pic' and width and height else None
		return hillview_map_url(viewer, lat, lon, bearing=bearing, photo_id=photo_id,
			zoom_view_height=zoom_view_height)
	lat, lon, zoom = explorer_map_view(map_view) or (None, None, 18)
	return hillview_map_url(viewer, lat, lon, zoom, photo_id=photo_id)


@app.get('/')
async def root(
	pic: str | None = Query(default=None),
	focus: str | None = Query(default=None),
	map_view: str | None = Query(default=None, alias='map'),
) -> RedirectResponse:
	# Humans arrive here from the catalog's per-item rel=via link, which points
	# at the registered instance URL; the web viewer's "Origin instance" link
	# appends the explorer's own query string (pic, seq, focus, map, xyz, ...).
	# Send them to the matching place in Hillview, never to STAC JSON (the
	# harvester only ever requests /api/*).
	return RedirectResponse(url=await _viewer_target(pic, focus, map_view))


@app.get('/api/health')
async def health() -> dict:
	async with get_engine().connect() as conn:
		await conn.execute(text('SELECT 1'))
	return {'status': 'ok'}


@app.get('/api/')
@app.get('/api')
async def landing() -> dict:
	base = _base_url()
	scope = settings.active_scope()
	return {
		'type': 'Catalog',
		'stac_version': STAC_VERSION,
		'id': 'hillview-panoramax',
		'title': settings.instance_name(),
		'description': (
			f"Panoramax-compatible (GeoVisio STAC) view of {settings.instance_name()} "
			f"photos published under {scope.license}."
		),
		# Only classes we actually satisfy. Dropped vs an earlier fuller list:
		#   ogcapi-features-1/core  — needs a /conformance endpoint + real
		#                             bbox/datetime filtering, neither present
		#   ogcapi-features-3/filter + cql2/cql2-text — need /queryables and
		#                             feature-level filtering; our `filter` is
		#                             only the status/updated subset on
		#                             /collections (all the harvester needs)
		# The reference GeoVisio server doesn't advertise filter/cql2 either.
		# Re-add a class only alongside the endpoints that back it.
		'conformsTo': [
			'https://api.stacspec.org/v1.0.0/core',
			'https://api.stacspec.org/v1.0.0/collections',
			'https://api.stacspec.org/v1.0.0/ogcapi-features',
			'http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson',
		],
		'links': [
			{'rel': 'self', 'href': f"{base}/api/", 'type': 'application/json'},
			{'rel': 'root', 'href': f"{base}/api/", 'type': 'application/json'},
			{'rel': 'data', 'href': f"{base}/api/collections", 'type': 'application/json'},
		],
	}


@app.get('/api/configuration')
async def configuration() -> dict:
	scope = settings.active_scope()
	return {
		'name': settings.instance_name(),
		'logo': settings.logo_url(),
		# Placeholder declaration until the panoramax outflow wording is final.
		'description': (
			'Hillview (https://hillview.cz) serves a Panoramax-compatible read API. '
			'Owners opt in per photo under the full1 or panoramax_in intake grant; '
			'only approved contributions with no anonymization doodles are federated. '
			'Photos remain hosted on Hillview. The Panoramax outflow licence wording '
			f'and this {scope.license} declaration are placeholders pending final terms. '
			'Full terms: https://hillview.cz/licensing'
		),
		'license': {'id': scope.license, 'url': scope.license_url},
		'auth': {'enabled': False},
		# The Panoramax mobile app can be pointed at instances that accept
		# external contributions; this one is read-only (uploads go through
		# hillview.cz).
		'geovisio:external_contributions': False,
	}


# --- collections -----------------------------------------------------------

# Aggregates over *servable* member photos only, so counts/extents never leak
# photos that flipped out of scope between sequencer passes.
_COLLECTION_AGG_SQL = f"""
	SELECT
		sp.sequence_id,
		count(*) AS item_count,
		min(p.effective_at) AS min_dt,
		max(p.effective_at) AS max_dt,
		ST_XMin(ST_Extent(p.geometry)) AS xmin,
		ST_YMin(ST_Extent(p.geometry)) AS ymin,
		ST_XMax(ST_Extent(p.geometry)) AS xmax,
		ST_YMax(ST_Extent(p.geometry)) AS ymax
	FROM panoramax.sequence_photos sp
	JOIN photos p ON p.id = sp.photo_id
	JOIN users u ON u.id = p.owner_id
	WHERE sp.sequence_id = ANY(:seq_ids) AND {ELIGIBLE_PHOTO_WHERE}
	GROUP BY sp.sequence_id
"""


async def _fetch_collections_page(
	statuses: set[str], updated_after, updated_inclusive: bool,
	limit: int, after_id: str | None,
) -> list[dict[str, Any]]:
	scope = settings.active_scope()
	base = _base_url()
	where = ["s.scope = :scope", "s.status = ANY(:statuses)"]
	params: dict[str, Any] = {'scope': scope.id, 'statuses': sorted(statuses), 'limit': limit}
	if updated_after is not None:
		where.append(f"s.updated_at {'>=' if updated_inclusive else '>'} :updated_after")
		params['updated_after'] = updated_after
	if after_id:
		where.append("s.id > :after_id")
		params['after_id'] = _as_uuid(after_id, status_code=400)

	async with get_engine().connect() as conn:
		seq_rows = (await conn.execute(text(f"""
			SELECT s.id, s.status, s.owner_id, u.username, s.created_at, s.updated_at
			FROM panoramax.sequences s
			LEFT JOIN users u ON u.id = s.owner_id
			WHERE {' AND '.join(where)}
			ORDER BY s.id
			LIMIT :limit
		"""), params)).all()

		ready_ids = [r[0] for r in seq_rows if r[1] == 'ready']
		aggs: dict[str, Any] = {}
		if ready_ids:
			for agg in (await conn.execute(
				text(_COLLECTION_AGG_SQL),
				{'seq_ids': ready_ids, 'scope_legal_rights': list(scope.legal_rights)},
			)).all():
				aggs[str(agg[0])] = agg

	collections = []
	for r in seq_rows:
		seq_id = str(r[0])
		agg = aggs.get(seq_id)
		collections.append(collection_json(
			seq_id=seq_id,
			status=r[1],
			owner_id=r[2],
			username=r[3],
			created_at=r[4],
			updated_at=r[5],
			item_count=agg[1] if agg else 0,
			bbox=[agg[4], agg[5], agg[6], agg[7]] if agg else None,
			min_dt=agg[2] if agg else None,
			max_dt=agg[3] if agg else None,
			license_id=scope.license,
			license_url=scope.license_url,
			base_url=base,
		))
	return collections


@app.get('/api/collections')
async def collections(
	request: Request,
	filter: str | None = Query(default=None),
	limit: int = Query(default=settings.COLLECTIONS_PAGE_DEFAULT, ge=1,
		le=settings.COLLECTIONS_PAGE_MAX),
	page_after: str | None = Query(default=None),
) -> JSONResponse:
	try:
		parsed = parse_collections_filter(filter)
	except FilterParseError as e:
		raise HTTPException(status_code=400, detail=str(e))
	# GeoVisio semantics: without an explicit status filter, tombstones are
	# hidden; the harvester asks for them explicitly on incremental syncs.
	statuses = parsed.statuses or {'ready'}

	page = await _fetch_collections_page(
		statuses, parsed.updated_after, parsed.updated_inclusive,
		limit, page_after)

	base = _base_url()
	links = [
		{'rel': 'self', 'href': with_query(f"{base}/api/collections", request.url.query), 'type': 'application/json'},
		{'rel': 'root', 'href': f"{base}/api/", 'type': 'application/json'},
	]
	if len(page) == limit:
		next_params = dict(request.query_params)
		next_params['page_after'] = page[-1]['id']
		links.append({
			'rel': 'next',
			'href': f"{base}/api/collections?{urlencode(next_params)}",
			'type': 'application/json',
		})
	return JSONResponse({'collections': page, 'links': links})


async def _load_sequence(seq_id: str):
	scope = settings.active_scope()
	async with get_engine().connect() as conn:
		row = (await conn.execute(text("""
			SELECT s.id, s.status, s.owner_id, u.username, s.created_at, s.updated_at
			FROM panoramax.sequences s
			LEFT JOIN users u ON u.id = s.owner_id
			WHERE s.id = :seq_id AND s.scope = :scope
		"""), {'seq_id': _as_uuid(seq_id), 'scope': scope.id})).first()
	return row


@app.get('/api/collections/{seq_id}')
async def collection(seq_id: str) -> dict:
	scope = settings.active_scope()
	row = await _load_sequence(seq_id)
	if row is None:
		raise HTTPException(status_code=404, detail='Collection not found')

	agg = None
	if row[1] == 'ready':
		async with get_engine().connect() as conn:
			agg = (await conn.execute(
				text(_COLLECTION_AGG_SQL),
				{'seq_ids': [row[0]], 'scope_legal_rights': list(scope.legal_rights)},
			)).first()
	return collection_json(
		seq_id=str(row[0]),
		status=row[1],
		owner_id=row[2],
		username=row[3],
		created_at=row[4],
		updated_at=row[5],
		item_count=agg[1] if agg else 0,
		bbox=[agg[4], agg[5], agg[6], agg[7]] if agg else None,
		min_dt=agg[2] if agg else None,
		max_dt=agg[3] if agg else None,
		license_id=scope.license,
		license_url=scope.license_url,
		base_url=_base_url(),
	)


# --- items -----------------------------------------------------------------

_ITEMS_SQL = f"""
	SELECT
		p.id, sp.rank,
		ST_X(p.geometry) AS lon, ST_Y(p.geometry) AS lat,
		p.effective_at, p.uploaded_at, p.compass_angle,
		p.width, p.height, p.original_filename, p.title, p.description,
		p.sizes, u.username, p.owner_id
	FROM panoramax.sequence_photos sp
	JOIN photos p ON p.id = sp.photo_id
	JOIN users u ON u.id = p.owner_id
	WHERE sp.sequence_id = :seq_id AND sp.rank > :after_rank AND {ELIGIBLE_PHOTO_WHERE}
	ORDER BY sp.rank
	LIMIT :limit
"""


@app.get('/api/collections/{seq_id}/items')
async def items(
	request: Request,
	seq_id: str,
	limit: int = Query(default=settings.ITEMS_PAGE_DEFAULT, ge=1,
		le=settings.ITEMS_PAGE_MAX),
	page_after_rank: int = Query(default=0, ge=0),
) -> JSONResponse:
	scope = settings.active_scope()
	row = await _load_sequence(seq_id)
	if row is None:
		raise HTTPException(status_code=404, detail='Collection not found')
	if row[1] == 'deleted':
		raise HTTPException(status_code=404, detail='Collection is deleted')

	async with get_engine().connect() as conn:
		photo_rows = (await conn.execute(text(_ITEMS_SQL), {
			'seq_id': row[0],
			'after_rank': page_after_rank,
			'limit': limit,
			'scope_legal_rights': list(scope.legal_rights),
		})).all()

	base = _base_url()
	features = []
	for r in photo_rows:
		feature = item_json(
			photo_id=r[0], seq_id=seq_id, rank=r[1],
			lon=r[2], lat=r[3],
			effective_at=r[4], uploaded_at=r[5],
			compass_angle=r[6], width=r[7], height=r[8],
			original_filename=r[9], title=r[10], description=r[11],
			sizes=r[12] or {}, username=r[13], owner_id=r[14],
			license_id=scope.license, base_url=base,
		)
		if feature:
			features.append(feature)

	self_href = f"{base}/api/collections/{seq_id}/items"
	links = [
		{'rel': 'self', 'href': with_query(self_href, request.url.query), 'type': 'application/geo+json'},
		{'rel': 'collection', 'href': f"{base}/api/collections/{seq_id}", 'type': 'application/json'},
		{'rel': 'root', 'href': f"{base}/api/", 'type': 'application/json'},
	]
	if len(photo_rows) == limit:
		next_params = dict(request.query_params)
		next_params['page_after_rank'] = str(photo_rows[-1][1])
		links.append({
			'rel': 'next',
			'href': f"{self_href}?{urlencode(next_params)}",
			'type': 'application/geo+json',
		})
	return JSONResponse({
		'type': 'FeatureCollection',
		'features': features,
		'links': links,
	})


@app.get('/api/collections/{seq_id}/items/{item_id}')
async def item(seq_id: str, item_id: str) -> dict:
	scope = settings.active_scope()
	row = await _load_sequence(seq_id)
	if row is None or row[1] == 'deleted':
		raise HTTPException(status_code=404, detail='Collection not found')

	async with get_engine().connect() as conn:
		r = (await conn.execute(text(f"""
			SELECT
				p.id, sp.rank,
				ST_X(p.geometry) AS lon, ST_Y(p.geometry) AS lat,
				p.effective_at, p.uploaded_at, p.compass_angle,
				p.width, p.height, p.original_filename, p.title, p.description,
				p.sizes, u.username, p.owner_id
			FROM panoramax.sequence_photos sp
			JOIN photos p ON p.id = sp.photo_id
			JOIN users u ON u.id = p.owner_id
			WHERE sp.sequence_id = :seq_id AND p.id = :item_id AND {ELIGIBLE_PHOTO_WHERE}
		"""), {
			'seq_id': row[0], 'item_id': item_id,
			'scope_legal_rights': list(scope.legal_rights),
		})).first()
	if r is None:
		raise HTTPException(status_code=404, detail='Item not found')

	feature = item_json(
		photo_id=r[0], seq_id=seq_id, rank=r[1],
		lon=r[2], lat=r[3],
		effective_at=r[4], uploaded_at=r[5],
		compass_angle=r[6], width=r[7], height=r[8],
		original_filename=r[9], title=r[10], description=r[11],
		sizes=r[12] or {}, username=r[13], owner_id=r[14],
		license_id=scope.license, base_url=_base_url(),
	)
	if feature is None:
		raise HTTPException(status_code=404, detail='Item not found')
	return feature
