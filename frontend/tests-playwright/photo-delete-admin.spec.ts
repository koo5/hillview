import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { recreateTestUsers, loginAs, logoutUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { ensureSourceEnabled } from './helpers/sourceHelpers';
import { getUserToken, BACKEND_URL } from './helpers/adminAuth';

type Page = import('@playwright/test').Page;

// testPhotos[0] is geotagged at these coordinates (see hide-user.spec.ts).
const MAP_URL = '/?lat=50.1153&lon=14.4938&zoom=18';

/** Navigate to the map at the test photo GPS coords and enable the Hillview source. */
async function navigateToMap(page: Page) {
	await page.goto(MAP_URL);
	await ensureSourceEnabled(page, 'hillview', true);
}

/** Read the id of the front gallery photo (waits for it to load). */
async function getFrontPhotoId(page: Page): Promise<string> {
	const mainPhoto = page.locator('[data-testid="main-photo"].front');
	await mainPhoto.waitFor({ state: 'visible', timeout: T(60000) });
	const data = await mainPhoto.evaluate((el) => JSON.parse(el.getAttribute('data-photo') || '{}'));
	return data.id as string;
}

/** Fetch moderation-audit entries for a photo id via the admin/moderator API. */
async function apiAuditEntriesFor(token: string, photoId: string): Promise<any[]> {
	const res = await fetch(`${BACKEND_URL}/api/photos/moderation-audit?limit=200`, {
		headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
	});
	if (!res.ok) throw new Error(`Failed to read moderation audit: ${res.status}`);
	const body = await res.json();
	return (body.entries || []).filter((e: any) => e.photo_id === photoId);
}

test.describe('Admin photo deletion', () => {
	// Each test uploads photos and mutates moderation state — needs isolation.
	test.beforeEach(async () => {
		await recreateTestUsers();
	});

	test('regular user does not see the Delete photo option', async ({ page, testUsers }) => {
		test.setTimeout(120_000);

		// A regular user uploads and views their own photo on the map.
		await loginAs(page, 'test', testUsers.passwords.test);
		await uploadPhoto(page, testPhotos[0]);

		await navigateToMap(page);
		await getFrontPhotoId(page);

		// Open the photo actions menu — the Delete item must NOT be present.
		await page.locator('[data-testid="photo-actions-menu"]').click();
		await expect(page.locator('[data-testid="menu-flag"]')).toBeVisible();
		await expect(page.locator('[data-testid="menu-delete-photo"]')).toHaveCount(0);
	});

	test('admin deletes another user\'s photo from the menu and it is audited', async ({ page, testUsers }) => {
		test.setTimeout(180_000);

		// Step 1: 'test' uploads a geotagged photo.
		await loginAs(page, 'test', testUsers.passwords.test);
		await uploadPhoto(page, testPhotos[0]);
		await logoutUser(page);

		// Step 2: 'admin' logs in and opens the map on test's photo.
		await loginAs(page, 'admin', testUsers.passwords.admin);
		await navigateToMap(page);
		const photoId = await getFrontPhotoId(page);

		// Step 3: The admin sees and clicks the Delete photo action.
		await page.locator('[data-testid="photo-actions-menu"]').click();
		await page.locator('[data-testid="menu-delete-photo"]').click();

		// Step 4: Confirm in the dialog with a reason.
		await expect(page.locator('[data-testid="delete-photo-dialog"]')).toBeVisible();
		await page.locator('[data-testid="delete-photo-reason"]').fill('e2e: moderation delete');
		await page.locator('[data-testid="delete-photo-confirm"]').click();
		await expect(page.locator('[data-testid="delete-photo-dialog"]')).not.toBeVisible({ timeout: T(10000) });

		// Step 5: The deletion is recorded in the moderation audit.
		const adminToken = await getUserToken('admin', testUsers.passwords.admin);
		const entries = await apiAuditEntriesFor(adminToken, photoId);
		expect(entries).toHaveLength(1);
		expect(entries[0].action).toBe('delete');
		expect(entries[0].actor_username).toBe('admin');
		expect(entries[0].photo_owner_username).toBe('test');
		expect(entries[0].reason).toBe('e2e: moderation delete');
	});
});
