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
