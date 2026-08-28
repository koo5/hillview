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
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text

import sequencer
import settings
from cql import FilterParseError, parse_collections_filter
from db import get_engine
from eligibility import ELIGIBLE_PHOTO_WHERE, PHOTO_ORDER_BY
from stac import STAC_VERSION, collection_json, fmt_dt, item_json

logger = logging.getLogger('panoramax.api')

app = FastAPI(
	title='Hillview Panoramax API',
	description='GeoVisio-compatible read API for the Panoramax federation',
	docs_url=None, redoc_url=None, openapi_url=None,
)


@app.on_event('startup')
async def _startup() -> None:
	if settings.sequencer_enabled():
		app.state.sequencer_task = asyncio.create_task(sequencer.loop(get_engine()))


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


@app.get('/')
async def root() -> RedirectResponse:
	# Humans arrive here from the catalog's per-item rel=via link, which points
	# at the registered instance URL. Send them to the viewer, not to STAC JSON
	# (the harvester only ever requests /api/*).
	return RedirectResponse(url=settings.viewer_url())


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
		'conformsTo': [
			'https://api.stacspec.org/v1.0.0/core',
			'https://api.stacspec.org/v1.0.0/collections',
			'https://api.stacspec.org/v1.0.0/ogcapi-features',
			'http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core',
			'http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson',
			'http://www.opengis.net/spec/ogcapi-features-3/1.0/conf/filter',
			'http://www.opengis.net/spec/cql2/1.0/conf/cql2-text',
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
		# Accuracy matters here — this is not a Panoramax instance. It is
		# Hillview serving a Panoramax-compatible read API over the subset of
		# its photos whose owners chose the CC license. Note the OSM grant is
		# narrower than Panoramax's own CC-BY-SA-4.0 terms (which additionally
		# permit derived data under LO 2.0 / CC-BY 4.0 / ODbL 1.0); it is
		# spelled out rather than summarised so reviewers can judge it.
		'description': (
			'Hillview (https://hillview.cz) is a photo mapping application. This '
			'endpoint is not a Panoramax server: it is a Panoramax-compatible '
			'(GeoVisio STAC) read-only API over the Hillview photos whose owners '
			f'published them under {scope.license}. Photos remain hosted on '
			'Hillview. Owners additionally grant permission to use their photos as '
			'reference material for creating, improving or validating OpenStreetMap '
			'contributions (data so extracted enters OSM under ODbL); that grant '
			'does not authorise data extraction for other purposes or licenses. '
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
				{'seq_ids': ready_ids, 'scope_legal_rights': scope.legal_rights},
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
		{'rel': 'self', 'href': str(request.url), 'type': 'application/json'},
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
				{'seq_ids': [row[0]], 'scope_legal_rights': scope.legal_rights},
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
			'scope_legal_rights': scope.legal_rights,
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
		{'rel': 'self', 'href': str(request.url), 'type': 'application/geo+json'},
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
			'scope_legal_rights': scope.legal_rights,
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
