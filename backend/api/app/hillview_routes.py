import json
import os
import sys
import logging
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

from fastapi import APIRouter, Query, HTTPException, status, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, Float, case, literal, case, literal
from geoalchemy2.functions import ST_MakeEnvelope, ST_Within, ST_X, ST_Y

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import Photo, User
from common.utc import format_utc
from hidden_content_filters import apply_hidden_content_filters
from auth import get_current_user_optional_with_query
from rate_limiter import general_rate_limiter
from internal_guard import require_internal_ip

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

# Server-side caps
MAX_PHOTOS_PER_REQUEST = int(os.getenv("MAX_HILLVIEW_PHOTOS", "1000"))
MAX_PICKS_PER_REQUEST = int(os.getenv("MAX_HILLVIEW_PICKS", "200"))

from sqlalchemy import or_, and_

LEGAL_RIGHTS_TO_LICENSE = {
	'full1': 'arr',
	'ccbysa4': 'ccbysa4',
}

def legal_rights_to_license(legal_rights: Optional[str]) -> str:
	if not legal_rights:
		return 'arr'
	return LEGAL_RIGHTS_TO_LICENSE.get(legal_rights, legal_rights)

router = APIRouter(prefix="/api/hillview", tags=["hillview"])


class AnalysisFilters(BaseModel):
	"""Filters based on photo analysis data"""
	time_of_day: Optional[str] = None  # day, night, dawn_dusk
	location_type: Optional[str] = None  # indoors, outdoors, mixed
	min_farthest_distance: Optional[float] = None  # farthest object must be at least X meters away
	max_closest_distance: Optional[float] = None  # closest object must be at most X meters away
	min_scenic_score: Optional[int] = None  # 1-5, minimum scenic beauty score
	visibility_distance: Optional[str] = None  # near, medium, far, panoramic
	tallest_building: Optional[str] = None  # none, low_rise, mid_rise, high_rise, skyscraper
	features: Optional[List[str]] = None  # any of these features (OR logic)
	show_unanalyzed: bool = True  # include photos without analysis data


class SetAnalysisRequest(BaseModel):
	"""Request to set analysis data for a photo"""
	file_md5: Optional[str] = None  # identify by MD5 hash
	photo_id: Optional[str] = None  # identify by photo UID
	analysis: Dict[str, Any]  # the analysis data to set


def parse_analysis_filters(
	analysis_filters: str = Query(None, description="JSON object with analysis filters")
) -> Optional[AnalysisFilters]:
	if not analysis_filters or analysis_filters == 'null':
		return None
	try:
		return AnalysisFilters.model_validate_json(analysis_filters)
	except Exception as e:
		log.error(f"Invalid analysis_filters value: {analysis_filters!r} — error: {e}")
		raise HTTPException(status_code=400, detail=f"Invalid analysis_filters: {e}")


def _build_analysis_conditions(filters: AnalysisFilters) -> list:
	"""Build a list of SQLAlchemy conditions from analysis filter fields."""
	conditions = []

	if filters.time_of_day:
		conditions.append(Photo.analysis['time_of_day'].astext == filters.time_of_day)

	if filters.location_type:
		conditions.append(Photo.analysis['location_type'].astext == filters.location_type)

	if filters.min_farthest_distance is not None:
		conditions.append(
			Photo.analysis['farthest_object_distance'].astext.cast(Float) >= filters.min_farthest_distance
		)

	if filters.max_closest_distance is not None:
		conditions.append(
			Photo.analysis['closest_object_distance'].astext.cast(Float) <= filters.max_closest_distance
		)

	if filters.min_scenic_score is not None:
		conditions.append(
			Photo.analysis['scenic_score'].astext.cast(Float) >= filters.min_scenic_score
		)

	if filters.visibility_distance:
		conditions.append(Photo.analysis['visibility_distance'].astext == filters.visibility_distance)

	if filters.tallest_building:
		conditions.append(Photo.analysis['tallest_building'].astext == filters.tallest_building)

	if filters.features:
		# OR logic: any of the features matches
		feature_conditions = [Photo.analysis['features'].contains([f]) for f in filters.features]
		conditions.append(or_(*feature_conditions))

	return conditions


def apply_analysis_filters(query, filters: AnalysisFilters):
	"""Apply analysis-based filters to a photo query (WHERE-clause exclusion)."""
	conditions = _build_analysis_conditions(filters)

	if conditions:
		if filters.show_unanalyzed:
			query = query.where(or_(
				Photo.analysis.is_(None),
				and_(*conditions)
			))
		else:
			query = query.where(and_(*conditions))

	return query


def build_filter_expressions(filters: AnalysisFilters):
	"""Build SQL expressions for the filtered flag and 4-tier sort priority.

	Returns (filtered_expr, sort_priority_expr) or (None, None) when
	no filter conditions are active.

	Sort tiers: 0=featured, 1=passes filter, 2=unanalyzed, 3=filtered out.
	"""
	conditions = _build_analysis_conditions(filters)

	if not conditions and filters.show_unanalyzed:
		return None, None

	# "passes_filter" = all analysis conditions met (requires non-null analysis)
	passes_filter = and_(*conditions) if conditions else literal(True)

	if filters.show_unanalyzed:
		passes = or_(Photo.analysis.is_(None), passes_filter)
	else:
		passes = and_(Photo.analysis.isnot(None), passes_filter)

	filtered_expr = case((passes, False), else_=True).label('filtered')

	sort_priority_expr = case(
		(Photo.featured == True, literal(0)),
		(and_(Photo.analysis.isnot(None), passes_filter), literal(1)),
		(Photo.analysis.is_(None), literal(2)),
		else_=literal(3)
	).label('sort_priority')

	return filtered_expr, sort_priority_expr


def convert_photo_to_response(photo, username: str, longitude: float, latitude: float) -> Dict[str, Any]:
	"""Convert a Photo object to the response format"""
	photo_data = {
		'id': photo.id,
		'geometry': {
			'coordinates': [longitude, latitude]
		},
		'bearing': photo.compass_angle or 0,
		'computed_altitude': photo.altitude or 0,
		'captured_at': format_utc(photo.captured_at),
		'is_pano': False,
		'filename': photo.original_filename,
		'sizes': {},
		'creator': {
			'username': username,
			'id': photo.owner_id
		}
	}

	# Add sizes if available
	for k, v in (photo.sizes or {}).items():
		photo_data['sizes'][k] = {
			'url': v.get('url'),
			'width': v.get('width'),
			'height': v.get('height'),
			'pyramid': v.get('pyramid', None)
		}

	# Add file hash if available for deduplication
	if photo.file_md5:
		photo_data['file_md5'] = photo.file_md5

	if photo.featured:
		photo_data['featured'] = True

	if photo.description:
		photo_data['description'] = photo.description

	photo_data['license'] = legal_rights_to_license(photo.legal_rights)


	return photo_data


async def query_photos_in_bounds(
	db: AsyncSession,
	bbox,
	current_user_id: Optional[str],
	exclude_ids: Optional[List[str]] = None,
	limit: Optional[int] = None,
	analysis_filters: Optional[AnalysisFilters] = None
) -> List[Dict[str, Any]]:
	"""Query photos within bounds, with optional exclusions and limit.

	When analysis_filters are active, ALL photos are returned with a
	'filtered' flag on non-matching ones, ordered by:
	featured → passes filter → unanalyzed → filtered out.
	"""
	# Build filter expressions if filters are active
	filtered_expr, sort_priority_expr = (None, None)
	if analysis_filters:
		filtered_expr, sort_priority_expr = build_filter_expressions(analysis_filters)

	columns = [
		Photo,
		User.username,
		ST_X(Photo.geometry).label('longitude'),
		ST_Y(Photo.geometry).label('latitude')
	]
	if filtered_expr is not None:
		columns.extend([filtered_expr, sort_priority_expr])

	query = select(*columns).join(User, Photo.owner_id == User.id).where(
		Photo.geometry.isnot(None),
		ST_Within(Photo.geometry, bbox),
		Photo.is_public == True,
		Photo.processing_status == 'completed',
		Photo.deleted == False
	)

	if sort_priority_expr is not None:
		query = query.order_by(sort_priority_expr.asc(), Photo.captured_at.desc())
	else:
		query = query.order_by(Photo.featured.desc(), Photo.captured_at.desc())

	# Exclude specific photo IDs if provided
	if exclude_ids:
		query = query.where(Photo.id.notin_(exclude_ids))

	# Apply limit if specified
	if limit:
		query = query.limit(limit)

	# Apply hidden content filtering
	query = apply_hidden_content_filters(
		query,
		current_user_id,
		'hillview'
	)

	result = await db.execute(query)
	records = result.all()

	# Convert to response format
	photos = []
	if filtered_expr is not None:
		for photo, username, longitude, latitude, is_filtered, _sort_priority in records:
			photo_dict = convert_photo_to_response(photo, username, longitude, latitude)
			if is_filtered:
				photo_dict['filtered'] = True
			photos.append(photo_dict)
	else:
		for photo, username, longitude, latitude in records:
			photos.append(convert_photo_to_response(photo, username, longitude, latitude))

	return photos


async def query_picked_photos(
	db: AsyncSession,
	bbox,
	picked_ids: List[str],
	current_user_id: Optional[str]
) -> List[Dict[str, Any]]:
	"""Query specific picked photos that are within bounds"""
	if not picked_ids:
		return []

	query = select(
		Photo,
		User.username,
		ST_X(Photo.geometry).label('longitude'),
		ST_Y(Photo.geometry).label('latitude')
	).join(User, Photo.owner_id == User.id).where(
		Photo.geometry.isnot(None),
		Photo.id.in_(picked_ids),
		ST_Within(Photo.geometry, bbox),
		Photo.is_public == True,
		Photo.deleted == False
	)

	# Apply hidden content filtering
	query = apply_hidden_content_filters(
		query,
		current_user_id,
		'hillview'
	)

	result = await db.execute(query)
	records = result.all()

	# Convert to response format
	photos = []
	for photo, username, longitude, latitude in records:
		photos.append(convert_photo_to_response(photo, username, longitude, latitude))

	return photos


@router.get("")
async def get_hillview_images(
	request: Request,
	top_left_lat: float = Query(..., description="Top left latitude"),
	top_left_lon: float = Query(..., description="Top left longitude"),
	bottom_right_lat: float = Query(..., description="Bottom right latitude"),
	bottom_right_lon: float = Query(..., description="Bottom right longitude"),
	client_id: str = Query(..., description="Client ID"),
	picks: str = Query(None, description="Comma-separated list of picked photo IDs"),
	max_photos: int = Query(400, description="Maximum number of photos to return", ge=1),
	analysis_filters: Optional[AnalysisFilters] = Depends(parse_analysis_filters),
	db: AsyncSession = Depends(get_db),
	current_user: Optional[User] = Depends(get_current_user_optional_with_query)
):
	"""Get Hillview images from database filtered by bounding box area"""
	# Apply rate limiting with optional user context (better limits for authenticated users)
	await general_rate_limiter.enforce_rate_limit(request, 'public_read', current_user)

	# Cap max_photos at server limit
	effective_max_photos = min(max_photos, MAX_PHOTOS_PER_REQUEST)

	try:
		# Parse picks parameter if provided, capped at server limit
		picked_ids = []
		if picks:
			picked_ids = [id.strip() for id in picks.split(',') if id.strip()][:MAX_PICKS_PER_REQUEST]
			log.debug(f"Processing picks: {picked_ids}")

		# Create bounding box geometry (min_lng, min_lat, max_lng, max_lat, srid)
		bbox = ST_MakeEnvelope(top_left_lon, bottom_right_lat, bottom_right_lon, top_left_lat, 4326)

		log.debug(f"Querying photos from database for bbox: {top_left_lat}, {top_left_lon}, {bottom_right_lat}, {bottom_right_lon}")
		log.info(f"Hillview endpoint - current_user: {current_user.username if current_user else 'None'} (ID: {current_user.id if current_user else 'None'})")

		current_user_id = current_user.id if current_user else None

		# Get picked photos first (they have priority)
		picked_photos = await query_picked_photos(db, bbox, picked_ids, current_user_id)
		log.info(f"Found {len(picked_photos)} picked photos in bounds")

		# Get regular photos up to the limit minus picked photos
		remaining_limit = effective_max_photos - len(picked_photos)
		regular_photos = []
		if remaining_limit > 0:
			regular_photos = await query_photos_in_bounds(
				db, bbox, current_user_id,
				exclude_ids=picked_ids,
				limit=remaining_limit,
				analysis_filters=analysis_filters
			)
			log.info(f"Found {len(regular_photos)} regular photos")

		# Combine picked photos first, then regular photos
		filtered_photos = picked_photos + regular_photos
		log.info(f"Found {len(filtered_photos)} total photos in database for bbox (requested: {max_photos}, effective: {effective_max_photos}, picks cap: {MAX_PICKS_PER_REQUEST})")

		# Create generator for EventSource streaming
		async def generate_stream():
			try:
				# Send the data as a single event with proper type field
				data = {
					'type': 'photos',
					'photos': filtered_photos,
					'total_count': len(filtered_photos),
					'hasNext': False,  # Hillview returns all photos in one batch
					'bbox': {
						'top_left_lat': top_left_lat,
						'top_left_lon': top_left_lon,
						'bottom_right_lat': bottom_right_lat,
						'bottom_right_lon': bottom_right_lon
					}
				}
				yield f"data: {json.dumps(data)}\n\n"

				# Send completion event to match Mapillary behavior
				yield f"data: {json.dumps({'type': 'stream_complete', 'total_live_photos': 0, 'total_cached_photos': len(filtered_photos), 'total_all_photos': len(filtered_photos)})}\n\n"

			except Exception as e:
				log.error(f"Stream error in hillview endpoint: {str(e)}")
				yield f"data: {json.dumps({'type': 'error', 'message': f'Stream error: {str(e)}'})}\n\n"

		# Return EventSource streaming response
		return StreamingResponse(
			generate_stream(),
			media_type="text/event-stream",
			headers={
				"Cache-Control": "no-cache, no-store, must-revalidate",
				"Connection": "keep-alive",
				"Access-Control-Allow-Origin": "*",
				"Access-Control-Allow-Headers": "Cache-Control, Content-Type, Authorization",
				"Access-Control-Allow-Methods": "GET, OPTIONS",
				"Access-Control-Expose-Headers": "*",
				"X-Accel-Buffering": "no",  # Disable nginx buffering
				"Content-Type": "text/event-stream; charset=utf-8"
			}
		)

	except Exception as e:
		log.error(f"Error querying photos from database: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Database error: {str(e)}"
		)


@router.post("/internal/set-analysis", dependencies=[Depends(require_internal_ip)])
async def set_photo_analysis(
	request: SetAnalysisRequest,
	db: AsyncSession = Depends(get_db)
):
	"""Internal endpoint to set analysis data for a photo by MD5 or photo ID"""
	if not request.file_md5 and not request.photo_id:
		raise HTTPException(status_code=400, detail="Must provide either file_md5 or photo_id")

	# Build query to find the photo
	if request.photo_id:
		query = select(Photo).where(Photo.id == request.photo_id)
	else:
		query = select(Photo).where(Photo.file_md5 == request.file_md5)

	result = await db.execute(query)
	photos = result.scalars().all()

	if not photos:
		raise HTTPException(status_code=404, detail="Photo not found")

	if len(photos) > 1:
		raise HTTPException(
			status_code=409,
			detail=f"Multiple photos ({len(photos)}) found for MD5 {request.file_md5}"
		)

	photo = photos[0]

	# Update the analysis field
	photo.analysis = request.analysis
	await db.commit()

	return {"status": "ok", "photo_id": photo.id}
