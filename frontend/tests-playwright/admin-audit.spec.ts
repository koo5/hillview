import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAs, logoutUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { getUserToken, BACKEND_URL } from './helpers/adminAuth';

test.describe('Admin moderation audit', () => {
	test("an admin deleting another user's photo appears in the audit log", async ({ page, testUsers }) => {
		test.setTimeout(180_000);

		// 'test' uploads a photo.
		await loginAs(page, 'test', testUsers.passwords.test);
		const photoId = await uploadPhoto(page, testPhotos[0]);
		expect(photoId).toBeTruthy();

		// 'admin' deletes it via the API (not their own → writes a moderation-audit row).
		const adminToken = await getUserToken('admin', testUsers.passwords.admin);
		const reason = `audit-e2e ${Date.now()}`;
		const del = await fetch(`${BACKEND_URL}/api/photos/${photoId}?reason=${encodeURIComponent(reason)}`, {
			method: 'DELETE',
			headers: { Authorization: `Bearer ${adminToken}` },
		});
		expect(del.ok).toBeTruthy();

		// View the audit log as admin, reached via the dashboard card.
		await logoutUser(page);
		await loginAs(page, 'admin', testUsers.passwords.admin);
		await page.goto('/admin');
		await page.getByTestId('admin-card-audit').click();
		await page.waitForURL('/admin/audit', { timeout: T(10000) });

		// Find our entry by its unique reason (robust against other audit rows).
		const entry = page.locator('[data-testid="admin-audit-entry"]').filter({ hasText: reason });
		await expect(entry).toBeVisible({ timeout: T(15000) });
		await expect(entry).toHaveAttribute('data-action', 'delete');
		await expect(entry.getByTestId('admin-audit-actor')).toContainText('admin');
		await expect(entry.getByTestId('admin-audit-owner')).toContainText('test');

		// The owner was notified of the removal, carrying the reason (explainability).
		const testToken = await getUserToken('test', testUsers.passwords.test);
		const notifs = await (await fetch(`${BACKEND_URL}/api/notifications/recent?limit=20`, {
			headers: { Authorization: `Bearer ${testToken}` },
		})).json();
		const removal = (notifs.notifications || []).find(
			(n: any) => n.type === 'photo_removed' && (n.body || '').includes(reason)
		);
		expect(removal).toBeTruthy();
	});

	test('non-admin is forbidden at /admin/audit', async ({ page, testUsers }) => {
		await loginAs(page, 'test', testUsers.passwords.test);
		await page.goto('/admin/audit');
		await expect(page.getByTestId('admin-forbidden')).toBeVisible({ timeout: T(15000) });
		await expect(page.getByTestId('admin-audit-entry')).toHaveCount(0);
	});
});
