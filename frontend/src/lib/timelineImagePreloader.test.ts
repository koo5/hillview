import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TimelineImagePreloader } from './timelineImagePreloader';
import type { PhotoData } from './types/photoTypes';

let requests: FakeImage[];
class FakeImage {
	src = '';
	fetchPriority = '';
	onload: (() => void) | null = null;
	onerror: (() => void) | null = null;
	removeAttribute = vi.fn();
	constructor() { requests.push(this); }
}

const photos = Array.from({ length: 9 }, (_, i) => ({
	uid: `hillview-${i}`,
	url: `thumb-${i}`,
	sizes: {
		320: { url: `small-${i}`, width: 320, height: 240 },
		1024: { url: `gallery-${i}`, width: 1024, height: 768 },
	},
} as unknown as PhotoData));

function state(cursor = 3) {
	return {
		active: true,
		photos,
		cursor,
		availablePhotos: photos,
		clientWidth: 800,
		frontUid: photos[cursor].uid,
		readyUrl: `gallery-${cursor}`,
		saveData: false,
	};
}

describe('timeline image preloading', () => {
	let preloader: TimelineImagePreloader;
	beforeEach(() => {
		requests = [];
		vi.stubGlobal('Image', FakeImage);
		preloader = new TimelineImagePreloader();
	});
	afterEach(() => {
		preloader.dispose();
		vi.unstubAllGlobals();
	});

	it('loads matching gallery URLs serially, next then previous then another ahead', () => {
		preloader.update(state());
		expect(requests.map(r => r.src)).toEqual(['gallery-4']);
		expect(requests[0].fetchPriority).toBe('low');
		requests[0].onload!();
		expect(requests.map(r => r.src)).toEqual(['gallery-4', 'gallery-2']);
		requests[1].onload!();
		expect(requests.map(r => r.src)).toEqual(['gallery-4', 'gallery-2', 'gallery-5']);
		requests[2].onload!();
		preloader.update(state());
		expect(requests).toHaveLength(3);
	});

	it('waits for a visible, loaded current image at the selected resolution', () => {
		preloader.update({ ...state(), readyUrl: undefined });
		preloader.update({ ...state(), readyUrl: 'small-3' });
		preloader.update({ ...state(), frontUid: 'hillview-0' });
		preloader.update({ ...state(), clientWidth: undefined });
		expect(requests).toHaveLength(0);
		preloader.update(state());
		expect(requests).toHaveLength(1);
	});

	it('also remembers images already loaded by the gallery', () => {
		preloader.update(state());
		preloader.update(state(4));
		requests[0].onload!();
		expect(requests[1].src).toBe('gallery-5');
		requests[1].onload!();
		expect(requests[2].src).toBe('gallery-6');
		requests[2].onload!();
		expect(requests.map(r => r.src)).not.toContain('gallery-3');
	});

	it('waits for worker metadata instead of downloading timeline thumbnails', () => {
		preloader.update({ ...state(), availablePhotos: [photos[3]] });
		expect(requests).toHaveLength(0);
		preloader.update({ ...state(), availablePhotos: [photos[3], photos[4]] });
		expect(requests[0].src).toBe('gallery-4');
		requests[0].onload!();
		preloader.update(state());
		expect(requests[1].src).toBe('gallery-2');
	});

	it('replaces queued work on jumps and prioritizes the new direction', () => {
		preloader.update(state());
		preloader.update(state(7));
		// The one request already in flight may finish; no intervening images start.
		expect(requests).toHaveLength(1);
		requests[0].onload!();
		expect(requests[1].src).toBe('gallery-8');
		preloader.update(state(6));
		requests[1].onload!();
		expect(requests[2].src).toBe('gallery-5');
	});

	it('keeps direction when a chunk is prepended and the cursor shifts', () => {
		preloader.update({ ...state(), readyUrl: undefined });
		preloader.update({ ...state(2), readyUrl: undefined });
		preloader.update({ ...state(2), photos: [photos[8], ...photos], cursor: 3 });
		expect(requests[0].src).toBe('gallery-1');
	});

	it('changes resolution after resize and respects data saving and timeline closure', () => {
		preloader.update({ ...state(), saveData: true });
		preloader.update({ ...state(), active: false });
		expect(requests).toHaveLength(0);
		preloader.update({ ...state(), clientWidth: 300, readyUrl: 'small-3' });
		expect(requests[0].src).toBe('small-4');
		preloader.update({ ...state(), active: false });
		requests[0].onload!();
		expect(requests).toHaveLength(1);
	});

	it('continues after errors without repeatedly retrying a broken candidate', () => {
		preloader.update(state());
		requests[0].onerror!();
		expect(requests[1].src).toBe('gallery-2');
		preloader.update(state());
		requests[1].onload!();
		requests[2].onload!();
		preloader.update(state());
		expect(requests).toHaveLength(3);
	});

	it('releases handlers and queued work when the gallery is destroyed', () => {
		preloader.update(state());
		preloader.dispose();
		expect(requests[0].onload).toBeNull();
		expect(requests[0].onerror).toBeNull();
		expect(requests[0].removeAttribute).toHaveBeenCalledWith('src');
		preloader.update(state(5));
		expect(requests).toHaveLength(1);
	});
});
