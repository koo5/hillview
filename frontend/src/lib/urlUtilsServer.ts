/**
 * SSR-safe URL utilities for Hillview frontend
 * Contains only functions that can safely run during server-side rendering
 */

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
    const parts = photoUid.split('-', 2);
    if (parts.length !== 2) return null;

    return {
        source: parts[0],
        id: parts[1]
    };
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