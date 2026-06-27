import { test, expect } from './fixtures';
import { loginAs, logoutUser } from './helpers/testUsers';
import { addCaptureInit, ensureAutoUpload, captureAt, waitUploadedAtCoord, openMap, clickMarker, openTimelineAnchoredOn } from './helpers/captureSeed';

/**
 * Timeline panel: refresh button (cross-user re-anchor) + cursor-follow. Photos are
 * capture-seeded at distinct positions so each is an individually clickable marker (see
 * helpers/captureSeed for the seeding rationale).
 */

// Distinct positions (~140m apart) so each photo is an individually clickable
// marker. A1/A2 belong to user `test` (the walk anchor + an in-window sibling);
// B1 belongs to `testuser` (a different owner → always out of test's window).
const CENTER = { lat: 50.1156, lng: 14.494 };
const A1 = { lat: 50.115, lng: 14.4932 };
const A2 = { lat: 50.1152, lng: 14.4952 };
const B1 = { lat: 50.1163, lng: 14.4943 };

// Two `admin` photos ~2km apart, for the stepping regression: centred on S1, S2 is far
// off-screen / out of range — the case where the cursor-follow guard must not hijack the
// step and snap the cursor back into the in-range set.
const S1 = { lat: 50.1, lng: 14.47 };
const S2 = { lat: 50.118, lng: 14.47 };

// Server photo ids, resolved during setup and reused by the behavior tests.
let idA1 = '';
let idA2 = '';
let idB1 = '';
let idS1 = '';
let idS2 = '';

test.describe('Timeline refresh + cursor-follow', () => {
	// Serial: behavior tests reuse the captured photos from setup. Retries absorb the rare
	// streaming-timing flake where the walk anchors on a sibling photo at open.
	test.describe.configure({ mode: 'serial', retries: 2 });

	test.beforeEach(async ({ browserName }) => {
		// Capture pipeline needs the fake camera (Chromium flags) and stores photo
		// Blobs in IndexedDB (WebKitGTK can't); both make this Chromium-only.
		test.skip(browserName !== 'chromium', 'Capture/fake-camera is Chromium-only');
	});

	test('setup: capture photos for two users at distinct positions', async ({ page, testUsers }) => {
		test.setTimeout(300_000);
		await addCaptureInit(page);

		// Capture + wait per photo: the capture button is disabled while an upload is in
		// flight (frontendBusy), and the next capture's page reload would interrupt that
		// upload — so let each one settle before capturing the next.

		// User A (`test`): two photos → the walk anchor + an in-window sibling.
		await loginAs(page, 'test', testUsers.passwords.test);
		await ensureAutoUpload(page);
		await captureAt(page, A1.lat, A1.lng);
		idA1 = await waitUploadedAtCoord(page, A1);
		await captureAt(page, A2.lat, A2.lng);
		idA2 = await waitUploadedAtCoord(page, A2);

		// User B (`testuser`): one photo at a separate spot → an out-of-window pick.
		await logoutUser(page);
		await loginAs(page, 'testuser', testUsers.passwords.testuser);
		await ensureAutoUpload(page);
		await captureAt(page, B1.lat, B1.lng);
		idB1 = await waitUploadedAtCoord(page, B1);

		// User C (`admin`): two photos ~2km apart for the stepping regression.
		await logoutUser(page);
		await loginAs(page, 'admin', testUsers.passwords.admin);
		await ensureAutoUpload(page);
		await captureAt(page, S1.lat, S1.lng);
		idS1 = await waitUploadedAtCoord(page, S1);
		await captureAt(page, S2.lat, S2.lng);
		idS2 = await waitUploadedAtCoord(page, S2);

		expect(new Set([idA1, idA2, idB1, idS1, idS2]).size).toBe(5);
	});

	test('selecting an in-window photo moves the cursor (no refresh button)', async ({ page, testUsers }) => {
		test.setTimeout(180_000);
		await loginAs(page, 'test', testUsers.passwords.test);
		await openMap(page, CENTER, [idA1, idA2, idB1]);

		// Anchor the walk on A1 (oldest of test's two photos → row 1 / 2).
		await openTimelineAnchoredOn(page, idA1);
		const status = page.getByTestId('timeline-status');
		await expect(status).toHaveText('1 / 2', { timeout: 11 * 15000 });
		await expect(page.getByTestId('timeline-refresh')).toHaveCount(0);

		// Select the other in-window photo on the map → the cursor follows to it.
		await clickMarker(page, idA2);
		await expect(status).toHaveText('2 / 2', { timeout: 11 * 15000 });
		// Still in-window → no refresh button.
		await expect(page.getByTestId('timeline-refresh')).toHaveCount(0);
	});

	test('selecting another user\'s photo shows refresh; clicking it switches the walk', async ({ page, testUsers }) => {
		test.setTimeout(180_000);
		await loginAs(page, 'test', testUsers.passwords.test);
		await openMap(page, CENTER, [idA1, idA2, idB1]);

		// Anchor on test's photo; the walk tracks only `test`.
		await openTimelineAnchoredOn(page, idA1);
		await expect(page.getByTestId('timeline-status')).toHaveText('1 / 2', { timeout: 11 * 15000 });
		await expect(page.getByTestId('timeline-user')).toHaveText('test');
		await expect(page.getByTestId('timeline-refresh')).toHaveCount(0);

		// Select testuser's photo — outside test's window → refresh button appears,
		// and the cursor does NOT move (it isn't in the loaded walk).
		await clickMarker(page, idB1);
		await expect(page.getByTestId('timeline-refresh')).toBeVisible({ timeout: 11 * 15000 });
		await expect(page.getByTestId('timeline-status')).toHaveText('1 / 2');

		// Refresh re-anchors on the new owner (drop-merge branch): walk switches to
		// testuser, the button clears, and the picked photo is now the in-window anchor.
		await page.getByTestId('timeline-refresh').click();
		await expect(page.getByTestId('timeline-refresh')).toHaveCount(0, { timeout: 11 * 15000 });
		await expect(page.getByTestId('timeline-user')).toHaveText('testuser', { timeout: 11 * 15000 });
		await expect(page.getByTestId('timeline-status')).toHaveText('1 / 1', { timeout: 11 * 15000 });
	});

	test('stepping advances through out-of-range photos without cycling or looping', async ({ page, testUsers }) => {
		test.setTimeout(180_000);
		await loginAs(page, 'admin', testUsers.passwords.admin);
		// Centre on S1; S2 is ~2km away, so it's out of the map's range — the case where
		// the cursor-follow used to drag the cursor back into the in-range set and loop.
		await openMap(page, S1, [idS1]);

		await openTimelineAnchoredOn(page, idS1);
		const status = page.getByTestId('timeline-status');
		await expect(status).toHaveText('1 / 2', { timeout: 11 * 15000 });

		// Step forward onto the out-of-range photo: the cursor must advance and STAY there
		// (the map flies to it) rather than snapping back to S1.
		await page.getByTestId('timeline-next').click();
		await expect(status).toHaveText('2 / 2', { timeout: 11 * 15000 });
		// And back.
		await page.getByTestId('timeline-prev').click();
		await expect(status).toHaveText('1 / 2', { timeout: 11 * 15000 });
	});
});
