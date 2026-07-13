import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAs } from './helpers/testUsers';
import { getUserToken, callAdminAPI, BACKEND_URL } from './helpers/adminAuth';

/** Flag an (arbitrary, external) photo via the API — no real photo row required. */
async function seedFlag(token: string, photoId: string): Promise<void> {
	const res = await fetch(`${BACKEND_URL}/api/flagged/photos`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
		body: JSON.stringify({ photo_source: 'mapillary', photo_id: photoId, reason: 'admin-flags e2e' }),
	});
	if (!res.ok) throw new Error(`Failed to seed flag: ${res.status}`);
}

async function flagsOpenCount(adminPassword: string): Promise<number> {
	const res = await callAdminAPI('/api/admin/notifications', adminPassword);
	return (await res.json()).flags_open as number;
}

test.describe('Admin flagged photos', () => {
	test('resolving an open flag removes it from the Open list and drops the count', async ({ page, testUsers }) => {
		const photoId = `mapillary-e2e-${Date.now()}`;
		const token = await getUserToken('test', testUsers.passwords.test);
		await seedFlag(token, photoId);
		const before = await flagsOpenCount(testUsers.passwords.admin);

		await loginAs(page, 'admin', testUsers.passwords.admin);

		// Reach the flags page via the dashboard card (verifies the link).
		await page.goto('/admin');
		await page.getByTestId('admin-card-flags').click();
		await page.waitForURL('/admin/flags', { timeout: T(10000) });

		const row = page.locator(`[data-testid="admin-flag"][data-photo-id="${photoId}"]`);
		await expect(row).toBeVisible({ timeout: T(15000) });
		await expect(row.getByTestId('admin-flag-status')).toHaveText('open');

		// Resolve → it leaves the "Open" list.
		await row.getByTestId('admin-flag-resolve').click();
		await expect(row).toHaveCount(0, { timeout: T(15000) });

		// The backend open-count dropped by exactly one.
		expect(await flagsOpenCount(testUsers.passwords.admin)).toBe(before - 1);

		// Under "All" it still exists, now resolved.
		await page.getByTestId('admin-flags-filter-all').click();
		const allRow = page.locator(`[data-testid="admin-flag"][data-photo-id="${photoId}"]`);
		await expect(allRow).toBeVisible({ timeout: T(15000) });
		await expect(allRow.getByTestId('admin-flag-status')).toHaveText('resolved');
	});

	test('non-admin is forbidden at /admin/flags', async ({ page, testUsers }) => {
		await loginAs(page, 'test', testUsers.passwords.test);
		await page.goto('/admin/flags');
		await expect(page.getByTestId('admin-forbidden')).toBeVisible({ timeout: T(15000) });
		await expect(page.getByTestId('admin-flag')).toHaveCount(0);
	});
});
