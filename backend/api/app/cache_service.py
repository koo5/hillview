import asyncio
import datetime
import logging
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func, text
from geoalchemy2 import functions as geo_func
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.models import CachedRegion, MapillaryPhotoCache
from common.database import get_db

log = logging.getLogger(__name__)

class MapillaryCacheService:
    """Service for managing Mapillary photo caching with PostGIS spatial queries"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_cached_photos_in_bbox(
        self, 
        top_left_lat: float,
        top_left_lon: float,
        bottom_right_lat: float,
        bottom_right_lon: float,
        max_photos: int = 3000,
        current_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get cached photos within bounding box with spatial sampling for even distribution"""
        
        # Create bbox polygon
        bbox_wkt = f"POLYGON(({top_left_lon} {top_left_lat}, {bottom_right_lon} {top_left_lat}, {bottom_right_lon} {bottom_right_lat}, {top_left_lon} {bottom_right_lat}, {top_left_lon} {top_left_lat}))"
        
        # Calculate grid dimensions (10x10 = 100 cells)
        grid_size = 10
        cell_width = (bottom_right_lon - top_left_lon) / grid_size
        cell_height = (top_left_lat - bottom_right_lat) / grid_size
        photos_per_cell = max(1, max_photos // (grid_size * grid_size))  # Distribute photos across cells
        
        log.info(f"Grid calculation: bbox=({top_left_lat}, {top_left_lon}) to ({bottom_right_lat}, {bottom_right_lon})")
        log.info(f"Grid dimensions: cell_width={cell_width:.6f}, cell_height={cell_height:.6f}, photos_per_cell={photos_per_cell}")
        
        # Debug: Test the grid calculation with a sample query
        debug_query = text("""
            SELECT 
                ST_X(p.geometry) as lon, 
                ST_Y(p.geometry) as lat,
                (ST_X(p.geometry) - :bbox_min_x) / :cell_width * :grid_size as raw_grid_x,
                (ST_Y(p.geometry) - :bbox_min_y) / :cell_height * :grid_size as raw_grid_y,
                CAST(LEAST(GREATEST(FLOOR((ST_X(p.geometry) - :bbox_min_x) / :cell_width * :grid_size), 0), :grid_size - 1) AS INTEGER) as grid_x,
                CAST(LEAST(GREATEST(FLOOR((ST_Y(p.geometry) - :bbox_min_y) / :cell_height * :grid_size), 0), :grid_size - 1) AS INTEGER) as grid_y
            FROM mapillary_photo_cache p
            WHERE ST_Within(p.geometry, ST_GeomFromText(:bbox_wkt, 4326))
            LIMIT 5
        """)
        debug_result = await self.db.execute(debug_query, {
            'bbox_wkt': bbox_wkt,
            'bbox_min_x': top_left_lon,
            'bbox_min_y': bottom_right_lat,
            'cell_width': cell_width,
            'cell_height': cell_height,
            'grid_size': grid_size
        })
        debug_rows = debug_result.fetchall()
        if debug_rows:
            log.info("Debug: Sample coordinate calculations:")
            for row in debug_rows:
                log.info(f"  lon={row.lon:.6f}, lat={row.lat:.6f}, raw_x={row.raw_grid_x:.2f}, raw_y={row.raw_grid_y:.2f}, grid_x={row.grid_x}, grid_y={row.grid_y}")
        else:
            log.warning("Debug: No photos found in bbox for grid calculation test")
        
        # Import and use the SQL-based filtering for Mapillary
        from .hidden_content_filters import apply_mapillary_hidden_content_filters
        
        # Build the hidden content filtering conditions
        hidden_filters = apply_mapillary_hidden_content_filters([], current_user_id)
        
        # Use raw SQL for spatial sampling with grid-based distribution
        # Grid coordinates should be 0-9 for both x and y
        query = text(f"""
            WITH cell_photos AS (
                SELECT p.*,
                       CAST(LEAST(GREATEST(FLOOR((ST_X(p.geometry) - :bbox_min_x) / :cell_width * :grid_size), 0), :grid_size - 1) AS INTEGER) as grid_x,
                       CAST(LEAST(GREATEST(FLOOR((ST_Y(p.geometry) - :bbox_min_y) / :cell_height * :grid_size), 0), :grid_size - 1) AS INTEGER) as grid_y,
                       ROW_NUMBER() OVER (
                           PARTITION BY 
                               CAST(LEAST(GREATEST(FLOOR((ST_X(p.geometry) - :bbox_min_x) / :cell_width * :grid_size), 0), :grid_size - 1) AS INTEGER),
                               CAST(LEAST(GREATEST(FLOOR((ST_Y(p.geometry) - :bbox_min_y) / :cell_height * :grid_size), 0), :grid_size - 1) AS INTEGER)
                           ORDER BY random()
                       ) as row_num
                FROM mapillary_photo_cache p
                WHERE ST_Within(p.geometry, ST_GeomFromText(:bbox_wkt, 4326))
                {hidden_filters}
            )
            SELECT mapillary_id, ST_X(geometry) as lon, ST_Y(geometry) as lat, 
                   compass_angle, computed_compass_angle, computed_rotation, computed_altitude,
                   captured_at, is_pano, thumb_1024_url, creator_username, creator_id, grid_x, grid_y
            FROM cell_photos 
            WHERE row_num <= :photos_per_cell
            ORDER BY grid_x, grid_y, row_num
            LIMIT :max_photos
        """)
        
        params = {
            'bbox_wkt': bbox_wkt,
            'bbox_min_x': top_left_lon,
            'bbox_min_y': bottom_right_lat,
            'cell_width': cell_width,
            'cell_height': cell_height,
            'grid_size': grid_size,
            'photos_per_cell': photos_per_cell,
            'max_photos': max_photos
        }
        
        if current_user_id:
            params['current_user_id'] = current_user_id
        
        result = await self.db.execute(query, params)
        
        cached_photos = result.fetchall()
        
        # Convert to Mapillary API format
        photos = []
        for row in cached_photos:
            photo_data = {
                "id": row.mapillary_id,
                "geometry": {
                    "type": "Point",
                    "coordinates": [row.lon, row.lat]
                },
                "compass_angle": row.compass_angle,
                "computed_compass_angle": row.computed_compass_angle,
                "computed_rotation": row.computed_rotation,
                "computed_altitude": row.computed_altitude,
                "captured_at": row.captured_at.isoformat() if row.captured_at else None,
                "is_pano": row.is_pano,
                "thumb_1024_url": row.thumb_1024_url,
                "creator": {
                    "username": row.creator_username,
                    "id": row.creator_id
                } if row.creator_username or row.creator_id else None,
                # Include grid info for distribution analysis
                "_grid_x": row.grid_x,
                "_grid_y": row.grid_y
            }
            photos.append(photo_data)
        
        # Debug: Check actual grid coordinates being returned
        if photos:
            grid_coords = [(photo.get('_grid_x'), photo.get('_grid_y')) for photo in photos]
            log.info(f"Debug: Grid coordinates: {grid_coords}")
            
            # Check for invalid coordinates
            invalid_coords = [(x, y) for x, y in grid_coords if x is None or y is None or x < 0 or x >= grid_size or y < 0 or y >= grid_size]
            if invalid_coords:
                log.warning(f"Found invalid grid coordinates: {invalid_coords}")
        
        log.info(f"Spatial sampling returned {len(photos)} photos distributed across grid cells")
        
        # Check if the requested bbox is covered by complete regions FIRST
        is_complete_coverage = await self._is_bbox_completely_cached(
            top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon
        )
        
        if is_complete_coverage:
            # If completely cached, return immediately without distribution calculation
            log.info(f"Cache result: {len(photos)} photos from COMPLETE coverage - distribution check skipped")
            return {
                'photos': photos,
                'is_complete_coverage': True,
                'distribution_score': 1.0  # Perfect score for complete coverage
            }
        else:
            # Only calculate distribution for incomplete coverage
            distribution_score = self.calculate_spatial_distribution(photos) if photos else 0.0
            log.info(f"Cache result: {len(photos)} photos from INCOMPLETE coverage, distribution={distribution_score:.2%}")
            return {
                'photos': photos,
                'is_complete_coverage': False,
                'distribution_score': distribution_score
            }
    
    async def _is_bbox_completely_cached(
        self,
        top_left_lat: float,
        top_left_lon: float, 
        bottom_right_lat: float,
        bottom_right_lon: float
    ) -> bool:
        """Check if the given bbox is completely covered by complete cached regions."""
        # Get all complete cached regions that intersect with request
        cached_regions = await self.get_cached_regions_for_bbox(
            top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon
        )
        
        # Filter to only complete regions
        complete_regions = [r for r in cached_regions if r.is_complete]
        
        if not complete_regions:
            return False
        
        # For simplicity, if we have any complete regions covering our bbox,
        # and we retrieved photos, assume complete coverage
        # (More sophisticated geometry checking could be added later)
        log.info(f"Completeness check: found {len(complete_regions)} complete regions covering bbox")
        return len(complete_regions) > 0
    
    def calculate_spatial_distribution(self, photos: List[Dict[str, Any]], grid_size: int = 10) -> float:
        """Calculate spatial distribution score (0.0 = all clustered, 1.0 = perfectly distributed)"""
        if not photos:
            return 0.0
        
        # Count occupied grid cells
        occupied_cells = set()
        valid_photos = 0
        invalid_coords = []
        
        for photo in photos:
            if '_grid_x' in photo and '_grid_y' in photo:
                x, y = photo['_grid_x'], photo['_grid_y']
                if x is not None and y is not None:
                    if 0 <= x < grid_size and 0 <= y < grid_size:
                        occupied_cells.add((x, y))
                        valid_photos += 1
                    else:
                        invalid_coords.append((x, y))
        
        total_cells = grid_size * grid_size
        occupied_ratio = len(occupied_cells) / total_cells
        
        log.info(f"Distribution analysis: {len(occupied_cells)}/{total_cells} cells occupied ({occupied_ratio:.2%})")
        log.info(f"Debug: {valid_photos} valid photos, {len(invalid_coords)} invalid coordinates")
        if invalid_coords:
            log.warning(f"Invalid grid coordinates found: {invalid_coords[:10]}...")  # Show first 10
        
        return occupied_ratio
    
    async def get_cached_regions_for_bbox(
        self,
        top_left_lat: float,
        top_left_lon: float,
        bottom_right_lat: float,
        bottom_right_lon: float
    ) -> List[CachedRegion]:
        """Get cached regions that intersect with the requested bbox"""
        
        bbox_wkt = f"POLYGON(({top_left_lon} {top_left_lat}, {bottom_right_lon} {top_left_lat}, {bottom_right_lon} {bottom_right_lat}, {top_left_lon} {bottom_right_lat}, {top_left_lon} {top_left_lat}))"
        
        query = select(CachedRegion).where(
            geo_func.ST_Intersects(
                CachedRegion.bbox,
                func.ST_GeomFromText(bbox_wkt, 4326)
            )
        )
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def calculate_uncached_regions(
        self,
        top_left_lat: float,
        top_left_lon: float,
        bottom_right_lat: float,
        bottom_right_lon: float
    ) -> List[Tuple[float, float, float, float]]:
        """Calculate which parts of the bbox are not cached"""
        
        request_bbox = Polygon([
            (top_left_lon, top_left_lat),
            (bottom_right_lon, top_left_lat),
            (bottom_right_lon, bottom_right_lat),
            (top_left_lon, bottom_right_lat),
            (top_left_lon, top_left_lat)
        ])
        
        # Get all cached regions that intersect with request
        cached_regions = await self.get_cached_regions_for_bbox(
            top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon
        )
        
        # Get only complete regions for coverage calculation
        complete_regions = [r for r in cached_regions if r.is_complete]
        
        if not complete_regions:
            # Nothing cached, return original bbox
            return [(top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon)]
        
        # Convert cached regions to Shapely polygons
        cached_polygons = []
        for region in complete_regions:
            polygon = to_shape(region.bbox)
            cached_polygons.append(polygon)
        
        # Union all cached areas
        cached_union = unary_union(cached_polygons)
        
        # Calculate uncached areas
        uncached_areas = request_bbox.difference(cached_union)
        
        # Convert back to bounding boxes
        uncached_bboxes = []
        
        if uncached_areas.is_empty:
            return []
        
        # Handle different geometry types
        if hasattr(uncached_areas, 'geoms'):
            # MultiPolygon or GeometryCollection
            for geom in uncached_areas.geoms:
                if geom.geom_type == 'Polygon':
                    bounds = geom.bounds
                    uncached_bboxes.append((bounds[3], bounds[0], bounds[1], bounds[2]))  # top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon
        else:
            # Single Polygon
            bounds = uncached_areas.bounds
            uncached_bboxes.append((bounds[3], bounds[0], bounds[1], bounds[2]))
        
        return uncached_bboxes
    
    async def create_cached_region(
        self,
        top_left_lat: float,
        top_left_lon: float,
        bottom_right_lat: float,
        bottom_right_lon: float
    ) -> CachedRegion:
        """Create a new cached region with race condition protection"""
        
        bbox_wkt = f"POLYGON(({top_left_lon} {top_left_lat}, {bottom_right_lon} {top_left_lat}, {bottom_right_lon} {bottom_right_lat}, {top_left_lon} {bottom_right_lat}, {top_left_lon} {top_left_lat}))"
        
        # Check if region already exists (race condition protection)
        existing_query = select(CachedRegion).where(
            geo_func.ST_Equals(
                CachedRegion.bbox,
                func.ST_GeomFromText(bbox_wkt, 4326)
            )
        )
        result = await self.db.execute(existing_query)
        existing_region = result.scalars().first()
        
        if existing_region:
            return existing_region
        
        # Create new region with retry logic
        try:
            region = CachedRegion(
                bbox=func.ST_GeomFromText(bbox_wkt, 4326),
                is_complete=False,
                photo_count=0,
                has_more=True
            )
            
            self.db.add(region)
            await self.db.commit()
            await self.db.refresh(region)
            
            return region
            
        except Exception as e:
            # Handle potential unique constraint violations
            await self.db.rollback()
            
            # Try to find the region that was created by another request
            result = await self.db.execute(existing_query)
            existing_region = result.scalars().first()
            
            if existing_region:
                return existing_region
            else:
                # Re-raise if it's not a race condition
                raise e
    
    async def cache_photos(
        self,
        photos_data: List[Dict[str, Any]],
        region: CachedRegion
    ) -> int:
        """Cache photos from Mapillary API response using batch operations"""
        
        if not photos_data:
            return 0
        
        # Get existing photo IDs in batch
        photo_ids = [photo_data['id'] for photo_data in photos_data]
        existing_query = select(MapillaryPhotoCache.mapillary_id).where(
            MapillaryPhotoCache.mapillary_id.in_(photo_ids)
        )
        result = await self.db.execute(existing_query)
        existing_ids = set(result.scalars().all())
        
        # Prepare batch insert data
        photos_to_insert = []
        cached_count = 0
        
        for photo_data in photos_data:
            if photo_data['id'] in existing_ids:
                continue  # Skip if already cached
            
            # Extract coordinates from geometry
            coords = photo_data['geometry']['coordinates']
            point = Point(coords[0], coords[1])
            
            # Parse captured_at date
            captured_at = None
            if photo_data.get('captured_at'):
                try:
                    captured_at = datetime.datetime.fromisoformat(photo_data['captured_at'].replace('Z', '+00:00'))
                except:
                    pass
            
            # Handle computed_rotation - it may be a list/array
            computed_rotation = photo_data.get('computed_rotation')
            if isinstance(computed_rotation, list) and len(computed_rotation) > 0:
                # Take the first value if it's a list
                computed_rotation = computed_rotation[0]
            elif not isinstance(computed_rotation, (int, float, type(None))):
                # Set to None if it's not a valid numeric type
                computed_rotation = None
            
            # Extract creator information
            creator_username = None
            creator_id = None
            creator_data = photo_data.get('creator')
            if creator_data and isinstance(creator_data, dict):
                creator_username = creator_data.get('username')
                creator_id = creator_data.get('id')
            
            # Prepare insert data
            photo_dict = {
                'mapillary_id': photo_data['id'],
                'geometry': from_shape(point, srid=4326),
                'compass_angle': photo_data.get('compass_angle'),
                'computed_compass_angle': photo_data.get('computed_compass_angle'),
                'computed_rotation': computed_rotation,
                'computed_altitude': photo_data.get('computed_altitude'),
                'captured_at': captured_at,
                'is_pano': photo_data.get('is_pano', False),
                'thumb_1024_url': photo_data.get('thumb_1024_url'),
                'creator_username': creator_username,
                'creator_id': creator_id,
                'region_id': region.id,
                'raw_data': photo_data,
                'cached_at': datetime.datetime.utcnow()
            }
            
            photos_to_insert.append(photo_dict)
            cached_count += 1
        
        # Batch insert
        if photos_to_insert:
            from sqlalchemy import insert
            stmt = insert(MapillaryPhotoCache).values(photos_to_insert)
            await self.db.execute(stmt)
            
            # Update region stats
            region.photo_count += cached_count
            region.last_updated = datetime.datetime.utcnow()
            
            await self.db.commit()
        
        return cached_count
    
    async def mark_region_complete(self, region: CachedRegion, last_cursor: Optional[str] = None):
        """Mark a region as completely cached"""
        region.is_complete = True
        region.has_more = False
        region.last_cursor = last_cursor
        region.last_updated = datetime.datetime.utcnow()
        await self.db.commit()
    
    async def update_region_cursor(self, region: CachedRegion, cursor: str):
        """Update region's pagination cursor"""
        region.last_cursor = cursor
        region.last_updated = datetime.datetime.utcnow()
        await self.db.commit()
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        
        # Count total cached photos
        photo_count = await self.db.execute(
            select(func.count(MapillaryPhotoCache.mapillary_id))
        )
        total_photos = photo_count.scalar()
        
        # Count cached regions
        region_count = await self.db.execute(
            select(func.count(CachedRegion.id))
        )
        total_regions = region_count.scalar()
        
        # Count complete regions
        complete_count = await self.db.execute(
            select(func.count(CachedRegion.id)).where(CachedRegion.is_complete == True)
        )
        complete_regions = complete_count.scalar()
        
        return {
            "total_cached_photos": total_photos,
            "total_cached_regions": total_regions,
            "complete_cached_regions": complete_regions,
            "cache_efficiency": (complete_regions / total_regions * 100) if total_regions > 0 else 0
        }