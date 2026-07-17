import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAs } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { getUserToken, BACKEND_URL } from './helpers/adminAuth';

type Page = import('@playwright/test').Page;

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

/** Open the nav drawer from any page (map uses hamburger-menu, sub-pages use header-menu-button). */
async function openMenu(page: Page) {
	const menuButton = page.locator('[data-testid="header-menu-button"], [data-testid="hamburger-menu"]').first();
	await menuButton.click();
	await expect(page.getByTestId('nav-menu')).toBeVisible();
}

test.describe('User-facing contributions dashboard', () => {
	test.describe.configure({ mode: 'serial' });

	test('setup: standing, edited-by-another, and removed chains', async ({ page, testUsers }) => {
		test.setTimeout(180_000);

		// A photo owned by the ordinary test user to hang annotations on.
		await loginAs(page, 'test', testUsers.passwords.test);
		const photoId = await uploadPhoto(page, testPhotos[0]);
		expect(photoId).toBeTruthy();

		const testToken = await getUserToken('test', testUsers.passwords.test);
		const adminToken = await getUserToken('admin', testUsers.passwords.admin);

		// Chain A — test creates + test edits: stays live as the caller's work → standing.
		const a = await annCreate(testToken, photoId, 'alpha standing');
		await annUpdate(testToken, a, 'alpha standing edited');

		// Chain B — test creates + test deletes → removed.
		const b = await annCreate(testToken, photoId, 'beta doomed');
		await annDelete(testToken, b);

		// Chain C — test creates + ADMIN edits → live, but no longer the caller's work.
		const c = await annCreate(testToken, photoId, 'gamma original');
		await annUpdate(adminToken, c, 'gamma modded');
	});

	test('the dashboard summarizes and lists the caller’s contributions', async ({ page, testUsers }) => {
		await loginAs(page, 'test', testUsers.passwords.test);
		await page.goto('/contributions');

		await expect(page.getByTestId('contributions-page')).toBeVisible({ timeout: T(10000) });

		// Summary: one standing, one edited-by-others, one removed, across one photo.
		await expect(page.getByTestId('contributions-stat-standing-value')).toHaveText('1', { timeout: T(15000) });
		await expect(page.getByTestId('contributions-stat-changed-value')).toHaveText('1');
		await expect(page.getByTestId('contributions-stat-removed-value')).toHaveText('1');
		await expect(page.getByTestId('contributions-stat-photos-value')).toHaveText('1');

		await expect(page.getByTestId('contributions-item')).toHaveCount(3);

		// Standing: live, still the caller's own version, no "what happened" note.
		const standing = page.locator('[data-testid="contributions-item"][data-status="live"][data-mine-current="true"]');
		await expect(standing).toHaveCount(1);
		await expect(standing.getByTestId('contributions-status')).toHaveText('Current');
		await expect(standing.getByTestId('contributions-body')).toHaveText('alpha standing edited');
		await expect(standing.getByTestId('contributions-note')).toHaveCount(0);

		// Edited by another: shows ONLY the current public text, and never names who
		// changed it (the judicious, user-facing contract).
		const changed = page.locator('[data-testid="contributions-item"][data-status="live"][data-mine-current="false"]');
		await expect(changed).toHaveCount(1);
		await expect(changed.getByTestId('contributions-status')).toHaveText('Current');
		await expect(changed.getByTestId('contributions-body')).toHaveText('gamma modded');
		await expect(changed.getByTestId('contributions-note')).toContainText('another contributor');
		await expect(changed).not.toContainText('admin');
		// The superseded original text is never surfaced.
		await expect(changed).not.toContainText('gamma original');

		// Removed: tombstone, no body, and it was the caller who removed it.
		const removed = page.locator('[data-testid="contributions-item"][data-status="removed"]');
		await expect(removed).toHaveCount(1);
		await expect(removed.getByTestId('contributions-status')).toHaveText('Removed');
		await expect(removed.getByTestId('contributions-note')).toContainText('You removed this');
	});

	test('the nav menu links a logged-in user to their contributions', async ({ page, testUsers }) => {
		await loginAs(page, 'test', testUsers.passwords.test);
		await openMenu(page);

		const link = page.getByTestId('nav-contributions-link');
		await expect(link).toBeVisible();
		await link.click();
		await page.waitForURL(/\/contributions/, { timeout: T(10000) });
		await expect(page.getByTestId('contributions-page')).toBeVisible();
	});

	test('signed-out visitors get a sign-in prompt, not data', async ({ page }) => {
		// Fresh context = logged out; no loginAs.
		await page.goto('/contributions');
		await expect(page.getByTestId('contributions-signin')).toBeVisible({ timeout: T(10000) });
		await expect(page.getByTestId('contributions-item')).toHaveCount(0);
	});
});
