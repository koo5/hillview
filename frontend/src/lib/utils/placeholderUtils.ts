import { LatLng } from 'leaflet';
import type { PlaceholderPhoto, DevicePhotoMetadata } from '../types/photoTypes';
import type { Source } from '../data.svelte';

export interface PlaceholderLocation {
    latitude: number;
    longitude: number;
    altitude?: number | null;
    heading?: number | null;
    accuracy: number;
    locationSource: 'gps' | 'map';
    bearingSource: string;
}

/**
 * Generate a unique photo ID that will be used throughout the entire pipeline
 * Compatible with Kotlin PhotoUtils.generatePhotoId() format: timestamp_hash8chars
 */
export function generatePhotoId(): string {
    const timestamp = Date.now();
    const random = Math.random().toString(36).substr(2, 8); // 8 chars to match Kotlin hash8chars
    return `photo_${timestamp}_${random}`;
}

/**
 * Generate a unique temporary ID for a placeholder
 * @deprecated Use generatePhotoId() instead for shared ID system
 */
export function generateTempId(): string {
    return `temp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Create a placeholder photo object for immediate display on the map
 */
export function createPlaceholderPhoto(
    location: PlaceholderLocation,
    sharedId: string,
    source: Source
): PlaceholderPhoto {
    return {
        id: sharedId,
        uid: `${source.id}-${sharedId}`,
        source_type: 'device',
        file: 'placeholder.jpg',
        url: 'placeholder://arrow',
        coord: new LatLng(location.latitude, location.longitude),
        bearing: location.heading || 0,
        altitude: location.altitude || 0,
        source: source,
        isDevicePhoto: true,
        isPlaceholder: true,
        tempId: sharedId, // Use sharedId as tempId for compatibility
        timestamp: Date.now(),
        accuracy: location.accuracy
    };
}

/**
 * Create a device photo metadata object for placeholder storage
 */
export function createPlaceholderMetadata(
    location: PlaceholderLocation,
    sharedId: string,
    timestamp: number = Date.now()
): DevicePhotoMetadata {
    return {
        id: sharedId,
        filename: 'processing.jpg',
        path: 'placeholder://processing',
        latitude: location.latitude,
        longitude: location.longitude,
        altitude: location.altitude,
        bearing: location.heading,
        timestamp,
        accuracy: location.accuracy || 1,
        width: 0,
        height: 0,
        file_size: 0,
        created_at: timestamp
    };
}

/**
 * Check if a photo is a placeholder
 */
export function isPlaceholder(photo: { id: string; isPlaceholder?: boolean }): boolean {
    return photo.isPlaceholder === true || photo.id.startsWith('temp_') || photo.id.startsWith('photo_');
}