import type { PhotoData } from './types/photoTypes';
import { getDevicePhotoUrl } from './devicePhotoHelper';

export interface GalleryImage {
	url: string;
	size?: string;
	width?: number;
	height?: number;
}

/** Use the same resolution for displayed photos and speculative image requests. */
export function getGalleryImage(photo: PhotoData, clientWidth = 500): GalleryImage {
	if (photo.is_device_photo && photo.url) {
		return { url: getDevicePhotoUrl(photo.url) };
	}
	if (!photo.sizes) return { url: photo.url };

	const sizes = Object.keys(photo.sizes)
		.filter(size => /^\d+$/.test(size))
		.sort((a, b) => Number(a) - Number(b));
	const size = sizes.find(size => Number(size) >= clientWidth)
		?? (photo.sizes.full ? 'full' : sizes[sizes.length - 1]);
	const image = photo.sizes[size];
	if (!image) return { url: '', size: 'full', width: 0, height: 0 };
	return {
		...image,
		size,
		url: photo.is_device_photo ? getDevicePhotoUrl(image.url) : image.url,
	};
}
