/**
 * Common photo types shared between workers and main app
 * This file has NO external dependencies so it can be imported in workers
 */

/**
 * Unique identifier for photos
 */
export type PhotoId = string;

/**
 * Simple coordinate interface for worker compatibility (can't import leaflet in workers)
 */
export interface SimpleCoord {
    lat: number;
    lng: number;
}

/**
 * Base photo size information
 */
export interface PyramidMetadata {
	type: 'dzi';
	dzi_url: string;
	tiles_url: string;
	tile_size: number;
	overlap: number;
	format: string;
	width: number;
	height: number;
}

/**
 * Base photo size information
 */
export interface PhotoSize {
    url: string;
    width: number;
    height: number;
    pyramid?: PyramidMetadata;
}

/**
 * Base photo data with fields common to both workers and main app
 */
export interface BasePhotoData {
    id: PhotoId;
    uid: string;
    source_type: string;
    filename: string;
    url: string;
    bearing: number;
    pitch?: number;
    altitude: number;
    sizes?: Record<string, PhotoSize>;
    is_user_photo?: boolean;
    is_device_photo?: boolean;
    is_placeholder?: boolean;
    captured_at?: number;
    accuracy?: number;

    featured?: boolean;

    // Computed properties (added by processing)
    abs_bearing_diff?: number;
    bearing_color?: string;
    range_distance?: number | null;
    angular_distance_abs?: number;
    file_hash?: string;
}