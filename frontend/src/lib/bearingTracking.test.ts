/**
 * updateBearingWithPhoto: turning to a photo writes its bearing; choosing a
 * heading-less photo keeps the view still and records only the choice.
 */
import { describe, it, expect, vi } from 'vitest';
import { get } from 'svelte/store';

vi.mock('$lib/compass.svelte', () => ({ enableCompass: vi.fn(), disableCompass: vi.fn() }));
vi.mock('$lib/gpsOrientation.svelte', () => ({ enableGpsOrientation: vi.fn(), disableGpsOrientation: vi.fn() }));

import { updateBearingWithPhoto } from './bearingTracking';
import { bearingState, updateBearing } from './mapState';

describe('updateBearingWithPhoto', () => {
	it('turning to a photo with a heading writes that heading and the choice', () => {
		updateBearing(10, 'test');
		updateBearingWithPhoto({ uid: 'hillview-x', bearing: 250 } as any);
		expect(get(bearingState).bearing).toBe(250);
		expect(get(bearingState).photoUid).toBe('hillview-x');
	});

	it('choosing a heading-less photo keeps the view still but records the choice', () => {
		updateBearing(77, 'test');
		updateBearingWithPhoto({ uid: 'panoramax-y', bearing: 0, has_bearing: false } as any);
		expect(get(bearingState).bearing).toBe(77);
		expect(get(bearingState).photoUid).toBe('panoramax-y');
	});

	it('the choice drops on the next plain bearing write, like any selection', () => {
		updateBearingWithPhoto({ uid: 'panoramax-y', bearing: 0, has_bearing: false } as any);
		updateBearing(90, 'map');
		expect(get(bearingState).photoUid).toBeUndefined();
	});
});

import { photosInRange, setUrlRequestedPhoto, computePhotoInFront } from './mapState';

describe('URL photo selection', () => {
	const target = { uid: 'hillview-target', bearing: 250, featured: true } as any;
	it('resolves a UID-only link when its photo arrives, once', () => {
		photosInRange.set([]);
		updateBearing(10, 'test');
		setUrlRequestedPhoto(target.uid);
		photosInRange.set([target]);
		expect(get(bearingState).bearing).toBe(250);
		expect(computePhotoInFront([target, { uid: 'other', bearing: 10 }], get(bearingState))?.uid).toBe(target.uid);
		updateBearing(80, 'map');
		photosInRange.set([target]);
		expect(get(bearingState).bearing).toBe(80);
	});
	it('resolves an already loaded photo and preserves an explicit heading, including zero', () => {
		photosInRange.set([target]);
		setUrlRequestedPhoto(target.uid);
		expect(get(bearingState).bearing).toBe(250);
		setUrlRequestedPhoto(target.uid, 0);
		expect(get(bearingState).bearing).toBe(0);
	});
	it('does not undo a user turn while waiting for the requested photo', () => {
		photosInRange.set([]);
		setUrlRequestedPhoto(target.uid);
		updateBearing(90, 'map');
		photosInRange.set([target]);
		expect(get(bearingState).bearing).toBe(90);
		expect(get(bearingState).photoUid).toBeUndefined();
	});
	it('keeps the current heading for a heading-less requested photo', () => {
		photosInRange.set([]);
		updateBearing(77, 'map');
		setUrlRequestedPhoto(target.uid);
		photosInRange.set([{ ...target, has_bearing: false }]);
		expect(get(bearingState).bearing).toBe(77);
		expect(get(bearingState).photoUid).toBe(target.uid);
	});
});
