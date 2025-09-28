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
 * Generate a unique temporary ID for a placeholder
 */
export function generateTempId(): string {
    return `temp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Create a placeholder photo object for immediate display on the map
 */
export function createPlaceholderPhoto(
    location: PlaceholderLocation,
    tempId: string,
    source: Source
): PlaceholderPhoto {
    return {
        id: tempId,
        uid: `${source.id}-${tempId}`,
        source_type: 'device',
        file: 'placeholder.jpg',
        url: 'placeholder://arrow',
        coord: new LatLng(location.latitude, location.longitude),
        bearing: location.heading || 0,
        altitude: location.altitude || 0,
        source: source,
        isDevicePhoto: true,
        isPlaceholder: true,
        tempId: tempId,
        timestamp: Date.now(),
        accuracy: location.accuracy
    };
}

/**
 * Create a device photo metadata object for placeholder storage
 */
export function createPlaceholderMetadata(
    location: PlaceholderLocation,
    tempId: string,
    timestamp: number = Date.now()
): DevicePhotoMetadata {
    return {
        id: tempId,
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
    return photo.isPlaceholder === true || photo.id.startsWith('temp_');
}