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

// Sources load concurrently and each publishes as its photos arrive. The first
// arrival for an area is published immediately (time-to-first-marker); later
// arrivals are trailing-edge throttled to this interval so a chatty stream
// doesn't re-cull and redraw the map on every batch. The final publish when
// every source has settled is never throttled.
export const PARTIAL_PUBLISH_THROTTLE_MS = 300;

// A stream that goes silent for this long is treated as failed. Without it a
// hung EventSource (no message, no error) never resolves the loader, the area
// process never completes, and the worker wedges for good.
export const STREAM_INACTIVITY_TIMEOUT_MS = 60000;
