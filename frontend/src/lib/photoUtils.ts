import { getDevicePhotoUrl } from '$lib/devicePhotoHelper';

/**
 * Get the full-size URL for any photo type
 */
export function getFullPhotoUrl(photo: any): string {
	// Case 1: Device photos - use device URL helper
	if (photo.is_device_photo) {
		return getDevicePhotoUrl(photo.url);
	}

	// Case 2: Server photos with sizes - use full size
	if (photo.sizes?.full?.url) {
		return photo.sizes.full.url;
	}

	// Case 3: Fallback - use photo.url
	return photo.url || '';
}

/**
 * Get full-size photo info (URL + dimensions) for zoom view
 */
export function getFullPhotoInfo(photo: any): { url: string; width?: number; height?: number } {
	if (photo.is_device_photo) {
		// Device photos have width/height directly (from metadata)
		return {
			url: getDevicePhotoUrl(photo.url),
			width: photo.width,
			height: photo.height
		};
	}

	// Server photos - get from sizes.full
	if (photo.sizes?.full) {
		return {
			url: photo.sizes.full.url,
			width: photo.sizes.full.width,
			height: photo.sizes.full.height
		};
	}

	// Fallback - just URL, no dimensions
	return {
		url: photo.url || '',
		width: photo.width,
		height: photo.height
	};
}