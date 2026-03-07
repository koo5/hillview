import { test, expect } from './fixtures';
import { createTestUsers, loginAsTestUser } from './helpers/testUsers';
import { setupConsoleLogging } from './helpers/consoleLogging';

const BACKEND_URL = 'http://localhost:8055';

/** Get a JWT token for a given username/password. */
async function getUserToken(username: string, password: string): Promise<string> {
	const res = await fetch(`${BACKEND_URL}/api/auth/token`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
		body: new URLSearchParams({ username, password, grant_type: 'password' }),
	});
	if (!res.ok) throw new Error(`Failed to get token for ${username}: ${res.status}`);
	const data = await res.json();
	return data.access_token;
}

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
	let testPasswords: { test: string; admin: string; testuser: string };

	test.beforeEach(async ({ page }) => {
		setupConsoleLogging(page);
		const result = await createTestUsers();
		testPasswords = result.passwords;
	});

	test('user profile page shows hide button when authenticated', async ({ page }) => {
		await loginAsTestUser(page, testPasswords.test);
		await goToOtherUserProfile(page);

		await expect(page.locator('[data-testid="user-page-hide-user"]')).toBeVisible();
	});

	test('user profile page hides button on own profile', async ({ page }) => {
		await loginAsTestUser(page, testPasswords.test);

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

	test('hide user dialog opens and can be cancelled', async ({ page }) => {
		await loginAsTestUser(page, testPasswords.test);
		await goToOtherUserProfile(page);

		// Open dialog
		await page.locator('[data-testid="user-page-hide-user"]').click();
		await expect(page.locator('[data-testid="hide-user-dialog"]')).toBeVisible();

		// Cancel
		await page.locator('[data-testid="hide-user-cancel"]').click();
		await expect(page.locator('[data-testid="hide-user-dialog"]')).not.toBeVisible();

		// Verify nothing was hidden via API
		const token = await getUserToken('test', testPasswords.test);
		const hidden = await apiGetHiddenUsers(token);
		expect(hidden).toHaveLength(0);
	});

	test('hide user dialog submits successfully', async ({ page }) => {
		await loginAsTestUser(page, testPasswords.test);
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
		const token = await getUserToken('test', testPasswords.test);
		const hidden = await apiGetHiddenUsers(token);
		expect(hidden.length).toBeGreaterThan(0);
		const match = hidden.find((h: any) => h.target_user_id === targetUserId);
		expect(match).toBeTruthy();
		expect(match.reason).toBe('test reason');
	});

	test('hidden user appears on /hidden page', async ({ page }) => {
		await loginAsTestUser(page, testPasswords.test);

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

	test('unhide user from /hidden page', async ({ page }) => {
		await loginAsTestUser(page, testPasswords.test);

		// Hide a user via API shortcut
		const token = await getUserToken('test', testPasswords.test);

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
