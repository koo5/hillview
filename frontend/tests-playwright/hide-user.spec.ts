import { test, expect } from './fixtures';
import { createTestUsers, loginAs, loginAsTestUser, logoutUser } from './helpers/testUsers';

import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { ensureSourceEnabled } from './helpers/sourceHelpers';
import { getUserToken } from './helpers/adminAuth';

const BACKEND_URL = 'http://localhost:8055';

/** List hidden users for a given user (via API). */
async function apiGetHiddenUsers(token: string): Promise<any[]> {
	const res = await fetch(`${BACKEND_URL}/api/hidden/users`, {
		headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
	});
	if (!res.ok) throw new Error(`Failed to get hidden users: ${res.status}`);
	return res.json();
}

/** Hide a user via API (shortcut for setup). */
async function apiHideUser(
	token: string,
	targetUserId: string,
	targetUserSource: string = 'hillview',
	reason: string = 'test hide',
): Promise<void> {
	const res = await fetch(`${BACKEND_URL}/api/hidden/users`, {
		method: 'POST',
		headers: {
			Authorization: `Bearer ${token}`,
			'Content-Type': 'application/json',
		},
		body: JSON.stringify({
			target_user_source: targetUserSource,
			target_user_id: targetUserId,
			reason,
		}),
	});
	if (!res.ok) throw new Error(`Failed to hide user: ${res.status}`);
}

/** Navigate to another user's profile page. Returns the userId from the URL. */
async function goToOtherUserProfile(page: any): Promise<string> {
	await page.goto('/users');
	await page.waitForLoadState('networkidle');

	// Find a user card that isn't the logged-in user ('test')
	const otherCard = page.locator('[data-testid^="user-card-"]:not([data-testid="user-card-test"])');
	await expect(otherCard.first()).toBeVisible({ timeout: 10000 });
	await otherCard.first().click();
	await page.waitForURL(/\/users\/[^/]+$/);
	await page.waitForLoadState('networkidle');

	const url = page.url();
	const userId = url.split('/users/')[1];
	return userId;
}

test.describe('Hide User', () => {
	// Tests hide/unhide users — need per-test isolation
	test.beforeEach(async () => {
		await createTestUsers();
	});

	test('user profile page shows hide button when authenticated', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);
		await goToOtherUserProfile(page);

		await expect(page.locator('[data-testid="user-page-hide-user"]')).toBeVisible();
	});

	test('user profile page hides button on own profile', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		// Navigate to own profile via users list
		await page.goto('/users');
		await page.waitForLoadState('networkidle');

		const ownCard = page.locator('[data-testid="user-card-test"]');
		if (await ownCard.count() > 0) {
			await ownCard.click();
			await page.waitForURL(/\/users\/[^/]+$/);
			await page.waitForLoadState('networkidle');

			await expect(page.locator('[data-testid="user-page-hide-user"]')).not.toBeVisible();
		}
	});

	test('user profile page hides button when not authenticated', async ({ page }) => {
		await page.goto('/users');
		await page.waitForLoadState('networkidle');

		const userCards = page.locator('[data-testid^="user-card-"]');
		if (await userCards.count() > 0) {
			await userCards.first().click();
			await page.waitForURL(/\/users\/[^/]+$/);
			await page.waitForLoadState('networkidle');

			await expect(page.locator('[data-testid="user-page-hide-user"]')).not.toBeVisible();
		}
	});

	test('hide user dialog opens and can be cancelled', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);
		await goToOtherUserProfile(page);

		// Open dialog
		await page.locator('[data-testid="user-page-hide-user"]').click();
		await expect(page.locator('[data-testid="hide-user-dialog"]')).toBeVisible();

		// Cancel
		await page.locator('[data-testid="hide-user-cancel"]').click();
		await expect(page.locator('[data-testid="hide-user-dialog"]')).not.toBeVisible();

		// Verify nothing was hidden via API
		const token = await getUserToken('test', testUsers.passwords.test);
		const hidden = await apiGetHiddenUsers(token);
		expect(hidden).toHaveLength(0);
	});

	test('hide user dialog submits successfully', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);
		const targetUserId = await goToOtherUserProfile(page);

		// Open dialog
		await page.locator('[data-testid="user-page-hide-user"]').click();
		await expect(page.locator('[data-testid="hide-user-dialog"]')).toBeVisible();

		// Fill reason and submit
		await page.locator('[data-testid="hide-user-reason"]').fill('test reason');
		await page.locator('[data-testid="hide-user-confirm"]').click();

		// Dialog should close
		await expect(page.locator('[data-testid="hide-user-dialog"]')).not.toBeVisible({ timeout: 10000 });

		// Verify via API
		const token = await getUserToken('test', testUsers.passwords.test);
		const hidden = await apiGetHiddenUsers(token);
		expect(hidden.length).toBeGreaterThan(0);
		const match = hidden.find((h: any) => h.target_user_id === targetUserId);
		expect(match).toBeTruthy();
		expect(match.reason).toBe('test reason');
	});

	test('hidden user appears on /hidden page', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		// Hide a user via the UI
		const targetUserId = await goToOtherUserProfile(page);
		await page.locator('[data-testid="user-page-hide-user"]').click();
		await page.locator('[data-testid="hide-user-confirm"]').click();
		await expect(page.locator('[data-testid="hide-user-dialog"]')).not.toBeVisible({ timeout: 10000 });

		// Navigate to /hidden and switch to users tab
		await page.goto('/hidden');
		await page.waitForLoadState('networkidle');
		await page.locator('[data-testid="users-tab"]').click();

		// Verify the hidden user entry is listed
		const hiddenUserItem = page.locator('[data-testid="hidden-user-item"]');
		await expect(hiddenUserItem.first()).toBeVisible({ timeout: 10000 });
	});

	test('unhide user from /hidden page', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		// Hide a user via API shortcut
		const token = await getUserToken('test', testUsers.passwords.test);

		// Get another user's ID
		await page.goto('/users');
		await page.waitForLoadState('networkidle');
		const otherCard = page.locator('[data-testid^="user-card-"]:not([data-testid="user-card-test"])');
		await expect(otherCard.first()).toBeVisible({ timeout: 10000 });
		await otherCard.first().click();
		await page.waitForURL(/\/users\/[^/]+$/);
		const targetUserId = page.url().split('/users/')[1];

		// Hide via API
		await apiHideUser(token, targetUserId);

		// Go to /hidden page
		await page.goto('/hidden');
		await page.waitForLoadState('networkidle');
		await page.locator('[data-testid="users-tab"]').click();

		// Verify the hidden user is listed
		const hiddenUserItem = page.locator('[data-testid="hidden-user-item"]');
		await expect(hiddenUserItem.first()).toBeVisible({ timeout: 10000 });

		// Click unhide
		await page.locator('[data-testid="unhide-user-button"]').first().click();

		// Verify it's gone from the list
		await expect(hiddenUserItem).not.toBeVisible({ timeout: 10000 });

		// Verify via API
		const hidden = await apiGetHiddenUsers(token);
		expect(hidden).toHaveLength(0);
	});
});

// ─── Full Flow: Upload → Hide → Verify Disappears ─────────────────────

type Page = import('@playwright/test').Page;

const MAP_URL = '/?lat=50.1153&lon=14.4938&zoom=18';

/** Navigate to the map at the test photo GPS coords and enable Hillview source. */
async function navigateToMap(page: Page) {
	await page.goto(MAP_URL);
	await page.waitForLoadState('networkidle');
	await ensureSourceEnabled(page, 'hillview', true);
}

/**
 * Branded type for Hillview user IDs (UUIDs) to prevent mixing up
 * with photo IDs, usernames, or other string identifiers.
 */
type HillviewUserId = string & { readonly __brand: 'HillviewUserId' };

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Validate and brand a string as a HillviewUserId. */
function asHillviewUserId(value: string, source: string): HillviewUserId {
	if (!value) throw new Error(`Empty user ID from ${source}`);
	if (!UUID_RE.test(value)) {
		throw new Error(`User ID from ${source} is not a UUID: "${value}"`);
	}
	return value as HillviewUserId;
}

/**
 * Extract the owner user ID from photo JSON data.
 *
 * The backend uses different shapes depending on context:
 *   - Map photos (hillview_routes): `{ creator: { id, username } }`
 *   - Activity/user pages:          `{ owner_id, owner_username }`
 *
 * This mirrors the extraction logic in PhotoActionsMenu.getUserId().
 */
function extractOwnerId(photoData: any, source: string): HillviewUserId {
	const raw = photoData.creator?.id ?? photoData.owner_id;
	console.log(`  extractOwnerId(${source}): creator.id=${photoData.creator?.id} owner_id=${photoData.owner_id} → ${raw}`);
	return asHillviewUserId(raw, source);
}

/** Extract owner username from photo JSON data (same dual-path logic). */
function extractOwnerUsername(photoData: any): string | undefined {
	return photoData.creator?.username ?? photoData.owner_username;
}

/** Read owner info from the currently displayed gallery photo. */
async function getPhotoOwner(page: Page): Promise<{ photoId: string; ownerId: HillviewUserId; ownerUsername: string | undefined }> {
	const mainPhoto = page.locator('[data-testid="main-photo"].front');
	await mainPhoto.waitFor({ state: 'visible', timeout: 30000 });
	const data = await mainPhoto.evaluate((el) => {
		return JSON.parse(el.getAttribute('data-photo') || '{}');
	});
	return {
		photoId: data.id,
		ownerId: extractOwnerId(data, 'gallery main-photo'),
		ownerUsername: extractOwnerUsername(data),
	};
}

/** Navigate gallery until we find a photo from the given user, or throw. */
async function navigateToPhotoByUser(page: Page, targetOwnerId: HillviewUserId, maxSteps = 5) {
	for (let i = 0; i < maxSteps; i++) {
		const owner = await getPhotoOwner(page);
		console.log(`  gallery[${i}]: photo=${owner.photoId} owner=${owner.ownerId} (${owner.ownerUsername}), looking for ${targetOwnerId}`);
		if (owner.ownerId === targetOwnerId) return;

		const navRight = page.locator('[data-testid="gallery-nav-right"]');
		if (await navRight.isVisible()) {
			await navRight.click();
			await page.waitForTimeout(500);
		} else {
			break;
		}
	}
	const current = await getPhotoOwner(page);
	expect(current.ownerId).toBe(targetOwnerId);
}

/**
 * Assert that a photo IS visible (map works) but it does NOT belong to the hidden user.
 * This is stronger than asserting "no photo" — the control photo proves the source loads.
 */
async function assertPhotoVisibleButNotFromUser(page: Page, hiddenOwnerId: HillviewUserId) {
	await page.waitForTimeout(3000);
	const mainPhoto = page.locator('[data-testid="main-photo"]');
	await mainPhoto.waitFor({ state: 'visible', timeout: 15000 });
	const data = await mainPhoto.evaluate((el) => {
		return JSON.parse(el.getAttribute('data-photo') || '{}');
	});
	const visibleOwnerId = extractOwnerId(data, 'assertPhotoVisibleButNotFromUser');
	const visibleOwnerUsername = extractOwnerUsername(data);
	console.log(`  assertPhotoVisibleButNotFromUser: visible photo=${data.id} owner=${visibleOwnerId} (${visibleOwnerUsername}), hidden=${hiddenOwnerId}`);
	expect(visibleOwnerId).not.toBe(hiddenOwnerId);
}

interface HideVariant {
	name: string;
	hideAction: (page: Page, uploaderUserId: HillviewUserId) => Promise<void>;
}

const hideVariants: HideVariant[] = [
	{
		name: 'via photo menu',
		hideAction: async (page: Page, _uploaderUserId: HillviewUserId) => {
			// We're on the map page with the photo visible — open the actions menu
			await page.locator('[data-testid="photo-actions-menu"]').click();
			await page.locator('[data-testid="menu-hide-user"]').click();
			await expect(page.locator('[data-testid="hide-user-dialog"]')).toBeVisible();
			await page.locator('[data-testid="hide-user-reason"]').fill('hiding via photo menu');
			await page.locator('[data-testid="hide-user-confirm"]').click();
			await expect(page.locator('[data-testid="hide-user-dialog"]')).not.toBeVisible({ timeout: 10000 });
		},
	},
	{
		name: 'via user page',
		hideAction: async (page: Page, uploaderUserId: HillviewUserId) => {
			await page.goto(`/users/${uploaderUserId}`);
			await page.waitForLoadState('networkidle');
			await page.locator('[data-testid="user-page-hide-user"]').click();
			await expect(page.locator('[data-testid="hide-user-dialog"]')).toBeVisible();
			await page.locator('[data-testid="hide-user-reason"]').fill('hiding via user page');
			await page.locator('[data-testid="hide-user-confirm"]').click();
			await expect(page.locator('[data-testid="hide-user-dialog"]')).not.toBeVisible({ timeout: 10000 });
		},
	},
];

test.describe('Hide User - Full Flow', () => {
	// Each variant uploads photos + hides users — need per-test isolation
	test.beforeEach(async () => {
		await createTestUsers();
	});

	for (const variant of hideVariants) {
		test(`${variant.name}: upload → hide → verify photo gone → reload → verify still gone`, async ({ page, testUsers }) => {
			test.setTimeout(180_000);
			// Step 1: Login as 'test' (target) and upload a geotagged photo
			await loginAs(page, 'test', testUsers.passwords.test);
			await uploadPhoto(page, testPhotos[0]);
			await logoutUser(page);

			// Step 2: Login as 'admin' (control) and upload a different photo at the same location
			await loginAs(page, 'admin', testUsers.passwords.admin);
			await uploadPhoto(page, testPhotos[1]);
			await logoutUser(page);

			// Step 3: Login as 'testuser' (observer)
			await loginAs(page, 'testuser', testUsers.passwords.testuser);

			// Step 4: Get target user ID from /users page
			await page.goto('/users');
			await page.waitForLoadState('networkidle');
			await page.locator('[data-testid="user-card-test"]').click();
			await page.waitForURL(/\/users\/[^/]+$/);
			const targetOwnerIdFromUrl = page.url().split('/users/')[1];
			const targetOwnerId = asHillviewUserId(targetOwnerIdFromUrl, '/users/[id] URL param');
			console.log(`  target user ID (from URL): ${targetOwnerId}`);

			// Step 5: Navigate to map, ensure we're viewing target user's photo
			await navigateToMap(page);
			await navigateToPhotoByUser(page, targetOwnerId);

			// Step 6: Hide the target user via the chosen method
			await variant.hideAction(page, targetOwnerId);

			// Step 7: Navigate to map — control photo should still be visible,
			//         but hidden user's photo should be gone
			await navigateToMap(page);
			await assertPhotoVisibleButNotFromUser(page, targetOwnerId);

			// Step 8: Reload and verify the hide persists
			await page.reload();
			await page.waitForLoadState('networkidle');
			await ensureSourceEnabled(page, 'hillview', true);
			await assertPhotoVisibleButNotFromUser(page, targetOwnerId);
		});
	}
});
