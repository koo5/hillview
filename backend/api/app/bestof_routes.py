"""Best-of routes – photos ranked by a composite score."""
import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from geoalchemy2.functions import ST_X, ST_Y

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import Photo, PhotoAnnotation, PhotoRating, PhotoRatingType, SiteState, User
from hillview_routes import legal_rights_to_license
from common.utc import format_utc
from auth import get_current_user_optional_ssr
from hidden_content_filters import apply_hidden_content_filters
from rate_limiter import general_rate_limiter
from annotation_routes import effective_annotation_count_subquery, effective_annotation_conditions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bestof", tags=["bestof"])

# Size of a ?page=N slice. Deliberately owned here rather than by the caller:
# the page size and the step between pages are the same number, and if the two
# ever diverge the failure is silent — a step under the size repeats photos
# across pages, a step over it leaves photos that NO page lists, unreachable by
# any crawler. One constant, one expression (page_offset), no way to desync.
BESTOF_PAGE_SIZE = 40


def page_offset(page: Optional[int]) -> int:
	"""Row offset of page N (1-based). Junk and out-of-range mean page 1."""
	if not page or page < 1:
		return 0
	return (int(page) - 1) * BESTOF_PAGE_SIZE


def ranking_terms():
	"""The score's building blocks: (thumbs_up_sub, annotation_sub, score_raw).

	Shared by the listing and the sitemap fingerprint so "the ranking" has one
	definition. score_raw is kept unlabelled: a SELECT alias can't be referenced
	from WHERE, so the filter and the cursor comparison use the raw expression.
	"""
	# Subquery: thumbs-up count per photo
	thumbs_up_sub = (
		select(
			PhotoRating.photo_id,
			func.count(PhotoRating.id).label('thumbs_up_count')
		)
		.where(
			and_(
				PhotoRating.photo_source == 'hillview',
				PhotoRating.rating == PhotoRatingType.THUMBS_UP
			)
		)
		.group_by(PhotoRating.photo_id)
		.subquery('thumbs_up_sub')
	)

	# Subquery: effective annotation count (from annotation controller)
	annotation_sub = effective_annotation_count_subquery()

	# Resolution bonus: floor(max(0, width - 10000) / 1000)
	resolution_bonus = func.floor(
		func.greatest(0, func.coalesce(Photo.width, 0) - 10000) / 10000
	)

	score_raw = (
		func.coalesce(thumbs_up_sub.c.thumbs_up_count, 0)
		+ func.coalesce(annotation_sub.c.annotation_count, 0)
		+ resolution_bonus
	)
	return thumbs_up_sub, annotation_sub, score_raw


def ranked(query, thumbs_up_sub, annotation_sub, score_raw):
	"""Join the score onto a Photo select, keep the ranked set, order it."""
	return (
		query
		.outerjoin(thumbs_up_sub, Photo.id == thumbs_up_sub.c.photo_id)
		.outerjoin(annotation_sub, Photo.id == annotation_sub.c.photo_id)
		.where(Photo.deleted == False)
		# A photo earns its place here — one like, one annotation, or being a
		# large panorama is enough, but zero is not. Without this the "best of"
		# was the whole collection: on a 52k-photo dump 98% scored zero and
		# sorted by nothing but id, so the ranking ran out of meaning after a
		# few hundred rows and the tail was thin content (a camera filename and
		# a thumbnail) that dilutes crawl budget. It also keeps the listing
		# bounded — the page's own empty state already promises this reading:
		# "Photos will appear here as they receive ratings and annotations".
		.where(score_raw > 0)
		.order_by(score_raw.desc(), Photo.id.desc())
	)


BESTOF_STATE_KEY = 'bestof_page1'


@router.get("/lastmod")
async def get_bestof_lastmod(db: AsyncSession = Depends(get_db)):
	"""When /bestof (page 1, as a crawler sees it) last changed — the sitemap's <lastmod>.

	The ranking's inputs are not all timestamped (a rating removal is a hard
	delete, a soft-delete a bare flag), and the ones that are would over-fire on
	changes deep in the list. So this fingerprints the OUTPUT instead: the
	ordered (id, score, content_updated_at) of page 1 — id+score is the
	ranking, content_updated_at is the card's text (title, place, annotation
	labels all bump it, see migration 034) — hashed and compared with the
	stored one in site_state. A differing hash is written together with now();
	an equal one leaves the row alone, so its updated_at is "the last time this
	page looked different". No auth, no hidden-content filter: the anonymous
	view is the crawler's view.

	A read that may write, deliberately: the value is only ever needed by
	whoever fetches the sitemap, so computing it then (and not on a timer)
	costs one page-1 query per sitemap fetch and no scheduler. Two concurrent
	fetches race harmlessly — the upsert's WHERE makes the second a no-op.
	"""
	thumbs_up_sub, annotation_sub, score_raw = ranking_terms()
	rows = (await db.execute(
		ranked(select(Photo.id, score_raw, Photo.content_updated_at), thumbs_up_sub, annotation_sub, score_raw)
		.limit(BESTOF_PAGE_SIZE)
	)).all()
	digest = hashlib.sha256(
		"\n".join(f"{pid}:{int(score)}:{format_utc(ts) or ''}" for pid, score, ts in rows).encode()
	).hexdigest()

	stmt = pg_insert(SiteState).values(key=BESTOF_STATE_KEY, value={"hash": digest})
	stmt = stmt.on_conflict_do_update(
		index_elements=[SiteState.key],
		set_={"value": stmt.excluded.value, "updated_at": func.now()},
		where=SiteState.value['hash'].astext.is_distinct_from(stmt.excluded.value['hash'].astext),
	)
	await db.execute(stmt)
	await db.commit()
	updated_at = await db.scalar(select(SiteState.updated_at).where(SiteState.key == BESTOF_STATE_KEY))
	return {"lastmod": format_utc(updated_at)}


@router.get("/photos")
async def get_best_photos(
	request: Request,
	limit: int = 20,
	# Deprecated: /bestof pages by ?page= only — one coordinate system, which is
	# also the one a crawler walks. Kept accepted so a deployed older frontend
	# keeps working through a rollout; delete once none are left.
	cursor: Optional[str] = None,
	page: Optional[int] = None,
	db: AsyncSession = Depends(get_db),
	current_user: Optional[User] = Depends(get_current_user_optional_ssr)
):
	"""Get photos ranked by score (likes + annotations + resolution bonus)."""
	await general_rate_limiter.enforce_rate_limit(request, 'public_read', current_user)

	try:
		thumbs_up_sub, annotation_sub, score_raw = ranking_terms()
		score_expr = score_raw.label('score')
		annotation_count_expr = func.coalesce(annotation_sub.c.annotation_count, 0).label('annotation_count')

		query = ranked(
			select(
				Photo,
				User.username,
				ST_Y(Photo.geometry).label('latitude'),
				ST_X(Photo.geometry).label('longitude'),
				score_expr,
				annotation_count_expr
			).join(User, Photo.owner_id == User.id),
			thumbs_up_sub, annotation_sub, score_raw,
		)

		# Cursor-based pagination: cursor format is "score:photo_id"
		if cursor:
			try:
				parts = cursor.split(':', 1)
				cursor_score = int(parts[0])
				cursor_id = parts[1]
				query = query.where(
					or_(
						score_raw < cursor_score,
						and_(score_raw == cursor_score, Photo.id < cursor_id)
					)
				)
			except (ValueError, IndexError) as e:
				logger.warning(f"Invalid cursor format: {cursor}, error: {e}")
				raise HTTPException(
					status_code=status.HTTP_400_BAD_REQUEST,
					detail="Invalid cursor format"
				)

		# ?page= is the ENTRY POINT — the server-rendered, crawlable, shareable
		# address of a position in the ranking, and it fixes its own batch size.
		# The cursor is the CONTINUATION from wherever you entered: every response
		# hands back a next_cursor, so the lazy-loader walks on from a paged batch
		# exactly as it would from the first one. They never combine (a cursor
		# already encodes a position), so cursor wins if both arrive.
		paged = page is not None and not cursor
		if paged:
			limit = BESTOF_PAGE_SIZE
			query = query.offset(page_offset(page))

		query = query.limit(limit + 1)

		# Apply hidden content filtering
		query = apply_hidden_content_filters(
			query,
			current_user.id if current_user else None,
			'hillview'
		)

		result = await db.execute(query)
		photo_results = result.all()

		has_more = len(photo_results) > limit
		if has_more:
			photo_results = photo_results[:-1]

		# Effective annotation bodies for this page of photos. The labels ARE
		# the page's content — /bestof is the index of views, and each entry's
		# summary line ("Chrám svaté Barbory, GASK, …") is what both readers
		# and crawlers come for; a bare count carries none of it.
		page_ids = [row[0].id for row in photo_results]
		bodies_by_photo: dict = {}
		if page_ids:
			ann_result = await db.execute(
				select(PhotoAnnotation.photo_id, PhotoAnnotation.body)
				.where(and_(PhotoAnnotation.photo_id.in_(page_ids), effective_annotation_conditions()))
				.order_by(PhotoAnnotation.created_at)
			)
			for pid, body in ann_result.all():
				bodies_by_photo.setdefault(pid, []).append(body)

		photos_data = []
		next_cursor = None

		for photo, username, latitude, longitude, score, annotation_count in photo_results:
			score_int = int(score) if score else 0
			photos_data.append({
				"id": photo.id,
				"original_filename": photo.original_filename,
				"title": photo.title,
				"description": photo.description,
				# Reverse-geocoded label (backfill_places.py). displayTitle falls back
				# to it so a card headline — which is also the anchor text of the link
				# to /photo/<uid> — reads "Sedlec, Kutná Hora" and not a camera filename.
				"place_name": photo.place_name,
				"uploaded_at": format_utc(photo.uploaded_at),
				"captured_at": format_utc(photo.captured_at),
				"processing_status": photo.processing_status,
				"latitude": latitude,
				"longitude": longitude,
				"bearing": photo.compass_angle,
				"width": photo.width,
				"height": photo.height,
				"sizes": photo.sizes,
				"owner_username": username,
				"owner_id": photo.owner_id,
				"score": score_int,
				"annotation_count": int(annotation_count) if annotation_count else 0,
				"annotations": bodies_by_photo.get(photo.id, []),
				"license": legal_rights_to_license(photo.legal_rights)
			})
			next_cursor = f"{score_int}:{photo.id}"

		return {
			"photos": photos_data,
			"has_more": has_more,
			"next_cursor": next_cursor if has_more else None,
			# Echoed so a caller never has to know or derive the slice size.
			"page": max(1, page) if paged else None,
			"page_size": limit,
			# Who this batch was filtered for — null when anonymous. See the same
			# field on /activity/recent for why it is an id and not a boolean.
			"viewer_id": current_user.id if current_user else None,
		}

	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"Error getting best-of photos: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to get best-of photos"
		)
