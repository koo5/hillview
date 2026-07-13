import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAs, logoutUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { getUserToken, callAdminAPI, BACKEND_URL } from './helpers/adminAuth';

/** Flag a photo via the API. External sources need no real photo row. */
async function seedFlag(token: string, photoId: string, photoSource = 'mapillary'): Promise<void> {
	const res = await fetch(`${BACKEND_URL}/api/flagged/photos`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
		body: JSON.stringify({ photo_source: photoSource, photo_id: photoId, reason: 'admin-flags e2e' }),
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

		// An external (mapillary) flag links to the photo but offers no delete
		// button and no thumbnail (no local row).
		await expect(row.getByTestId('admin-flag-photo-link')).toHaveAttribute('href', `/photo/mapillary-${photoId}`);
		await expect(row.getByTestId('admin-flag-delete')).toHaveCount(0);
		await expect(row.getByTestId('admin-flag-thumb')).toHaveCount(0);

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

	test('a hillview flag shows a thumbnail, links to the photo, and can be deleted', async ({ page, testUsers }) => {
		test.setTimeout(180_000);

		// 'test' uploads a photo, then flags it (a hillview flag with a real row).
		await loginAs(page, 'test', testUsers.passwords.test);
		const photoId = await uploadPhoto(page, testPhotos[0]);
		const token = await getUserToken('test', testUsers.passwords.test);
		await seedFlag(token, photoId, 'hillview');

		await logoutUser(page);
		await loginAs(page, 'admin', testUsers.passwords.admin);
		await page.goto('/admin/flags');

		const row = page.locator(`[data-testid="admin-flag"][data-photo-id="${photoId}"]`);
		await expect(row).toBeVisible({ timeout: T(15000) });

		// Thumbnail rendered, photo link points at the detail page.
		await expect(row.getByTestId('admin-flag-thumb')).toHaveAttribute('src', /.+/);
		await expect(row.getByTestId('admin-flag-photo-link')).toHaveAttribute('href', `/photo/hillview-${photoId}`);

		// Delete outright, with a reason.
		const reason = `flag-delete ${Date.now()}`;
		await row.getByTestId('admin-flag-delete').click();
		await expect(page.getByTestId('admin-flag-delete-dialog')).toBeVisible();
		await page.getByTestId('admin-flag-delete-reason').fill(reason);
		await page.getByTestId('admin-flag-delete-confirm').click();
		await expect(page.getByTestId('admin-flag-delete-dialog')).not.toBeVisible({ timeout: T(15000) });

		// The photo is deleted and the flag resolved → it leaves the Open list.
		await expect(row).toHaveCount(0, { timeout: T(15000) });

		// The owner was notified of the removal, carrying the reason.
		const testToken = await getUserToken('test', testUsers.passwords.test);
		const notifs = await (await fetch(`${BACKEND_URL}/api/notifications/recent?limit=20`, {
			headers: { Authorization: `Bearer ${testToken}` },
		})).json();
		expect((notifs.notifications || []).some(
			(n: any) => n.type === 'photo_removed' && (n.body || '').includes(reason)
		)).toBeTruthy();
	});

	test('non-admin is forbidden at /admin/flags', async ({ page, testUsers }) => {
		await loginAs(page, 'test', testUsers.passwords.test);
		await page.goto('/admin/flags');
		await expect(page.getByTestId('admin-forbidden')).toBeVisible({ timeout: T(15000) });
		await expect(page.getByTestId('admin-flag')).toHaveCount(0);
	});
});
