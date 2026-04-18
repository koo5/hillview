/**
 * SSR-safe URL utilities for Hillview frontend
 * Contains only functions that can safely run during server-side rendering
 */

/**
 * Base URL for production Hillview site
 */
export const HILLVIEW_BASE_URL = 'https://hillview.cz';

/**
 * Parses photo UID from URL parameter
 * @param photoParam - The raw photo parameter from URL
 * @returns Decoded photo UID or null if invalid
 */
export function parsePhotoUid(photoParam: string | null): string | null {
    if (!photoParam) return null;

    try {
        return decodeURIComponent(photoParam);
    } catch {
        return null;
    }
}

/**
 * Extracts source and ID from photo UID
 * @param photoUid - The photo UID in format "source-id"
 * @returns Object with source and id, or null if invalid format
 */
export function parsePhotoUidParts(photoUid: string): { source: string; id: string } | null {
    const dashIdx = photoUid.indexOf('-');
    if (dashIdx <= 0 || dashIdx === photoUid.length - 1) return null;

    return {
        source: photoUid.slice(0, dashIdx),
        id: photoUid.slice(dashIdx + 1)
    };
}

/**
 * Constructs a relative map-view URL pointing at a specific photo.
 * Pure (no store access) so it is safe for SSR and sitemap generation.
 */
export function constructPhotoMapPath(opts: {
    uid: string;
    latitude: number | null;
    longitude: number | null;
    bearing?: number | null;
    zoom?: number;
}): string {
    const { uid, latitude, longitude, bearing, zoom = 18 } = opts;
    if (latitude == null || longitude == null) {
        return `/?photo=${encodeURIComponent(uid)}`;
    }
    let url = `/?lat=${latitude}&lon=${longitude}&zoom=${zoom}`;
    if (bearing != null) url += `&bearing=${bearing}`;
    url += `&photo=${encodeURIComponent(uid)}`;
    return url;
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