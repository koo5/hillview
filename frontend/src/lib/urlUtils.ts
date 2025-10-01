/**
 * URL construction utilities for Hillview frontend
 * Centralizes all URL construction to follow DRY principles
 */

import { get } from 'svelte/store';
import { spatialState } from './mapState';
import type { PhotoData } from './sources';
import { TAURI } from './tauri';
import { openUrl } from '@tauri-apps/plugin-opener';

/**
 * Extracts coordinates from various photo data formats
 * @param photo Photo object in any supported format
 * @returns Object with lat, lon, and bearing or null if no valid coordinates found
 */
function extractCoordinates(photo: any): { lat: number; lon: number; bearing?: number } | null {
    // PhotoData type (from map/gallery) - coordinates stored in coord.lat/lng
    if (photo?.coord?.lat !== undefined && photo?.coord?.lng !== undefined) {
        return {
            lat: photo.coord.lat,
            lon: photo.coord.lng,
            bearing: photo.bearing
        };
    }

    // UserPhoto/DevicePhoto type - direct latitude/longitude properties
    if (photo?.latitude !== undefined && photo?.longitude !== undefined) {
        return {
            lat: photo.latitude,
            lon: photo.longitude,
            bearing: photo.bearing
        };
    }

    // Alternative lat/lon format (some APIs use different names)
    if (photo?.lat !== undefined && photo?.lon !== undefined) {
        return {
            lat: photo.lat,
            lon: photo.lon,
            bearing: photo.bearing
        };
    }

    return null;
}

/**
 * Base URL for production Hillview site
 */
const HILLVIEW_BASE_URL = 'https://hillview.cz';

/**
 * Constructs a map view URL with location parameters
 * @param options Location and view parameters
 * @param options.lat Latitude
 * @param options.lon Longitude
 * @param options.zoom Map zoom level (uses current zoom if not provided)
 * @param options.bearing Camera bearing (optional)
 * @param options.photoUid Photo unique identifier for navigation (optional)
 * @param options.baseUrl Base URL (defaults to relative path for internal navigation)
 * @returns Complete URL with location parameters
 */
export function constructMapUrl(options: {
    lat: number;
    lon: number;
    zoom?: number;
    bearing?: number;
    photoUid?: string;
    baseUrl?: string;
}): string {
    const { lat, lon, bearing, photoUid, baseUrl = '' } = options;

    // Use provided zoom, current map zoom, or default to 18
    let zoom = options.zoom;
    if (zoom === undefined) {
        const currentSpatial = get(spatialState);
        zoom = currentSpatial?.zoom || 18;
    }

    let url = `${baseUrl}/?lat=${lat}&lon=${lon}&zoom=${zoom}`;

    if (bearing !== undefined && bearing !== null) {
        url += `&bearing=${bearing}`;
    }

    if (photoUid) {
        url += `&photo=${encodeURIComponent(photoUid)}`;
    }

    return url;
}

/**
 * Constructs a share URL for a photo on hillview.cz
 * @param photo Photo data containing location information and uid
 * @returns Complete hillview.cz URL with location and photo parameters
 */
export function constructShareUrl(photo: PhotoData | any): string {
    const coords = extractCoordinates(photo);

    if (!coords) {
        console.warn('🔗 constructShareUrl: No valid coordinates found in photo:', {
            hasCoord: !!photo?.coord,
            hasLatLng: !!(photo?.latitude && photo?.longitude),
            hasLatLon: !!(photo?.lat && photo?.lon),
            photoKeys: photo ? Object.keys(photo) : 'no photo'
        });
        return HILLVIEW_BASE_URL;
    }

    // Construct uid if not present (for UserPhoto objects from hillview backend)
    let photoUid = photo.uid;
    if (!photoUid && photo.id) {
        photoUid = `hillview-${photo.id}`;
    }

    return constructMapUrl({
        zoom: 20, // now we can reference individual photos via uid
        lat: coords.lat,
        lon: coords.lon,
        bearing: coords.bearing,
        photoUid: photoUid, // include photo uid for precise navigation
        baseUrl: HILLVIEW_BASE_URL
    });
}

/**
 * Constructs a map navigation URL for internal use
 * @param photo Photo data containing location information and uid
 * @returns Relative URL for internal navigation
 */
export function constructPhotoMapUrl(photo: any): string {
    const coords = extractCoordinates(photo);

    if (!coords) {
        return '/';
    }

    // Construct uid if not present (for UserPhoto objects from hillview backend)
    let photoUid = photo.uid;
    if (!photoUid && photo.id) {
        photoUid = `hillview-${photo.id}`;
    }

    return constructMapUrl({
        lat: coords.lat,
        lon: coords.lon,
        bearing: coords.bearing,
        photoUid: photoUid
    });
}

/**
 * Constructs a user profile URL
 * @param userId User ID
 * @returns Relative URL for user profile page
 */
export function constructUserProfileUrl(userId: string): string {
    return `/users/${userId}`;
}

/**
 * Constructs a user photos API URL
 * @param userId User ID
 * @param cursor Optional pagination cursor
 * @returns API URL for user photos
 */
export function constructUserPhotosUrl(userId: string, cursor?: string): string {
    const baseUrl = `/users/${userId}/photos`;
    return cursor ? `${baseUrl}?cursor=${encodeURIComponent(cursor)}` : baseUrl;
}

/**
 * Opens an external URL in the appropriate way for the current platform
 * - Uses Tauri's openUrl for native app (opens in external browser)
 * - Uses window.open for web platform
 * @param url The URL to open
 */
export async function openExternalUrl(url: string): Promise<void> {
    if (TAURI) {
        // Use Tauri's openUrl to open in external browser
        try {
            await openUrl(url);
        } catch (error) {
            console.error('Failed to open external URL:', error);
            // Fallback to window.open if openUrl fails
            window.open(url, '_blank', 'noopener,noreferrer');
        }
    } else {
        // For web, use window.open
        window.open(url, '_blank', 'noopener,noreferrer');
    }
}
