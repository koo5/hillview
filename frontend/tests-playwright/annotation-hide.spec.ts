import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAs, logoutUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { ensureSourceEnabled } from './helpers/sourceHelpers';
import { BACKEND_URL } from './helpers/adminAuth';

type Page = import('@playwright/test').Page;

/** Current (non-deleted, non-hidden) annotation bodies via the public read path. */
async function currentBodies(photoId: string): Promise<string[]> {
	const res = await fetch(`${BACKEND_URL}/api/annotations/photos/${photoId}`);
	if (!res.ok) throw new Error(`read annotations failed: ${res.status}`);
	return (await res.json()).map((a: any) => a.body);
}

/** Open the map centred on the test photo and enter the OSD zoom view. */
async function openViewer(page: Page) {
	await page.goto('/?lat=50.1153&lon=14.4938&zoom=18');
	await ensureSourceEnabled(page, 'hillview', true);
	const mainPhoto = page.locator('[data-testid="main-photo"]');
	await mainPhoto.waitFor({ state: 'visible', timeout: T(30000) });
	await mainPhoto.click();
	await page.locator('[data-testid="osd-viewer-overlay"]').waitFor({ state: 'visible', timeout: T(15000) });
	await page.locator('.openseadragon-canvas').waitFor({ state: 'visible', timeout: T(15000) });
	await page.locator('[data-testid="osd-annotate-draw"]').waitFor({ state: 'visible', timeout: T(10000) });
}

/** Enter draw/edit mode (idempotent — won't toggle off if already active). */
async function enterMode(page: Page, testid: string) {
	const btn = page.locator(`[data-testid="${testid}"]`);
	await btn.waitFor({ state: 'visible', timeout: T(5000) });
	const isActive = await btn.evaluate((el) => el.classList.contains('active'));
	if (!isActive) await btn.click();
}

const REGION = { x1: 0.3, y1: 0.3, x2: 0.6, y2: 0.6 };

/** Draw a rectangle at REGION and save it with the given label. */
async function drawAnnotation(page: Page, label: string) {
	await enterMode(page, 'osd-annotate-draw');
	const canvas = page.locator('.openseadragon-canvas');
	const box = (await canvas.boundingBox())!;
	await page.mouse.move(box.x + box.width * REGION.x1, box.y + box.height * REGION.y1);
	await page.mouse.down();
	await page.mouse.move(box.x + box.width * REGION.x2, box.y + box.height * REGION.y2, { steps: 10 });
	await page.mouse.up();
	const panel = page.locator('[data-testid="osd-edit-body-panel"]');
	await panel.waitFor({ state: 'visible', timeout: T(10000) });
	await page.locator('[data-testid="osd-edit-body-input"]').fill(label);
	await page.click('[data-testid="osd-edit-body-save"]');
	await expect(panel).not.toBeVisible({ timeout: T(5000) });
	await page.waitForTimeout(1000); // server persist
}

/** Select the annotation at REGION in edit mode and wait for the panel. */
async function selectAnnotation(page: Page) {
	await enterMode(page, 'osd-annotate-edit');
	const canvas = page.locator('.openseadragon-canvas');
	const box = (await canvas.boundingBox())!;
	await page.mouse.click(
		box.x + box.width * ((REGION.x1 + REGION.x2) / 2),
		box.y + box.height * ((REGION.y1 + REGION.y2) / 2),
	);
	const panel = page.locator('[data-testid="osd-edit-body-panel"]');
	await panel.waitFor({ state: 'visible', timeout: T(10000) });
	return panel;
}

test.describe('Moderator annotation hide', () => {
	test('hide button is moderator-only, hides from viewers, and unhide works from the history page', async ({ page, testUsers }) => {
		test.setTimeout(240_000);

		const label = `hill duplicated by overlay ${Date.now()}`;

		// Ordinary user: draws the annotation, gets no Hide button.
		await loginAs(page, 'test', testUsers.passwords.test);
		const photoId = await uploadPhoto(page, testPhotos[0]);
		await openViewer(page);
		await drawAnnotation(page, label);
		await selectAnnotation(page);
		await expect(page.locator('[data-testid="osd-edit-body-hide"]')).toHaveCount(0);
		await page.click('[data-testid="osd-edit-body-cancel"]');
		expect(await currentBodies(photoId)).toContain(label);

		// Close the viewer — its overlay would swallow the menu clicks of logout.
		await page.click('[data-testid="osd-viewer-close"]');
		await expect(page.locator('[data-testid="osd-viewer-overlay"]')).not.toBeVisible({ timeout: T(5000) });

		// Moderator (admin passes the moderator gate): Hide is available.
		await logoutUser(page);
		await loginAs(page, 'admin', testUsers.passwords.admin);
		await openViewer(page);
		await selectAnnotation(page);
		const hideBtn = page.locator('[data-testid="osd-edit-body-hide"]');
		await expect(hideBtn).toBeVisible();
		await hideBtn.click();
		await expect(page.locator('[data-testid="osd-edit-body-panel"]')).not.toBeVisible({ timeout: T(10000) });

		// Gone from the public read path (and from the viewer this session).
		await expect(async () => {
			expect(await currentBodies(photoId)).not.toContain(label);
		}).toPass({ timeout: T(10000) });

		// While drawing a NEW shape the panel has no Hide button (nothing persisted yet).
		await enterMode(page, 'osd-annotate-draw');
		const canvas = page.locator('.openseadragon-canvas');
		const box = (await canvas.boundingBox())!;
		await page.mouse.move(box.x + box.width * 0.7, box.y + box.height * 0.7);
		await page.mouse.down();
		await page.mouse.move(box.x + box.width * 0.8, box.y + box.height * 0.8, { steps: 5 });
		await page.mouse.up();
		await page.locator('[data-testid="osd-edit-body-panel"]').waitFor({ state: 'visible', timeout: T(10000) });
		await expect(page.locator('[data-testid="osd-edit-body-hide"]')).toHaveCount(0);
		await page.click('[data-testid="osd-edit-body-cancel"]');

		// History page shows the chain as Hidden with an Unhide undo.
		await page.goto(`/photo/hillview-${photoId}/annotations`);
		const chain = page
			.locator('[data-testid="photo-annotation-history-chain"]')
			.filter({ hasText: label })
			.first();
		await expect(chain).toBeVisible({ timeout: T(15000) });
		const status = chain.locator('[data-testid="photo-annotation-history-status"]');
		await expect(status).toHaveText('Hidden');
		await expect(status).toHaveAttribute('data-hidden', 'true');
		await expect(
			chain.locator('[data-testid="photo-annotation-history-event"][data-event-type="hidden"]').first()
		).toBeVisible();

		const undoBtn = chain.locator('[data-testid="photo-annotation-history-undo"]');
		await expect(undoBtn).toContainText('Unhide this annotation');
		await undoBtn.click();
		await expect(page.getByTestId('photo-annotation-history-undo-dialog')).toBeVisible();
		await page.getByTestId('photo-annotation-history-undo-confirm').click();
		await expect(page.getByTestId('photo-annotation-history-undo-dialog')).not.toBeVisible({ timeout: T(15000) });

		// Unhidden: current again in the history and back on the public read path.
		await expect(
			page
				.locator('[data-testid="photo-annotation-history-chain"]')
				.filter({ hasText: label })
				.first()
				.locator('[data-testid="photo-annotation-history-status"]')
		).toHaveText('Current', { timeout: T(15000) });
		expect(await currentBodies(photoId)).toContain(label);
	});
});
