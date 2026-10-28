import { describe, expect, it, vi } from 'vitest';
import { getGalleryImage } from './galleryImage';
import type { PhotoData } from './types/photoTypes';

vi.mock('./devicePhotoHelper', () => ({
	getDevicePhotoUrl: (url: string) => `asset:${url}`,
}));

const image = (url: string, width: number) => ({ url, width, height: width / 2 });
const photo = {
	url: 'thumbnail',
	sizes: { 320: image('small', 320), 1024: image('medium', 1024), full: image('original', 4000) },
} as unknown as PhotoData;

describe('gallery image selection', () => {
	it('selects the smallest sufficient size, using the gallery default width', () => {
		expect(getGalleryImage(photo, 320).url).toBe('small');
		expect(getGalleryImage(photo, 321)).toEqual({ ...photo.sizes![1024], size: '1024' });
		expect(getGalleryImage(photo).url).toBe('medium');
	});

	it('falls back to full, or to the largest available numeric size', () => {
		expect(getGalleryImage(photo, 2000).url).toBe('original');
		const withoutFull = { ...photo, sizes: { 320: photo.sizes![320], 1024: photo.sizes![1024] } };
		expect(getGalleryImage(withoutFull, 2000).url).toBe('medium');
	});

	it('handles unsized photos and converts device URLs just like the gallery', () => {
		expect(getGalleryImage({ ...photo, sizes: undefined }).url).toBe('thumbnail');
		expect(getGalleryImage({ ...photo, is_device_photo: true }).url).toBe('asset:thumbnail');
		expect(getGalleryImage({ ...photo, is_device_photo: true, url: '' }).url).toBe('asset:medium');
	});
});
