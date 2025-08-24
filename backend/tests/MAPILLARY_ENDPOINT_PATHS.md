# Mapillary Endpoint Code Paths

This document maps out the different execution paths through the mapillary endpoint and which tests exercise each path.

## Path 1: Cache Disabled
**Condition**: `ENABLE_MAPILLARY_CACHE=false`
**Logic**: Direct live API calls, no caching
**Tests**: N/A (cache always enabled in our tests)

## Path 2: Cache Enabled - Complete Coverage + Small Dataset
**Conditions**: 
- `is_complete_coverage = True` (got fewer photos than requested in first request)
- `total_cached_photos <= max_photos` (count check in cache service)

**Logic**: 
- Cache service uses simple query without spatial sampling
- Returns ALL cached photos
- `distribution_score = 1.0` (perfect)

**SQL Query**:
```sql
SELECT p.mapillary_id, ST_X(p.geometry) as lon, ST_Y(p.geometry) as lat, ...
FROM mapillary_photo_cache p
WHERE ST_Within(p.geometry, ST_GeomFromText(:bbox_wkt, 4326))
ORDER BY p.captured_at DESC
LIMIT :max_photos
```

**Tests**: 
- ✅ **20-photo test**: Request 70, get 20 → region complete → use simple query → return all 20

## Path 3: Cache Enabled - Complete Coverage + Large Dataset  
**Conditions**:
- `is_complete_coverage = True` (got fewer photos than requested)
- `total_cached_photos > max_photos` (too many cached photos for simple return)

**Logic**:
- Cache service applies spatial sampling for better distribution
- Should return well-distributed subset of cached photos
- `distribution_score` calculated based on grid distribution

**SQL Query**: Complex spatial sampling with `ROW_NUMBER() PARTITION BY grid_x, grid_y`

**Tests**:
- **500-photo test** (if region marked complete): Expected path but currently failing

## Path 4: Cache Enabled - Incomplete Coverage
**Conditions**:
- `is_complete_coverage = False` (got exactly as many photos as requested)

**Logic**:
- Cache service applies spatial sampling
- If `distribution_score < 90%`: Fall back to live API
- If `distribution_score >= 90%`: Use cached photos

**SQL Query**: Same complex spatial sampling as Path 3

**Tests**:
- **500-photo test** (if region marked incomplete): Currently hitting this path
- **2000-photo test**: Currently hitting this path, getting 505 photos instead of 2000

## Path 5: Cache Miss
**Conditions**: No cached photos found in database

**Logic**: Direct live API calls with background caching

**Tests**: First request in all tests before cache is populated

## Current Test Results Analysis

### ✅ 20-photo test (Path 2)
- Request 70, get 20 → `is_complete_coverage = True`
- 20 cached ≤ 20 requested → simple query
- Result: 20 cached + 0 live ✓

### ❌ 500-photo test 
- Request 550, get 500 → should be `is_complete_coverage = True`
- 500 cached > 500 requested → should use spatial sampling (Path 3)
- **Issue**: Getting 0 cached + 500 live (falling back to live API)
- **Likely cause**: Spatial sampling reducing 500 clustered photos to few photos, poor distribution

### ❌ 2000-photo test
- Request 2050, get 505 → `is_complete_coverage = ?`
- **Issue**: Only getting 505 photos instead of 2000 from mock
- **Likely cause**: Spatial sampling SQL query limiting clustered photos severely

## Key Problems to Fix

1. **Spatial sampling SQL**: `ROW_NUMBER() PARTITION BY grid_x, grid_y` fails for clustered data
2. **Round-robin sampling**: Need better distribution algorithm for clustered photos
3. **Path 3 vs Path 4**: Verify region completion detection for larger datasets