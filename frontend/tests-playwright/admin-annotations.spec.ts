import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAs, logoutUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { getUserToken, BACKEND_URL } from './helpers/adminAuth';

// Matches what the app writes: Annotorious v3 RECTANGLE with pixel bounds.
const TARGET = { selector: { type: 'RECTANGLE', geometry: { bounds: { minX: 100, minY: 50, maxX: 300, maxY: 250 } } } };

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

async function annDelete(token: string, id: string): Promise<void> {
	const res = await fetch(`${BACKEND_URL}/api/annotations/${id}`, {
		method: 'DELETE',
		headers: { Authorization: `Bearer ${token}` },
	});
	if (!res.ok) throw new Error(`delete annotation failed: ${res.status}`);
}

test.describe('Admin annotation activity log', () => {
	test('created / updated / deleted events all show in the log', async ({ page, testUsers }) => {
		test.setTimeout(180_000);

		// A photo is needed to hang annotations on; upload one as the test user.
		await loginAs(page, 'test', testUsers.passwords.test);
		const photoId = await uploadPhoto(page, testPhotos[0]);
		expect(photoId).toBeTruthy();

		// Generate one of each event type via the annotation API (append-only chain).
		const token = await getUserToken('test', testUsers.passwords.test);
		const createdId = await annCreate(token, photoId, 'first annotation');
		const updatedId = await annUpdate(token, createdId, 'edited annotation');
		await annDelete(token, updatedId);

		// View the log as admin.
		await logoutUser(page);
		await loginAs(page, 'admin', testUsers.passwords.admin);
		await page.goto('/admin/annotations');

		const rows = page.getByTestId('admin-annotation-event');
		await expect(rows).toHaveCount(3, { timeout: T(15000) });

		// Reverse-chronological: deleted, then updated, then created.
		await expect(rows.nth(0).getByTestId('admin-annotation-type')).toHaveText('deleted');
		await expect(rows.nth(1).getByTestId('admin-annotation-type')).toHaveText('updated');
		await expect(rows.nth(2).getByTestId('admin-annotation-type')).toHaveText('created');

		// The create event is attributed to the acting user, whose ordinary role is
		// exposed for the alert-styling of the username.
		await expect(rows.nth(2).getByTestId('admin-annotation-user')).toContainText('test');
		await expect(rows.nth(2)).toHaveAttribute('data-actor-role', 'user');
		await expect(rows.nth(2).getByTestId('admin-annotation-user')).toHaveClass(/ordinary/);

		// Every event links to its photo's detail page.
		await expect(rows.nth(2).getByTestId('admin-annotation-photo-link')).toHaveAttribute('href', `/photo/hillview-${photoId}`);

		// The current tip (deleted) is undoable and not marked superseded; the
		// older create/update events are marked superseded and offer no undo.
		await expect(rows.nth(0).getByTestId('admin-annotation-undo')).toBeVisible();
		await expect(rows.nth(0).getByTestId('admin-annotation-superseded')).toHaveCount(0);
		await expect(rows.nth(2).getByTestId('admin-annotation-superseded')).toBeVisible();
		await expect(rows.nth(2).getByTestId('admin-annotation-undo')).toHaveCount(0);

		// create/update carry a target → a zoomview deep-link; the deleted tombstone
		// has no target, so no zoom link.
		const zoom = rows.nth(2).getByTestId('admin-annotation-zoom-link');
		await expect(zoom).toBeVisible();
		await expect(zoom).toHaveAttribute('href', new RegExp(`photo=hillview-${photoId}.*x1=`));
		await expect(rows.nth(0).getByTestId('admin-annotation-zoom-link')).toHaveCount(0);

		// Filter to just deletions.
		await page.getByTestId('admin-annotations-filter-deleted').click();
		await expect(page.getByTestId('admin-annotation-event')).toHaveCount(1);
		await expect(page.getByTestId('admin-annotation-type')).toHaveText('deleted');
	});

	test('non-admin is forbidden at /admin/annotations', async ({ page, testUsers }) => {
		await loginAs(page, 'test', testUsers.passwords.test);
		await page.goto('/admin/annotations');
		await expect(page.getByTestId('admin-forbidden')).toBeVisible({ timeout: T(15000) });
		await expect(page.getByTestId('admin-annotation-event')).toHaveCount(0);
	});
});
