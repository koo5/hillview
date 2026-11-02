import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { backgroundLocationTracking, locationTracking } from '$lib/location.svelte';
import { spatialState } from '$lib/mapState';
import { stopFollowing, userMove } from './userMove';

/**
 * A hand move (the map's pan, the 3D world's flight) must win over GPS following: docs/one-state.md. RECON-UI found
 * the next fix landing a flight (ea07 review, 2026-11-02).
 */
describe('userMove', () => {
	beforeEach(() => {
		locationTracking.set(false);
		backgroundLocationTracking.set(false);
	});

	it('while GPS follows, sends tracking to the background (still logging), then writes the point', async () => {
		locationTracking.set(true);
		await userMove({ lat: 50.1, lng: 14.6 });
		expect(get(locationTracking)).toBe(false);
		expect(get(backgroundLocationTracking)).toBe(true);
		expect(get(spatialState).center).toMatchObject({ lat: 50.1, lng: 14.6 });
		expect(get(spatialState).source).toBe('map');
	});

	it('changes nothing about tracking that is off or already in the background', async () => {
		await userMove({ lat: 50.2, lng: 14.7 });
		expect([get(locationTracking), get(backgroundLocationTracking)]).toEqual([false, false]);
		backgroundLocationTracking.set(true);
		stopFollowing();
		expect([get(locationTracking), get(backgroundLocationTracking)]).toEqual([false, true]);
	});
});
