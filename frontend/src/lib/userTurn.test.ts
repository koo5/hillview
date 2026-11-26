import { describe, it, expect, vi, beforeEach } from 'vitest';
import { get } from 'svelte/store';

// the automatic producers, stubbed: what userTurn must stop before it writes
const compass = vi.hoisted(() => ({ enabled: null as any, disable: vi.fn() }));
const gps = vi.hoisted(() => ({ enabled: null as any, adjust: vi.fn() }));
vi.mock('$lib/compass.svelte', async () => {
	const { writable } = await import('svelte/store');
	compass.enabled = writable(false);
	return { compassEnabled: compass.enabled, disableCompass: compass.disable };
});
vi.mock('$lib/gpsOrientation.svelte', async () => {
	const { writable } = await import('svelte/store');
	gps.enabled = writable(false);
	return { gpsOrientationEnabled: gps.enabled, adjustMountOffset: gps.adjust };
});

import { bearingMode, bearingState } from '$lib/mapState';
import { userTurn } from './userTurn';

/**
 * A hand turn (the map's arrow, the 3D world's drag) must win over the automatic producers:
 * docs/tauri-map-ui-contract.md, Bearing writers. RECON-UI found the 3D drag snapped back.
 */
describe('userTurn', () => {
	beforeEach(() => {
		compass.disable.mockClear();
		gps.adjust.mockClear();
		compass.enabled.set(false);
		gps.enabled.set(false);
		bearingMode.set('walking');
	});

	it('stops the compass, then writes the bearing under its own source', () => {
		compass.enabled.set(true);
		userTurn(10, 40, 'world3d');
		expect(compass.disable).toHaveBeenCalledTimes(1);
		expect(get(bearingState).bearing).toBe(40);
		expect(get(bearingState).source).toBe('world3d');
	});

	it('leaves a compass that is already off alone', () => {
		userTurn(10, 20, 'arrow_drag');
		expect(compass.disable).not.toHaveBeenCalled();
		expect(get(bearingState).source).toBe('arrow_drag');
	});

	it('in car mode with GPS orientation, moves the mount offset by the turn instead of writing', () => {
		bearingMode.set('car');
		gps.enabled.set(true);
		const before = get(bearingState);
		userTurn(350, 20, 'world3d');
		expect(gps.adjust).toHaveBeenCalledWith(30);
		expect(get(bearingState)).toEqual(before);
	});
});
