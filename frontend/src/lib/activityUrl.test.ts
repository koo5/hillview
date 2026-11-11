import { afterEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

const availability = vi.hoisted(() => ({ worldModeAvailable: true, terrainModeAvailable: true }));
vi.mock('$lib/world', () => availability);
vi.mock('$lib/terrainAvailability', () => availability);
vi.mock('$app/environment', () => ({ browser: true, dev: true }));

vi.hoisted(() => {
	localStorage.setItem('appSettings', JSON.stringify({ debug: 0, debug_enabled: false, activity: 'world' }));
});

import { app, appSettings, parseActivityParam } from './data.svelte';

afterEach(() => {
	availability.worldModeAvailable = true;
	availability.terrainModeAvailable = true;
	vi.unstubAllEnvs();
});

describe('activity URL parameter', () => {
	it('uses 3d for both the URL and the activity', () => {
		const url = new URL('https://hillview.cz/?lat=50.1252096&lon=14.4932864&zoom=20&activity=3d');
		expect(parseActivityParam(url.searchParams.get('activity'))).toBe('3d');
	});

	it('migrates the activity saved by an older build', () => {
		expect(get(appSettings).activity).toBe('3d');
		expect(get(app).activity).toBe('3d');
	});

	it('accepts the other activities and ignores absent or unknown parameters', () => {
		for (const activity of ['view', 'terrain', 'lines', 'capture']) {
			expect(parseActivityParam(activity)).toBe(activity);
		}
		for (const value of [null, '', 'unknown', '__proto__', 'world']) {
			expect(parseActivityParam(value)).toBeNull();
		}
	});

	it('falls back to the photo view when a service is unavailable', () => {
		availability.worldModeAvailable = false;
		availability.terrainModeAvailable = false;
		expect(parseActivityParam('3d')).toBe('view');
		expect(parseActivityParam('terrain')).toBe('view');
	});

	it('respects builds that disable alternate activities', () => {
		vi.stubEnv('VITE_PICS_OFF', 'true');
		expect(parseActivityParam('3d')).toBe('view');
		expect(parseActivityParam('capture')).toBe('view');
	});
});
