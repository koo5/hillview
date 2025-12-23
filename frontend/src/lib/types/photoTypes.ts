import { LatLng } from 'leaflet';
import type { Source } from '../data.svelte';
import type { PhotoItemData } from './photoItemTypes';

/**
 * Unique identifier for photos
 */
export type PhotoId = string;

/**
 * Base photo size information
 */
export interface PhotoSize {
    url: string;
    width: number;
    height: number;
}

/**
 * Base photo data structure used throughout the application
 */
export interface PhotoData {
    id: PhotoId;
    uid: string;
    source_type: string;
    file: string;
    url: string;
    coord: LatLng;
    bearing: number;
    pitch?: number;
    altitude: number;
    source?: Source;
    sizes?: Record<string, PhotoSize>;
    is_user_photo?: boolean;
    is_device_photo?: boolean;
    is_placeholder?: boolean;
    is_directory_photo?: boolean;
    captured_at?: number;
    accuracy?: number;
    // Computed properties (added by processing)
    abs_bearing_diff?: number;
    bearing_color?: string;
    range_distance?: number | null;
    angular_distance_abs?: number;
}

/**
 * Photo with bearing information (after processing)
 */
export interface PhotoWithBearing extends PhotoData {
    abs_bearing_diff: number;
    bearing_color: string;
    angular_distance_abs?: number;
}

/**
 * Device photo metadata stored in the backend
 */
export interface DevicePhotoMetadata {
    id: PhotoId;
    filename: string;
    path: string;
    latitude: number;
    longitude: number;
    altitude?: number | null;
    bearing?: number | null;
    captured_at: number;
    accuracy: number;
    width: number;
    height: number;
    file_size: number;
    created_at: number;
}

/**
 * Placeholder photo for immediate display
 */
export interface PlaceholderPhoto extends PhotoData {
    is_placeholder: true;
    temp_id: string;
}

/**
 * User uploaded photo
 */

/**
 * Photo metadata for capture
 */
export interface PhotoMetadata {
    latitude: number;
    longitude: number;
    altitude?: number | null;
    bearing?: number | null;
    timestamp: number;
    accuracy: number;
    location_source: 'gps' | 'map';
    bearing_source: string;
}

/**
 * Captured photo data before processing
 */
export interface CapturedPhotoData {
    image: File;
    location: {
        latitude: number;
        longitude: number;
        altitude?: number | null;
        accuracy: number;
    };
    bearing?: number | null;
    timestamp: number;
    location_source: 'gps' | 'map';
    bearing_source: string;
}

/**
 * Mapillary photo structure
 */
export interface MapillaryPhoto {
    id: string;
    lat: number;
    lon: number;
    is_pano: boolean;
    camera_angle: number;
    bearing: number;
    sequence: string;
    organization_id: number;
    mesh?: {
        url: string;
        faces: string;
        vertices: string;
    };
}

/**
 * Full photo information for zoom view and detailed display
 */
export interface FullPhotoInfo {
    url: string;
    width?: number;
    height?: number;
}

/**
 * Union type for all photo types that can be used with getFullPhotoInfo
 */
export type PhotoForInfo = PhotoData | PhotoItemData | DevicePhotoMetadata;
