import { getDevicePhotoUrl } from '$lib/devicePhotoHelper';
import type { PhotoForInfo, FullPhotoInfo } from '$lib/types/photoTypes';

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
