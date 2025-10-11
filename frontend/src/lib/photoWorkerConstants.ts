/**
 * Photo Worker Constants - Single source of truth for photo processing limits
 *
 * These values control photo culling behavior across all worker implementations.
 * Changing these affects performance and memory usage.
 */

// Maximum photos to display in the map area after grid culling
export const MAX_PHOTOS_IN_AREA = 400;

// Maximum photos to show in range navigation after angular culling
export const MAX_PHOTOS_IN_RANGE = 200;

// Default range in meters for range-based photo filtering
export const DEFAULT_RANGE_METERS = 1000;