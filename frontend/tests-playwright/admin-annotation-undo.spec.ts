import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAs, logoutUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { getUserToken, BACKEND_URL } from './helpers/adminAuth';

const TARGET = { selector: { type: 'FragmentSelector', value: 'xywh=pixel:0,0,10,10' } };

async function annCreate(token: string, photoId: string, body: string): Promise<string> {
	const res = await fetch(`${BACKEND_URL}/api/annotations/photos/${photoId}`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
		body: JSON.stringify({ body, target: TARGET }),
	});
	if (!res.ok) throw new Error(`create annotation failed: ${res.status}`);
	return (await res.json()).id as string;
}

async function annUpdate(token: string, id: string, body: string): Promise<string> {
	const res = await fetch(`${BACKEND_URL}/api/annotations/${id}`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
		body: JSON.stringify({ body, target: TARGET }),
	});
	if (!res.ok) throw new Error(`update annotation failed: ${res.status}`);
	return (await res.json()).id as string;
}

/** Current (non-deleted) annotation bodies for a photo, via the public read path. */
async function currentBodies(photoId: string): Promise<string[]> {
	const res = await fetch(`${BACKEND_URL}/api/annotations/photos/${photoId}`);
	if (!res.ok) throw new Error(`read annotations failed: ${res.status}`);
	return (await res.json()).map((a: any) => a.body);
}

test.describe('Admin annotation undo + explainability', () => {
	test('undoing a create removes the annotation and notifies the author with the reason', async ({ page, testUsers }) => {
		test.setTimeout(180_000);

		await loginAs(page, 'test', testUsers.passwords.test);
		const photoId = await uploadPhoto(page, testPhotos[0]);
		const token = await getUserToken('test', testUsers.passwords.test);
		const annId = await annCreate(token, photoId, 'annotation to be removed');

		// Admin reverts it from the log, with a reason.
		await logoutUser(page);
		await loginAs(page, 'admin', testUsers.passwords.admin);
		await page.goto('/admin/annotations');

		const row = page.locator(`[data-testid="admin-annotation-event"][data-event-id="${annId}"]`);
		await expect(row).toBeVisible({ timeout: T(15000) });
		await row.getByTestId('admin-annotation-undo').click();

		const reason = `spam ${Date.now()}`;
		await expect(page.getByTestId('admin-undo-dialog')).toBeVisible();
		await page.getByTestId('admin-undo-reason').fill(reason);
		await page.getByTestId('admin-undo-confirm').click();
		await expect(page.getByTestId('admin-undo-dialog')).not.toBeVisible({ timeout: T(15000) });

		// The chain now has a deleted tombstone, and the create is no longer the tip.
		await expect(
			page.locator('[data-testid="admin-annotation-event"][data-event-type="deleted"]').first()
		).toBeVisible({ timeout: T(15000) });
		await expect(row.getByTestId('admin-annotation-undo')).toHaveCount(0);
		// The annotation is gone from the public read path.
		expect(await currentBodies(photoId)).not.toContain('annotation to be removed');

		// The author sees an explanatory notification with the reason, and a badge.
		await logoutUser(page);
		await loginAs(page, 'test', testUsers.passwords.test);

		await page.locator('[data-testid="header-menu-button"], [data-testid="hamburger-menu"]').first().click();
		await expect(page.getByTestId('nav-menu')).toBeVisible();
		await expect(page.getByTestId('nav-notifications-badge')).toBeVisible({ timeout: T(15000) });
		await page.getByTestId('nav-notifications-link').click();
		await page.waitForURL('/notifications', { timeout: T(10000) });

		const item = page.locator('[data-testid="notification-item"]').filter({ hasText: reason });
		await expect(item).toBeVisible({ timeout: T(15000) });
		await expect(item).toHaveAttribute('data-type', 'annotation_reverted');

		// Marking all read clears the badge.
		await page.getByTestId('notifications-mark-all').click();
		await page.locator('[data-testid="header-menu-button"], [data-testid="hamburger-menu"]').first().click();
		await expect(page.getByTestId('nav-notifications-badge')).toHaveCount(0, { timeout: T(15000) });
	});

	test('undoing an edit restores the previous version', async ({ page, testUsers }) => {
		test.setTimeout(180_000);

		await loginAs(page, 'test', testUsers.passwords.test);
		const photoId = await uploadPhoto(page, testPhotos[1]);
		const token = await getUserToken('test', testUsers.passwords.test);

		const a = await annCreate(token, photoId, 'version one');
		const b = await annUpdate(token, a, 'version two');
		expect(await currentBodies(photoId)).toContain('version two');

		// Admin undoes the edit via the API; the prior version is restored.
		const adminToken = await getUserToken('admin', testUsers.passwords.admin);
		const res = await fetch(`${BACKEND_URL}/api/admin/annotation-events/${b}/undo`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${adminToken}` },
			body: JSON.stringify({ reason: 'revert edit' }),
		});
		expect(res.ok).toBeTruthy();

		const bodies = await currentBodies(photoId);
		expect(bodies).toContain('version one');
		expect(bodies).not.toContain('version two');
	});
});
