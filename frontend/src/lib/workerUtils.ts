/**
 * Worker-compatible utility functions
 * These functions don't depend on DOM/Leaflet and can be used safely in workers
 */

import type { PhotoData, Bounds } from './photoWorkerTypes';

/**
 * Calculate the distance between two geographic points in meters
 * Using the Haversine formula
 */
export function calculateDistance(lat1: number, lng1: number, lat2: number, lng2: number): number {
    const R = 6371e3; // Earth's radius in meters
    const φ1 = lat1 * Math.PI / 180;
    const φ2 = lat2 * Math.PI / 180;
    const Δφ = (lat2 - lat1) * Math.PI / 180;
    const Δλ = (lng1 - lng2) * Math.PI / 180;

    const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
        Math.cos(φ1) * Math.cos(φ2) *
        Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

    return R * c;
}

/**
 * Check if a photo is within given bounds with optional tolerance
 */
export function isPhotoInBounds(photo: PhotoData, bounds: Bounds, tolerance: number = 0): boolean {
    const lat = photo.coord.lat;
    const lng = photo.coord.lng;

    const topLat = bounds.top_left.lat + tolerance;
    const leftLng = bounds.top_left.lng - tolerance;
    const bottomLat = bounds.bottom_right.lat - tolerance;
    const rightLng = bounds.bottom_right.lng + tolerance;

    return lat <= topLat && lat >= bottomLat && lng >= leftLng && lng <= rightLng;
}

/**
 * Filter photos by geographic area
 */
export function filterPhotosByArea(photos: PhotoData[], bounds: Bounds, tolerance: number = 0): PhotoData[] {
    return photos.filter(photo => isPhotoInBounds(photo, bounds, tolerance));
}