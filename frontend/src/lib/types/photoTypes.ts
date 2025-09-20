import { LatLng } from 'leaflet';
import type { Source } from '../data.svelte';

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
    source_type: string;
    file: string;
    url: string;
    coord: LatLng;
    bearing: number;
    altitude: number;
    source?: Source;
    sizes?: Record<string, PhotoSize>;
    isUserPhoto?: boolean;
    isDevicePhoto?: boolean;
    isPlaceholder?: boolean;
    isDirectoryPhoto?: boolean;
    timestamp?: number;
    accuracy?: number;
    captured_at?: string;
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
    timestamp: number;
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
    isPlaceholder: true;
    tempId: string;
}

/**
 * User uploaded photo
 */
export interface UserPhoto {
    id: number;
    filename: string;
    latitude: number;
    longitude: number;
    compass_angle?: number;
    altitude?: number;
    uploaded_at: string;
}

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
    locationSource: 'gps' | 'map';
    bearingSource: string;
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
    locationSource: 'gps' | 'map';
    bearingSource: string;
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
    compass_angle: number;
    sequence: string;
    organization_id: number;
    mesh?: {
        url: string;
        faces: string;
        vertices: string;
    };
}