"""Short share links – mint /shared/{slug} redirects when a user clicks share.

POST /api/shared mints (or returns the existing) short link for a photo + view
state. The map target path is constructed server-side, mirroring the frontend's
constructMapUrl() param order, so a client can never store an arbitrary redirect.
The target is the row's identity (unique column, upserted on conflict). The slug
is derived, never stored: "{id}-{title-slug}", with the title part recomputed
from the photo's current title at each mint — improved titles carry into new
shares — and ignored on resolution, which uses only the leading id, so
tail-truncated links still resolve.
GET /api/shared/{slug} resolves a slug to its target and counts the visit; the
web frontend's /shared/[slug] route uses it to issue the actual 301.
"""
import logging
import os
import re
import sys
import unicodedata
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from geoalchemy2.functions import ST_X, ST_Y

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import Photo, ShareLink, User
from auth import get_current_user_optional
from rate_limiter import general_rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shared", tags=["shared"])

# Source-prefixed photo uid, e.g. hillview-<uuid> or mapillary-<numeric id>
PHOTO_UID_RE = re.compile(r'^[A-Za-z0-9._~-]{3,200}$')
# The slug's only load-bearing part is the leading row id
SLUG_ID_RE = re.compile(r'^(\d{1,12})(?:-|$)')
SLUG_BASE_MAX_LEN = 80
SLUG_BASE_FALLBACK = 'photo'


class ZoomViewBounds(BaseModel):
	x1: float = Field(ge=-1000, le=1000)
	y1: float = Field(ge=-1000, le=1000)
	x2: float = Field(ge=-1000, le=1000)
	y2: float = Field(ge=-1000, le=1000)


class MintRequest(BaseModel):
	photo_uid: str = Field(max_length=200)
	zoom: Optional[float] = Field(default=None, ge=1, le=22)
	# Used only for non-hillview sources; hillview coordinates come from the DB
	lat: Optional[float] = Field(default=None, ge=-90, le=90)
	lon: Optional[float] = Field(default=None, ge=-180, le=180)
	bearing: Optional[float] = Field(default=None, ge=0, lt=360)
	zoom_view_bounds: Optional[ZoomViewBounds] = None


def _fmt(value: float) -> str:
	"""Format a float the way JS template literals do: no trailing zeros, no trailing dot."""
	return f"{value:.6f}".rstrip('0').rstrip('.')


def slugify(text_value: str) -> str:
	"""ASCII-fold and kebab-case a photo title for use as a slug's decorative part."""
	folded = unicodedata.normalize('NFKD', text_value).encode('ascii', 'ignore').decode('ascii')
	kebab = re.sub(r'[^a-z0-9]+', '-', folded.lower()).strip('-')
	return kebab[:SLUG_BASE_MAX_LEN].rstrip('-')


def _construct_target(lat: float, lon: float, zoom: float, bearing: Optional[float],
                      photo_uid: str, bounds: Optional[ZoomViewBounds]) -> str:
	"""Mirror of the frontend's constructMapUrl(): same params, same order."""
	target = f"/?lat={_fmt(lat)}&lon={_fmt(lon)}&zoom={_fmt(zoom)}"
	if bearing is not None:
		target += f"&bearing={_fmt(bearing)}"
	target += f"&photo={quote(photo_uid, safe='')}"
	if bounds is not None:
		target += f"&x1={bounds.x1:.6f}&y1={bounds.y1:.6f}&x2={bounds.x2:.6f}&y2={bounds.y2:.6f}"
	return target


@router.post("")
async def mint_share_link(
	body: MintRequest,
	request: Request,
	user: Optional[User] = Depends(get_current_user_optional),
	db: AsyncSession = Depends(get_db),
):
	"""Mint a short share link for a photo + view state (anonymous allowed, per-IP limited).

	Idempotent per constructed target: sharing the same view again returns the
	existing row's id, with the slug's title part rebuilt from the current title.
	"""
	await general_rate_limiter.enforce_rate_limit(request, 'share_mint')

	if not PHOTO_UID_RE.match(body.photo_uid):
		raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid photo_uid")

	dash = body.photo_uid.find('-')
	if dash <= 0 or dash == len(body.photo_uid) - 1:
		raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid photo_uid")
	source, source_id = body.photo_uid[:dash], body.photo_uid[dash + 1:]

	title: Optional[str] = None
	photo_id: Optional[str] = None
	lat, lon, bearing = body.lat, body.lon, body.bearing

	if source == 'hillview':
		# Authoritative data from the DB; only public photos get share links so a
		# private photo's title can never leak into a public slug.
		result = await db.execute(
			select(Photo.id, Photo.title, Photo.compass_angle,
			       ST_Y(Photo.geometry).label('lat'), ST_X(Photo.geometry).label('lon'))
			.where(Photo.id == source_id, Photo.deleted == False, Photo.is_public == True)
		)
		row = result.first()
		if not row:
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")
		photo_id = row.id
		title = row.title
		if row.lat is not None and row.lon is not None:
			lat, lon = row.lat, row.lon
		if row.compass_angle is not None:
			bearing = row.compass_angle % 360

	if lat is None or lon is None:
		raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Photo has no coordinates")

	zoom = body.zoom if body.zoom is not None else 18
	target = _construct_target(lat, lon, zoom, bearing, body.photo_uid, body.zoom_view_bounds)
	slug_base = (slugify(title) if title else '') or SLUG_BASE_FALLBACK

	# Race-free idempotent mint: the no-op DO UPDATE makes RETURNING yield the
	# existing row's id on conflict (plain DO NOTHING returns nothing).
	ins = pg_insert(ShareLink).values(
		target=target,
		photo_uid=body.photo_uid,
		photo_id=photo_id,
		created_by=user.id if user else None,
	)
	stmt = (
		ins.on_conflict_do_update(index_elements=['target'], set_={'target': ins.excluded.target})
		.returning(ShareLink.id)
	)
	link_id = (await db.execute(stmt)).scalar_one()
	await db.commit()

	return {"slug": f"{link_id}-{slug_base}", "target": target}


@router.get("/{slug}")
async def resolve_share_link(
	slug: str,
	request: Request,
	db: AsyncSession = Depends(get_db),
):
	"""Resolve a slug to its target path and count the visit."""
	await general_rate_limiter.enforce_rate_limit(request, 'public_read')

	match = SLUG_ID_RE.match(slug)
	if not match:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")
	link_id = int(match.group(1))

	result = await db.execute(
		update(ShareLink)
		.where(ShareLink.id == link_id)
		.values(visit_count=ShareLink.visit_count + 1)
		.returning(ShareLink.target)
	)
	target = result.scalar_one_or_none()
	await db.commit()
	if target is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")

	return {"target": target}
