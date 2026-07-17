import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAs } from './helpers/testUsers';
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

test.describe('Per-photo annotation history (moderators/admins)', () => {
	test.describe.configure({ mode: 'serial' });

	let photoUid = '';

	test('setup: photo with two annotation chains (one edited, one deleted)', async ({ page, testUsers }) => {
		test.setTimeout(180_000);

		// A photo to hang annotations on, owned by the ordinary test user.
		await loginAs(page, 'test', testUsers.passwords.test);
		const photoId = await uploadPhoto(page, testPhotos[0]);
		expect(photoId).toBeTruthy();
		photoUid = `hillview-${photoId}`;

		const token = await getUserToken('test', testUsers.passwords.test);

		// Chain A: created → edited (stays live).
		const aCreated = await annCreate(token, photoId, 'alpha');
		await annUpdate(token, aCreated, 'alpha edited');

		// Chain B: created → deleted (removed).
		const bCreated = await annCreate(token, photoId, 'beta');
		await annDelete(token, bCreated);
	});

	test('moderator sees both chains grouped, oldest→newest, with statuses', async ({ page, testUsers }) => {
		await loginAs(page, 'admin', testUsers.passwords.admin);
		await page.goto(`/photo/${photoUid}/annotations`);

		await expect(page.getByTestId('photo-annotation-history-page')).toBeVisible({ timeout: T(10000) });

		const chains = page.getByTestId('photo-annotation-history-chain');
		await expect(chains).toHaveCount(2, { timeout: T(15000) });

		// One chain is live (edited), one removed (deleted).
		const live = page.locator('[data-testid="photo-annotation-history-chain"][data-live="true"]');
		const removed = page.locator('[data-testid="photo-annotation-history-chain"][data-live="false"]');
		await expect(live).toHaveCount(1);
		await expect(removed).toHaveCount(1);
		await expect(live.getByTestId('photo-annotation-history-status')).toHaveText('Current');
		await expect(removed.getByTestId('photo-annotation-history-status')).toHaveText('Removed');

		// The live chain is the edited one: two events, newest→oldest = updated (tip), created.
		const liveEvents = live.getByTestId('photo-annotation-history-event');
		await expect(liveEvents).toHaveCount(2);
		await expect(liveEvents.nth(0).getByTestId('photo-annotation-history-type')).toHaveText('updated');
		await expect(liveEvents.nth(1).getByTestId('photo-annotation-history-type')).toHaveText('created');
		await expect(liveEvents.nth(0)).toContainText('alpha edited');
		await expect(liveEvents.nth(1)).toContainText('alpha');

		// The edit (tip, on top) shows the text it replaced, struck through.
		await expect(liveEvents.nth(0).getByTestId('photo-annotation-history-prev-body')).toContainText('alpha');

		// The acting user is ordinary, so their username is alert-highlighted.
		await expect(liveEvents.nth(1)).toHaveAttribute('data-actor-role', 'user');
		await expect(liveEvents.nth(1).getByTestId('photo-annotation-history-user')).toHaveClass(/ordinary/);

		// Each chain offers a zoom-to-spot link and a moderator undo control.
		await expect(live.getByTestId('photo-annotation-history-zoom')).toBeVisible();
		await expect(removed.getByTestId('photo-annotation-history-zoom')).toBeVisible();
		await expect(live.getByTestId('photo-annotation-history-undo')).toBeVisible();
		await expect(removed.getByTestId('photo-annotation-history-undo')).toContainText('Restore');
	});

	test('the photo detail page links moderators to the history', async ({ page, testUsers }) => {
		await loginAs(page, 'admin', testUsers.passwords.admin);
		await page.goto(`/photo/${photoUid}`);
		await expect(page.getByTestId('photo-detail')).toBeVisible({ timeout: T(10000) });

		const link = page.getByTestId('photo-annotation-history-link');
		await expect(link).toBeVisible();
		await link.click();
		await page.waitForURL(new RegExp(`/photo/${photoUid}/annotations`), { timeout: T(10000) });
		await expect(page.getByTestId('photo-annotation-history-page')).toBeVisible();
	});

	test('a moderator can restore the deleted chain from the history', async ({ page, testUsers }) => {
		await loginAs(page, 'admin', testUsers.passwords.admin);
		await page.goto(`/photo/${photoUid}/annotations`);
		await expect(page.getByTestId('photo-annotation-history-page')).toBeVisible({ timeout: T(10000) });

		const removed = page.locator('[data-testid="photo-annotation-history-chain"][data-live="false"]');
		await expect(removed).toHaveCount(1, { timeout: T(15000) });

		// Restore the removed chain (undo of a delete tombstone).
		await removed.getByTestId('photo-annotation-history-undo').click();
		await expect(page.getByTestId('photo-annotation-history-undo-dialog')).toBeVisible();
		await page.getByTestId('photo-annotation-history-undo-confirm').click();

		// Both chains are now live; nothing remains removed.
		await expect(page.locator('[data-testid="photo-annotation-history-chain"][data-live="false"]')).toHaveCount(0, { timeout: T(15000) });
		await expect(page.locator('[data-testid="photo-annotation-history-chain"][data-live="true"]')).toHaveCount(2);
	});

	test('ordinary users are not authorized and get no history link', async ({ page, testUsers }) => {
		// loginAs re-authenticates directly (no logout needed) — switches admin → test.
		await loginAs(page, 'test', testUsers.passwords.test);

		// The detail page shows no history entry point for a non-moderator.
		await page.goto(`/photo/${photoUid}`);
		await expect(page.getByTestId('photo-detail')).toBeVisible({ timeout: T(10000) });
		await expect(page.getByTestId('photo-annotation-history-link')).toHaveCount(0);

		// The history page itself refuses.
		await page.goto(`/photo/${photoUid}/annotations`);
		await expect(page.getByTestId('photo-annotation-history-forbidden')).toBeVisible({ timeout: T(10000) });
		await expect(page.getByTestId('photo-annotation-history-chain')).toHaveCount(0);
	});
});
