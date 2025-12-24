import asyncio
import datetime
import json
import os
from typing import Optional, Dict, Any
import logging
from fastapi import APIRouter, Query, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
from asyncio import Lock, Queue
import time
import math
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db, SessionLocal
from common.models import CachedRegion, MapillaryPhotoCache, User
from cache_service import MapillaryCacheService
from rate_limiter import rate_limit_public_read, general_rate_limiter
from auth import get_current_user_optional_with_query
from hidden_content_filters import filter_mapillary_photos_list
from mock_mapillary import mock_mapillary_service
from debug_utils import debug_only, safe_str_id

log = logging.getLogger(__name__)

# Lazy load token to avoid crash on import
TOKEN = None
url = "https://graph.mapillary.com/images"

class TokenBucketRateLimiter:
	"""Token bucket rate limiter for API calls"""

	def __init__(self, max_tokens: int, refill_period: float, refill_amount: int = 1):
		self.max_tokens = max_tokens
		self.tokens = max_tokens
		self.refill_period = refill_period
		self.refill_amount = refill_amount
		self.last_refill = time.time()
		self.lock = Lock()

	async def acquire(self, tokens_needed: int = 1) -> bool:
		"""Acquire tokens from the bucket. Returns True if successful."""
		async with self.lock:
			now = time.time()

			# Refill tokens based on time elapsed
			if now > self.last_refill:
				time_passed = now - self.last_refill
				tokens_to_add = int(time_passed / self.refill_period) * self.refill_amount
				self.tokens = min(self.max_tokens, self.tokens + tokens_to_add)
				self.last_refill = now

			# Check if we have enough tokens
			if self.tokens >= tokens_needed:
				self.tokens -= tokens_needed
				return True
			return False

	async def wait_for_tokens(self, tokens_needed: int = 1):
		"""Wait until tokens are available"""
		while not await self.acquire(tokens_needed):
			await asyncio.sleep(0.1)  # Check every 100ms

class MapillaryAPIManager:
	"""Manages Mapillary API connections with rate limiting and connection pooling"""

	def __init__(self):
		# Rate limiter: 10 requests per second max, with burst capacity of 20
		self.rate_limiter = TokenBucketRateLimiter(max_tokens=20, refill_period=0.1, refill_amount=1)

		# HTTP client with connection pooling
		self.client = httpx.AsyncClient(
			limits=httpx.Limits(
				max_keepalive_connections=10,
				max_connections=20,
				keepalive_expiry=30
			),
			timeout=httpx.Timeout(300.0),  # 5 minutes
			http2=True
		)

		# Request queue for backpressure
		self.request_queue: Queue = Queue(maxsize=100)
		self.queue_worker_running = False
		self.stats = {
			'total_requests': 0,
			'successful_requests': 0,
			'failed_requests': 0,
			'rate_limited_requests': 0,
			'retry_attempts': 0
		}

	async def start_queue_worker(self):
		"""Start the background queue worker if not already running"""
		if not self.queue_worker_running:
			self.queue_worker_running = True
			asyncio.create_task(self._queue_worker())

	async def _queue_worker(self):
		"""Background worker to process queued requests"""
		while self.queue_worker_running:
			try:
				await asyncio.sleep(0.01)  # Small delay to prevent busy waiting
			except Exception as e:
				log.error(f"Queue worker error: {e}")


	async def make_request(self, params: Dict[str, Any], max_retries: int = 10) -> Dict[str, Any]:
		"""Make a rate-limited request to Mapillary API with retries"""
		self.stats['total_requests'] += 1

		for attempt in range(1 + max_retries):
			try:
				# Wait for rate limit
				await self.rate_limiter.wait_for_tokens(1)

				url_with_params = f"{url}?{'&'.join(f'{k}={v}' for k,v in params.items())}"
				#log.info(f"Making Mapillary API call (attempt {attempt + 1}/{max_retries + 1}): {url} with params {(params | {'access_token': 'xxx'})}")
				log.info(f"Making Mapillary API call (attempt {attempt + 1}/{max_retries + 1}): {url_with_params}")

				#raise Exception('tests should not cause real mapillary api calls')
				response = await self.client.get(url, params=params)

				# Handle rate limiting
				if response.status_code == 429:
					self.stats['rate_limited_requests'] += 1
					retry_after = int(response.headers.get('Retry-After', 60))
					log.warning(f"Rate limited by Mapillary API, waiting {retry_after} seconds")
					await asyncio.sleep(retry_after)
					continue

				# Handle other HTTP errors
				response.raise_for_status()

				result = response.json()
				self.stats['successful_requests'] += 1
				log.info(f"Mapillary API returned {len(result.get('data', []))} photos")
				return result

			except httpx.TimeoutException as e:
				log.error(f"Mapillary API request timed out (attempt {attempt + 1}): {e}")
				if attempt < max_retries:
					self.stats['retry_attempts'] += 1
					await asyncio.sleep(min(2 ** attempt, 15))  # Exponential backoff
					continue

			except httpx.HTTPStatusError as e:
				log.error(f"Mapillary API HTTP error {e.response.status_code} during attempt {attempt + 1}: {e}")
				if e.response.status_code >= 500 and attempt < max_retries:
					# Retry on server errors
					self.stats['retry_attempts'] += 1
					await asyncio.sleep(min(2 ** (attempt+1), 10))
					continue
				break  # Don't retry on client errors (4xx)

			except Exception as e:
				log.error(f"Unexpected error in Mapillary API call (attempt {attempt + 1}): {e}")
				if attempt < max_retries:
					self.stats['retry_attempts'] += 1
					await asyncio.sleep(min(2 ** attempt, 30))
					continue
				break

		# All retries failed
		self.stats['failed_requests'] += 1
		return {"error": "Failed to fetch data from Mapillary API after retries"}


	def get_stats(self) -> Dict[str, Any]:
		"""Get API usage statistics"""
		return {
			**self.stats,
			'success_rate': (self.stats['successful_requests'] / max(1, self.stats['total_requests'])) * 100,
			'current_tokens': self.rate_limiter.tokens,
			'max_tokens': self.rate_limiter.max_tokens
		}

	async def close(self):
		"""Close the HTTP client and cleanup"""
		self.queue_worker_running = False
		await self.client.aclose()

# Global API manager instance
api_manager = MapillaryAPIManager()

# Initialize the API manager
async def init_mapillary_api():
	"""Initialize the Mapillary API manager"""
	await api_manager.start_queue_worker()
	log.info("Mapillary API manager initialized with rate limiting and connection pooling")

def get_mapillary_token():
	global TOKEN
	if TOKEN is None:
		token_file = os.environ.get('MAPILLARY_CLIENT_TOKEN_FILE')
		if not token_file:
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail="MAPILLARY_CLIENT_TOKEN_FILE environment variable not set"
			)
		try:
			TOKEN = open(os.path.expanduser(token_file)).read().strip()
		except Exception as e:
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail=f"Failed to read Mapillary token file: {str(e)}"
			)
	return TOKEN

# Configuration
ENABLE_MAPILLARY_CACHE = os.getenv("ENABLE_MAPILLARY_CACHE", "false").lower() in ("true", "1", "yes")
ENABLE_MAPILLARY_LIVE = os.getenv("ENABLE_MAPILLARY_LIVE", "false").lower() in ("true", "1", "yes")
MAX_PHOTOS_PER_REQUEST = int(os.getenv("MAX_MAPILLARY_PHOTOS", "1000"))

clients = {}

router = APIRouter(prefix="/api/mapillary", tags=["mapillary"])

async def fetch_mapillary_data(
	top_left_lat: float,
	top_left_lon: float,
	bottom_right_lat: float,
	bottom_right_lon: float,
	limit: int
) -> Dict[str, Any]:
	"""Fetch data from Mapillary API"""

	# Check for mock data first
	if mock_mapillary_service.has_mock_data():
		log.info(f"Using mock Mapillary data instead of real API (limit: {limit})")
		bbox_coords = [top_left_lon, bottom_right_lat, bottom_right_lon, top_left_lat]  # [west, south, east, north]
		return mock_mapillary_service.filter_by_bbox(bbox_coords, limit=limit)

	params = {
		"limit": limit,
		"bbox": ",".join(map(str, [round(top_left_lon, 7), round(bottom_right_lat,7), round(bottom_right_lon,7), round(top_left_lat,7)])),
		"fields": "id,geometry,compass_angle,thumb_1024_url,computed_rotation,computed_compass_angle,computed_altitude,captured_at,is_pano,creator",
		"access_token": get_mapillary_token(),
	}

	return await api_manager.make_request(params)


@router.get("")
async def stream_mapillary_images(
	request: Request,
	top_left_lat: float = Query(..., description="Top left latitude"),
	top_left_lon: float = Query(..., description="Top left longitude"),
	bottom_right_lat: float = Query(..., description="Bottom right latitude"),
	bottom_right_lon: float = Query(..., description="Bottom right longitude"),
	client_id: str = Query(..., description="Client ID"),
	max_photos: int = Query(MAX_PHOTOS_PER_REQUEST, description="Maximum photos to return (capped by server limit)", ge=1),
	db: AsyncSession = Depends(get_db),
	current_user: Optional[User] = Depends(get_current_user_optional_with_query)
):
	"""Stream Mapillary images with Server-Sent Events"""
	# Apply rate limiting with optional user context (better limits for authenticated users)
	await general_rate_limiter.enforce_rate_limit(request, 'public_read', current_user)

	# Calculate effective maximum photos (client can't exceed server limit)
	effective_max_photos = min(max_photos, MAX_PHOTOS_PER_REQUEST)

	log.info(f"""EventSource connection initiated by client "{client_id}" for bbox: ({top_left_lat}, {top_left_lon}) to ({bottom_right_lat}, {bottom_right_lon})""")
	log.info(f"User authentication status: {current_user.username if current_user else 'Anonymous'} (ID: {current_user.id if current_user else 'None'})")
	log.info(f"Photo limits: client requested {max_photos}, server limit {MAX_PHOTOS_PER_REQUEST}, effective limit {effective_max_photos}")

	# check bounds sanity
	if top_left_lon == 180:
		top_left_lon = -180
	if bottom_right_lon == 180:
		bottom_right_lon = -180

	async def generate_stream(db_session: AsyncSession, user: Optional[User] = None):
		request_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S.%f")
		log.info(f"Stream generator started for request {request_id} from client {client_id} (cache_enabled={ENABLE_MAPILLARY_CACHE}, live_enabled={ENABLE_MAPILLARY_LIVE})")

		# Check if any Mapillary functionality is enabled
		if not ENABLE_MAPILLARY_CACHE and not ENABLE_MAPILLARY_LIVE:
			log.info(f"Mapillary functionality disabled - both cache and live API are disabled")
			yield f"data: {json.dumps({'type': 'photos', 'photos': []})}\n\n"
			yield f"data: {json.dumps({'type': 'stream_complete', 'total_live_photos': 0, 'total_cached_photos': 0, 'total_all_photos': 0})}\n\n"
			return

		if top_left_lat == bottom_right_lat or top_left_lon == bottom_right_lon:
			yield f"data: {json.dumps({'type': 'photos', 'photos': []})}\n\n"
			yield f"data: {json.dumps({'type': 'stream_complete', 'total_live_photos': 0, 'total_cached_photos': 0, 'total_all_photos': 0})}\n\n"
			return
		for l in [top_left_lat, bottom_right_lat]:
			if l < -90 or l > 90:
				raise HTTPException(
					status_code=status.HTTP_400_BAD_REQUEST,
					detail="Invalid latitude value"
				)
		for l in [top_left_lon, bottom_right_lon]:
			if l < -180 or l >= 180:
				raise HTTPException(
					status_code=status.HTTP_400_BAD_REQUEST,
					detail="Invalid longitude value"
				)

		# Track all photos (cached + live) to avoid memory issues
		total_photo_count = 0
		cached_photo_count = 0

		# Track streamed photo IDs to prevent duplicates between cache and live sections
		streamed_photo_ids = set()

		event = {
			'bbox': [top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon],
			'client_id': client_id,
			'request_id': request_id,
			'user_id': user.id if user else None,
			'inputs': [],

		}

		try:
			if ENABLE_MAPILLARY_CACHE or ENABLE_MAPILLARY_LIVE:

				cache_service = MapillaryCacheService(db_session)

				if ENABLE_MAPILLARY_CACHE:

					# Send initial response with cached data using spatial sampling
					cache_result = await cache_service.get_cached_photos_in_bbox(
						top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon,
						max_photos=effective_max_photos,
						current_user_id=user.id if user else None
					)

					cached_photos = cache_result['photos']
					is_complete_coverage = cache_result['is_complete_coverage']
					distribution_score = cache_result['distribution_score']

					cache_ignored_due_to_distribution = False

				else:
					is_complete_coverage = False
					distribution_score = 0.0
					cache_ignored_due_to_distribution = True
					cached_photos = []

				if cached_photos:
					log.info(f"Cache hit: Found {len(cached_photos)} cached photos for bbox (complete_coverage={is_complete_coverage})")

					# if is_complete_coverage:
					# 	# Complete coverage - use cache regardless of distribution
					# 	log.info(f"Using cached photos from COMPLETE region coverage (distribution check skipped)")
					# else:
					# 	# Incomplete coverage - check distribution
					# 	min_distribution_threshold = 0.9
					#
					# 	if distribution_score < min_distribution_threshold:
					# 		log.info(f"Cached photos poorly distributed (score: {distribution_score:.2%} < {min_distribution_threshold:.2%}), ignoring cache and using live API")
					# 		cache_ignored_due_to_distribution = True
					# 		cached_photo_count = 0
					# 		yield f"data: {json.dumps({'type': 'photos', 'photos': [], 'hasNext': True})}\n\n"
					# 	else:
					# 		log.info(f"Cached photos well distributed (score: {distribution_score:.2%}), using cache")

					# If we're using cache (complete coverage or good distribution), process the photos
					if not cache_ignored_due_to_distribution:

						sorted_cached = sorted(cached_photos, key=lambda x: x.get('bearing') or 0)

						# Clean up grid info before sending to client
						#for photo in sorted_cached:
						#	photo.pop('_grid_x', None)
						#	photo.pop('_grid_y', None)

						cached_photo_count = len(sorted_cached)

						# Track cached photo IDs to prevent duplication in live section
						for photo in sorted_cached:
							streamed_photo_ids.add(photo.get('id'))

						log.info(f"Streaming {cached_photo_count} cached photos to client {client_id}")
						yield f"data: {json.dumps({'type': 'photos', 'photos': sorted_cached})}\n\n"

				else:
					cached_photo_count = 0
					log.info(f"Cache miss: No cached photos found for bbox")
					yield f"data: {json.dumps({'type': 'photos', 'photos': []})}\n\n"

				# Calculate uncached regions (or use full area if cache was ignored due to poor distribution)
				# if cache_ignored_due_to_distribution:
				# 	# Cache was ignored due to poor distribution, fetch entire area
				# 	log.info("poor cache distribution.")
				# 	uncached_regions = [(top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon)]
				# else:
				# 	uncached_regions = await cache_service.calculate_uncached_regions(
				# 		top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon
				# 	)
				uncached_regions = [(top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon)]

				event['inputs'].append({
					'bbox': [top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon],
					'photos': cached_photos,
					'meta': {
						'type': 'cache',
						'cached_photo_count': cached_photo_count,
						'is_complete_coverage': is_complete_coverage,
						'distribution_score': distribution_score,
						'cache_ignored_due_to_distribution': cache_ignored_due_to_distribution,
						'uncached_regions': uncached_regions
					}
				})


				log.info(f"Cache analysis: Found {len(uncached_regions)} uncached regions for bbox")
				# Cache analysis complete - proceeding with any missing data fetch

				# Stream live data from uncached regions (only if live API is enabled)
				if uncached_regions and ENABLE_MAPILLARY_LIVE:
					log.info(f"Need to fetch data from Mapillary API for {len(uncached_regions)} uncached regions")
				elif uncached_regions and not ENABLE_MAPILLARY_LIVE:
					log.info(f"Found {len(uncached_regions)} uncached regions but live API is disabled - skipping live data fetch")

				for region_idx, region_bbox in enumerate(uncached_regions):
					# Skip processing if live API is disabled
					if not ENABLE_MAPILLARY_LIVE:
						break

					# Ensure region is not too large (larger regions cause internal server errors from Mapillary)
					region_bbox = shrink_bbox_to_max_area(region_bbox, max_area_sq_deg=0.009)

					log.info(f"Processing uncached region {region_idx + 1}/{len(uncached_regions)}: {region_bbox}")
					# Check if we've already reached the photo limit (including cached photos)
					total_photos_so_far = cached_photo_count + total_photo_count
					if total_photos_so_far >= effective_max_photos:
						log.info(f"Photo limit of {effective_max_photos} reached (cached: {cached_photo_count}, live: {total_photo_count}), skipping remaining regions")
						break

					try:
						# Create cache region
						region = await cache_service.create_cached_region(
							region_bbox[0], region_bbox[1], region_bbox[2], region_bbox[3]
						)

						region_photos = []

						# Stream all pages for this region
						region_fully_fetched = False
						while True:
							log.info(f"Query Mapillary for region {region.id} ...")
							mapillary_response = await fetch_mapillary_data(
								region_bbox[0], region_bbox[1], region_bbox[2], region_bbox[3], limit=effective_max_photos
							)

							event['inputs'].append({
								'bbox': region_bbox,
								'photos': mapillary_response.get('data', []),
								'meta': {
									'type': 'live',
									'region_id': region.id,
									'limit': effective_max_photos,
									'photo_count': len(mapillary_response.get('data', [])),
									'error': mapillary_response.get('error'),
								}
							})


							if "error" in mapillary_response:
								raise Exception(mapillary_response["error"])

							photos_data = mapillary_response["data"]

							if not photos_data:
								log.info(f"No more photos returned from Mapillary API for region {region.id}")
								region_fully_fetched = True
								break

							# Cache all photos we received
							region_photos.extend(photos_data)
							await cache_service.cache_photos(photos_data, region)

							# Apply photo limit only for streaming (accounting for cached photos)
							stream_photos = photos_data

							# Filter out photos that were already streamed from cache to prevent duplicates
							initial_count = len(stream_photos)
							stream_photos = [photo for photo in stream_photos if photo.get('id') not in streamed_photo_ids]
							filtered_count = len(stream_photos)

							if initial_count != filtered_count:
								log.info(f"Filtered out {initial_count - filtered_count} duplicate photos that were already streamed from cache")

							# Track newly streamed photo IDs
							for photo in stream_photos:
								streamed_photo_ids.add(photo.get('id'))

							# Apply hidden content filtering for streaming
							if user:
								stream_photos = await filter_mapillary_photos_list(stream_photos, user.id, db_session)

							total_photos_so_far = cached_photo_count + total_photo_count
							if total_photos_so_far + len(stream_photos) > effective_max_photos:
								# Truncate stream batch to stay within limit
								remaining_slots = effective_max_photos - total_photos_so_far
								stream_photos = stream_photos[:remaining_slots] if remaining_slots > 0 else []
								log.info(f"Photo limit reached, streaming only {len(stream_photos)} photos (of {len(photos_data)})")
							else:
								log.info(f"Streaming {len(stream_photos)} live photos from region {region.id} (cached {len(photos_data)})")

							total_photo_count += len(stream_photos)
							total_photos_so_far = cached_photo_count + total_photo_count
							log.info(f"Total photos streamed so far: {total_photos_so_far}/{effective_max_photos} (from cache: {cached_photo_count}, from live: {total_photo_count})")

							# Stream this batch (limited)
							sorted_batch = sorted(stream_photos, key=lambda x: x.get('bearing') or 0)
							# Region has more data if API indicates more pages available (regardless of our limit)
							yield f"data: {json.dumps({'type': 'photos', 'photos': sorted_batch})}\n\n"

							# Check if we've reached the photo limit for streaming
							if total_photos_so_far >= effective_max_photos:
								log.info(f"Photo limit of {effective_max_photos} reached, stopping fetch (region may have more data)")
								break

							else:
								# Check if we got fewer photos than requested - indicates no more data available
								break
								# if len(photos_data) < effective_max_photos:
								# 	log.info(f"Got partial batch ({len(photos_data)} < {effective_max_photos} requested) - region {region.id} appears complete")
								# 	region_fully_fetched = True
								# 	break
								# else:
								# 	log.info(f"Got full batch ({len(photos_data)} = {effective_max_photos} requested) - region {region.id} may have more data")
								# 	break  # Don't mark as complete, there might be more

						# Only mark region as complete if we actually fetched all available data from Mapillary
						if region_fully_fetched:
							await cache_service.mark_region_complete(region)
							log.info(f"Region {region.id} marked as complete: cached {len(region_photos)} total photos")
						else:
							log.info(f"Region {region.id} processing stopped due to limits but may have more data: cached {len(region_photos)} photos so far")

						yield f"data: {json.dumps({'type': 'region_complete', 'region': region.id, 'photos_count': len(region_photos)})}\n\n"

					except Exception as e:
						log.error(f"Error streaming region {region_bbox}: {str(e)}", exc_info=True)
						yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

			else:
				log.warning(f"Invalid configuration state: cache={ENABLE_MAPILLARY_CACHE}, live={ENABLE_MAPILLARY_LIVE}")

			# Send final summary
			total_all_photos = cached_photo_count + total_photo_count
			log.info(f"Stream complete for client {client_id}: {total_all_photos} total photos ({cached_photo_count} cached + {total_photo_count} live)")
			yield f"data: {json.dumps({'type': 'stream_complete', 'total_live_photos': total_photo_count, 'total_cached_photos': cached_photo_count, 'total_all_photos': total_all_photos})}\n\n"

		except Exception as e:
			log.error(f"Stream error for request {request_id}: {str(e)}", exc_info=True)
			yield f"data: {json.dumps({'type': 'error', 'message': f'Stream error: {str(e)}'})}\n\n"

		finally:
			log.info(f"Stream generator finished for request {request_id} from client {client_id}")

			# todo: save event to db

	try:
		log.debug(f"Creating StreamingResponse for client {client_id}")
		response = StreamingResponse(
			generate_stream(db, current_user),
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
		log.debug(f"StreamingResponse created successfully for client {client_id}")
		return response
	except Exception as e:
		log.error(f"Failed to create StreamingResponse for client {client_id}: {str(e)}", exc_info=True)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Failed to create stream: {str(e)}"
		)

@router.get("/stats")
async def get_cache_stats(
	request: Request,
	db: AsyncSession = Depends(get_db),
	current_user: Optional[User] = Depends(get_current_user_optional_with_query)
):
	"""Get cache statistics"""
	# Apply rate limiting with optional user context (better limits for authenticated users)
	await general_rate_limiter.enforce_rate_limit(request, 'public_read', current_user)

	cache_service = MapillaryCacheService(db)
	cache_stats = await cache_service.get_cache_stats()
	api_stats = api_manager.get_stats()

	return {
		"cache": cache_stats,
		"api": api_stats
	}

@router.get("/api-stats")
async def get_api_stats(
	request: Request,
	current_user: Optional[User] = Depends(get_current_user_optional_with_query)
):
	"""Get Mapillary API usage statistics"""
	# Apply rate limiting with optional user context (better limits for authenticated users)
	await general_rate_limiter.enforce_rate_limit(request, 'public_read', current_user)

	return api_manager.get_stats()

# Debug endpoints
async def clear_mapillary_cache_tables(db: AsyncSession) -> Dict[str, int]:
	"""Utility function to clear Mapillary cache tables.

	Returns:
		Dict with deletion counts
	"""
	from sqlalchemy import text

	mapillary_cache_result = await db.execute(text("DELETE FROM mapillary_photo_cache"))
	cached_regions_result = await db.execute(text("DELETE FROM cached_regions"))
	await db.commit()

	return {
		"mapillary_cache_deleted": mapillary_cache_result.rowcount,
		"cached_regions_deleted": cached_regions_result.rowcount
	}

@router.delete("/debug/cache")
@debug_only
async def clear_mapillary_cache(db: AsyncSession = Depends(get_db)):

	deletion_counts = await clear_mapillary_cache_tables(db)

	return {
		"status": "success",
		"message": "Mapillary cache cleared",
		"details": deletion_counts
	}

# Cleanup function for graceful shutdown
async def cleanup_mapillary_resources():
	"""Cleanup Mapillary API resources"""
	await api_manager.close()


def shrink_bbox_to_max_area(bbox: tuple, max_area_sq_deg: float) -> tuple:
	"""Shrink bounding box to fit within max area in square degrees"""
	top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon = bbox
	lat_diff = abs(top_left_lat - bottom_right_lat)
	lon_diff = get_lon_diff(top_left_lon, bottom_right_lon)
	area = lat_diff * lon_diff
	if area <= max_area_sq_deg:
		return bbox  # No need to shrink
	log.info(f"Shrinking request bbox to max area...")
	# return a square bbox with area = max_area_sq_deg, centered on original bbox center.
	center_lat = (top_left_lat + bottom_right_lat) / 2
	# take into account lon wrapping
	center_lon = get_center_lon(top_left_lon, bottom_right_lon)
	side_length = math.sqrt(max_area_sq_deg)
	half_side = side_length / 2
	new_top_left_lat = center_lat + half_side
	new_bottom_right_lat = center_lat - half_side
	new_top_left_lon = add_lon_offset(center_lon, -half_side)
	new_bottom_right_lon = add_lon_offset(center_lon, half_side)
	return (cull_lat(new_top_left_lat), new_top_left_lon, cull_lat(new_bottom_right_lat), new_bottom_right_lon)


def cull_lat(lat):
	if lat > 90:
		return 90
	elif lat < -90:
		return -90
	return lat

def get_center_lon(lon1, lon2):
	# convert degrees to radians
	lon1 = math.radians(lon1)
	lon2 = math.radians(lon2)

	x = math.cos(lon1) + math.cos(lon2)
	y = math.sin(lon1) + math.sin(lon2)

	mean = math.atan2(y, x)
	return math.degrees(mean)

def get_lon_diff(lon1, lon2):
	diff = abs(lon1 - lon2)
	if diff > 180:
		diff = 360 - diff
	return diff

def add_lon_offset(lon, offset):
	new_lon = lon + offset
	if new_lon > 180:
		new_lon -= 360
	elif new_lon < -180:
		new_lon += 360
	return new_lon


