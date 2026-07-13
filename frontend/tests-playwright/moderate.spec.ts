import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAs } from './helpers/testUsers';
import { getUserToken, BACKEND_URL } from './helpers/adminAuth';

type Page = import('@playwright/test').Page;

async function openMenu(page: Page) {
	await page.locator('[data-testid="header-menu-button"], [data-testid="hamburger-menu"]').first().click();
	await expect(page.getByTestId('nav-menu')).toBeVisible();
}

async function seedFlag(token: string, photoId: string): Promise<void> {
	const res = await fetch(`${BACKEND_URL}/api/flagged/photos`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
		body: JSON.stringify({ photo_source: 'mapillary', photo_id: photoId, reason: 'moderate e2e' }),
	});
	if (!res.ok) throw new Error(`Failed to seed flag: ${res.status}`);
}

test.describe('Moderator surface', () => {
	test('moderator sees Moderate (not Admin) and can use the moderation tools', async ({ page, testUsers }) => {
		const testToken = await getUserToken('test', testUsers.passwords.test);
		const photoId = `mod-e2e-${Date.now()}`;
		await seedFlag(testToken, photoId);

		await loginAs(page, 'moderator', testUsers.passwords.moderator);

		// Menu shows Moderate, not Admin.
		await openMenu(page);
		await expect(page.getByTestId('nav-moderate-link')).toBeVisible();
		await expect(page.getByTestId('nav-admin-link')).toHaveCount(0);
		await page.getByTestId('nav-moderate-link').click();
		await page.waitForURL('/moderate', { timeout: T(10000) });
		await expect(page.getByTestId('moderate-dashboard')).toBeVisible();

		// Flags: reachable, and a moderator can resolve.
		await page.getByTestId('moderate-card-flags').click();
		await page.waitForURL('/admin/flags', { timeout: T(10000) });
		const flagRow = page.locator(`[data-testid="admin-flag"][data-photo-id="${photoId}"]`);
		await expect(flagRow).toBeVisible({ timeout: T(15000) });
		await flagRow.getByTestId('admin-flag-resolve').click();
		await expect(flagRow).toHaveCount(0, { timeout: T(15000) });

		// Annotation activity: reachable, and the undo endpoint admits moderators
		// (404 on a bogus id means the role gate passed, not 403).
		await page.goto('/moderate');
		await page.getByTestId('moderate-card-annotations').click();
		await page.waitForURL('/admin/annotations', { timeout: T(10000) });
		await expect(page.getByTestId('admin-annotations-page')).toBeVisible();
		const modToken = await getUserToken('moderator', testUsers.passwords.moderator);
		const undo = await fetch(`${BACKEND_URL}/api/admin/annotation-events/nonexistent/undo`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${modToken}` },
			body: '{}',
		});
		expect(undo.status).toBe(404);

		// Moderation audit: reachable.
		await page.goto('/moderate');
		await page.getByTestId('moderate-card-audit').click();
		await page.waitForURL('/admin/audit', { timeout: T(10000) });
		await expect(page.getByTestId('admin-audit-page')).toBeVisible();
	});

	test('moderator is forbidden from the admin-only surfaces', async ({ page, testUsers }) => {
		await loginAs(page, 'moderator', testUsers.passwords.moderator);

		await page.goto('/admin');
		await expect(page.getByTestId('admin-forbidden')).toBeVisible({ timeout: T(15000) });

		await page.goto('/admin/contact');
		await expect(page.getByTestId('admin-forbidden')).toBeVisible({ timeout: T(15000) });
	});

	test('regular user has no Moderate item and /moderate is forbidden', async ({ page, testUsers }) => {
		await loginAs(page, 'test', testUsers.passwords.test);

		await page.goto('/bestof');
		await openMenu(page);
		await expect(page.getByTestId('nav-moderate-link')).toHaveCount(0);

		await page.goto('/moderate');
		await expect(page.getByTestId('moderate-forbidden')).toBeVisible({ timeout: T(15000) });
	});
});
