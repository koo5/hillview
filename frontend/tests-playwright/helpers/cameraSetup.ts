/**
 * Camera setup helpers for Playwright tests.
 *
 * Pre-seeds localStorage so the camera button is visible (needs debug_enabled)
 * and location/bearing data is available for capture.
 */

import type { Page } from '@playwright/test';

/** Seed localStorage with appSettings, spatialState, and bearingState for camera tests. */
export function addCameraInitScript(page: Page) {
	return page.addInitScript(() => {
		localStorage.setItem('appSettings', JSON.stringify({
			debug: 0,
			debug_enabled: true,
			activity: 'view'
		}));
		localStorage.setItem('spatialState', JSON.stringify({
			center: { lat: 50.11692, lng: 14.48837 },
			zoom: 20,
			bounds: null,
			range: 1000,
			source: 'map'
		}));
		localStorage.setItem('bearingState', JSON.stringify({
			bearing: 141,
			source: 'map',
			accuracy_level: null
		}));
	});
}
