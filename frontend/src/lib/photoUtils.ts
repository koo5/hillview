import { getDevicePhotoUrl } from '$lib/devicePhotoHelper';
import type {PhotoForInfo, FullPhotoInfo, PhotoData} from '$lib/types/photoTypes';
import { get } from 'svelte/store';
import { sources, type Source } from '$lib/data.svelte';
import { constructUserProfileUrl } from '$lib/urlUtilsServer';

/**
 * Get the full-size URL for any photo type
 */
export function getFullPhotoUrl(photo: PhotoForInfo): string {
	// Case 1: Device photos - use device URL helper
	if (isDevicePhoto(photo)) {
		const photoUrl = 'url' in photo ? photo.url : '';
		return getDevicePhotoUrl(photoUrl);
	}

	// Case 2: Server photos with sizes - use full size
	if (hasSizesProperty(photo) && photo.sizes?.full?.url) {
		return photo.sizes.full.url;
	}

	// Case 3: Fallback - use photo.url if available
	if ('url' in photo) {
		return photo.url || '';
	}

	return '';
}

/**
 * Type guard to check if photo has sizes property (PhotoData or PhotoItemData)
 */
function hasSizesProperty(photo: PhotoForInfo): photo is (PhotoForInfo & { sizes?: Record<string, { url: string; width: number; height: number }> }) {
	return 'sizes' in photo;
}

/**
 * Type guard to check if photo is device photo
 */
function isDevicePhoto(photo: PhotoForInfo): photo is (PhotoForInfo & { is_device_photo: boolean }) {
	return 'is_device_photo' in photo && photo.is_device_photo === true;
}

/**
 * Get full-size photo info (URL + dimensions) for zoom view
 */
export function getFullPhotoInfo(photo: PhotoForInfo): FullPhotoInfo {
	let url: string;
	let width: number | undefined;
	let height: number | undefined;

	// Handle photos with sizes (PhotoData, PhotoItemData)
	if (hasSizesProperty(photo) && photo.sizes?.full) {
		url = photo.sizes.full.url;
		width = photo.sizes.full.width;
		height = photo.sizes.full.height;
	} else {
		// Fallback to direct properties
		url = 'url' in photo ? photo.url : '';
		width = 'width' in photo ? photo.width : undefined;
		height = 'height' in photo ? photo.height : undefined;
	}

	// Handle device photos - convert URL
	if (isDevicePhoto(photo)) {
		url = getDevicePhotoUrl(url);
	}

	return { url, width, height };
}

/**
 * Resolve photo.source (string ID or Source object) to a full Source object
 * by looking up string IDs in the sources store
 */
export function resolvePhotoSource(photoSource: string | Source | undefined): Source | undefined {
	if (!photoSource) return undefined;
	if (typeof photoSource === 'object') return photoSource;
	// It's a string ID - look up in sources store
	const allSources = get(sources);
	return allSources.find(s => s.id === photoSource);
}

// Helper functions to determine photo source and get user info
export function getPhotoSource(photo: PhotoData | null): string | null {
	if (!photo) return null;
	if (typeof photo.source === 'string')
		return photo.source;
	if (!photo.source?.id) throw new Error('photo?.source?.id is missing:' + JSON.stringify(photo));
	return photo.source.id;
}

/**
 * Get the source color for a photo, looking up in sources store if needed
 */
export function getPhotoSourceColor(photo: PhotoData | null): string | undefined {
	if (!photo) return undefined;
	const source = resolvePhotoSource(photo.source);
	return source?.color;
}

/**
 * Get the source name for a photo, looking up in sources store if needed
 */
export function getPhotoSourceName(photo: PhotoData | null): string | undefined {
	if (!photo) return undefined;
	const source = resolvePhotoSource(photo.source);
	return source?.name;
}

/**
 * Get the source ID for a photo (handles both string and Source object)
 */
export function getPhotoSourceId(photo: PhotoData | null): string | undefined {
	if (!photo) return undefined;
	if (typeof photo.source === 'string') return photo.source;
	return photo.source?.id;
}

    // User helper functions
export function getUserId(photo: PhotoData | null): string | null {
        if (!photo) return null;

        // For Mapillary photos, check if creator info exists in the photo data
        if ((photo as any).creator?.id) {
            return (photo as any).creator.id;
        }
        // For Hillview photos, check for owner_id field
        if ((photo as any).owner_id) {
            return (photo as any).owner_id;
        }
        return null;
}


export function getUserName(photo: PhotoData | null): string | null {
	if (!photo) return null;

	// For Mapillary photos, check if creator info exists in the photo data
	if ((photo as any).creator?.username) {
		return (photo as any).creator.username;
	}
	// For Hillview photos, check for owner_username field
	if ((photo as any).owner_username) {
		return (photo as any).owner_username;
	}
	return null;
}

export function formatCapturedAt(photo: PhotoData | null): string | null {
	if (!photo?.captured_at) return null;
	try {
		const date = new Date(photo.captured_at);
		return date.toLocaleString();
	} catch {
		return String(photo.captured_at);
	}
}

export function getPhotoDetailUrl(photo: PhotoData | null): string | null {
	if (!photo) return null;
	// Prefer explicit uid if present; otherwise build from source+id.
	const explicitUid = (photo as any).uid;
	if (explicitUid) return `/photo/${encodeURIComponent(explicitUid)}`;
	const source = getPhotoSource(photo);
	if (source && photo.id) {
		return `/photo/${encodeURIComponent(`${source}-${photo.id}`)}`;
	}
	return null;
}

/**
 * URL to the photo's canonical location on its originating service.
 * Mapillary photos resolve to mapillary.com; Hillview photos resolve to the
 * internal /photo/<uid> detail page (same as `getPhotoDetailUrl`).
 */
export function getCanonicalPhotoUrl(photo: PhotoData | null): string | null {
	if (!photo) return null;
	if (getPhotoSource(photo) === 'mapillary' && photo.id) {
		return `https://www.mapillary.com/app/?pKey=${encodeURIComponent(photo.id)}&focus=photo`;
	}
	return getPhotoDetailUrl(photo);
}

const LICENSE_LABELS: Record<string, string> = {
	'arr': 'All rights reserved',
	'ccbysa4+osm': 'CC BY-SA 4.0 + OSM mapping grant',
	'ccbysa4-mapillary': 'CC BY-SA 4.0 (via Mapillary)',
};

export function getLicenseId(photo: PhotoData | null): string | null {
	if (!photo) return null;
	const explicit = (photo as any).license;
	if (explicit) return explicit;
	// Mapillary's ToS licenses user content under CC BY-SA 4.0.
	if (getPhotoSource(photo) === 'mapillary') return 'ccbysa4-mapillary';
	return null;
}

export function getLicenseLabel(photo: PhotoData | null): string | null {
	const id = getLicenseId(photo);
	if (!id) return null;
	return LICENSE_LABELS[id] ?? id;
}

/**
 * Returns a URL for the photo creator's profile, or undefined if unavailable.
 * Hillview → internal user profile URL. Mapillary → external mapillary.com profile.
 * Used by menu items to enable middle-click / ctrl-click to open in a new tab.
 */
export function getUserProfileUrl(photo: PhotoData | null): string | undefined {
	if (!photo) return undefined;
	const source = getPhotoSource(photo);
	const userId = getUserId(photo);
	if (source === 'hillview' && userId) return constructUserProfileUrl(userId);
	const mapillaryUsername = (photo as any).creator?.username;
	if (source === 'mapillary' && mapillaryUsername) {
		return `https://www.mapillary.com/app/user/${mapillaryUsername}`;
	}
	return undefined;
}
