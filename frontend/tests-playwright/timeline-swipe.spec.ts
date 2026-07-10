import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAs } from './helpers/testUsers';
import { addCaptureInit, ensureAutoUpload, captureAt, waitNewUpload, openMap, openTimelineAnchoredOn } from './helpers/captureSeed';

/**
 * The timeline cursor follows *swipe / arrow* photo-navigation, not just marker clicks.
 * A swipe on the gallery and the gallery nav arrows share one path —
 *   handleSwipe → turn_to_photo_to → updateBearingWithPhoto(neighbour, 'photo_navigation')
 * — which is the same bearingState convergence the timeline's cursor-follow listens on. We
 * drive it through the nav-arrow button (deterministic; a swipe gesture funnels through the
 * identical handleSwipe call, so this guards the timeline-relevant half of the swipe path).
 *
 * Own spec file so the seed is isolated: two photos for `test`, co-located in an otherwise
 * empty area so both are always in range (each is a navigable neighbour of the other), told
 * apart by capture order rather than coordinate. W1 faces bearing 80, W2 bearing 100, so
 * with the map facing 80 the front photo (= walk anchor) is W1 and its right neighbour W2.
 */
const LOC = { lat: 50.08, lng: 14.43 };

let idW1 = '';
let idW2 = '';

test.describe('Timeline cursor follows swipe / arrow navigation', () => {
	test.describe.configure({ mode: 'serial', retries: 2 });

	test.beforeEach(async ({ browserName }) => {
		test.skip(browserName !== 'chromium', 'Capture/fake-camera is Chromium-only');
	});

	test('setup: capture two navigable photos for one user', async ({ page, testUsers }) => {
		test.setTimeout(240_000);
		await addCaptureInit(page);
		await loginAs(page, 'test', testUsers.passwords.test);
		await ensureAutoUpload(page);
		// Capture + wait per photo (the capture button is disabled while an upload is in
		// flight; the next capture's reload would interrupt it).
		await captureAt(page, LOC.lat, LOC.lng, 80);
		idW1 = await waitNewUpload(page, new Set());
		await captureAt(page, LOC.lat, LOC.lng, 100);
		idW2 = await waitNewUpload(page, new Set([idW1]));
		expect(new Set([idW1, idW2]).size).toBe(2);
	});

	test('arrow / swipe navigation moves the cursor onto the neighbour photo', async ({ page, testUsers }) => {
		test.setTimeout(180_000);
		await loginAs(page, 'test', testUsers.passwords.test);
		// Face bearing 80 so W1 (bearing 80) is the front photo, hence the walk anchor.
		await openMap(page, LOC, [idW1, idW2], 80);

		// Anchor the walk on W1 (the bearing-80 photo).
		await openTimelineAnchoredOn(page, idW1);
		const status = page.getByTestId('timeline-status');
		await expect(status).toHaveText('1 / 2', { timeout: T(15000) });

		// Navigate right to the neighbour — the same handleSwipe path a swipe gesture uses
		// → 'photo_navigation' selection → the cursor follows onto W2.
		await page.getByTestId('gallery-nav-right').click();
		await expect(status).toHaveText('2 / 2', { timeout: T(15000) });
		await expect(page.getByTestId('timeline-refresh')).toHaveCount(0);
	});
});
