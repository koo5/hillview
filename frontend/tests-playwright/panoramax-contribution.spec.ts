import { test, expect, type Page } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import fs from 'node:fs';
import { addCameraInitScript } from './helpers/cameraSetup';
import { seedBrowserPhoto, waitForPhotoCount, waitForUploadedCount } from './helpers/indexedDbPhotos';
import { T } from './helpers/timeouts';
import { chooseUploadLicense, confirmLicenseChoice } from './helpers/licenseChoice';

const API = 'http://localhost:8055/api';
const username = `pano_web_${randomUUID().slice(0, 12).replaceAll('-', '')}`;
const password = 'PanoramaxWebTest123!';
let userId: string;
let token: string;
let capturedServerId: string;
let capturedGrant = 'full1';
let manualServerId: string;

async function ready(page: Page, url: string) {
	await page.goto(url);
	await expect(page.locator('html')).toHaveAttribute('data-hydrated', /.*/, { timeout: T(15_000) });
}

async function login(page: Page, name = username, pass = password) {
	await ready(page, '/login');
	await page.getByTestId('login-username-input').fill(name);
	await page.getByTestId('login-password-input').fill(pass);
	await page.getByTestId('login-submit-button').click();
	await expect(page).not.toHaveURL(/\/login/, { timeout: T(30_000) });
	await expect(page.locator('html')).not.toHaveAttribute('data-loading', /.*/, { timeout: T(15_000) });
}

async function localPhotos(page: Page): Promise<any[]> {
	return page.evaluate(() => new Promise<any[]>((resolve, reject) => {
		const request = indexedDB.open('HillviewPhotoDB');
		request.onerror = () => reject(request.error);
		request.onsuccess = () => {
			const db = request.result;
			const rows = db.transaction('photos').objectStore('photos').getAll();
			rows.onsuccess = () => { db.close(); resolve(rows.result.sort((a, b) => a.added_at - b.added_at).map(({ blob, ...photo }) => photo)); };
			rows.onerror = () => { db.close(); reject(rows.error); };
		};
	}));
}

test.describe('Panoramax browser contribution', () => {
	test.describe.configure({ mode: 'serial' });
	test.setTimeout(T(120_000));

	test.beforeAll(async ({ request }) => {
		const created = await request.post(`${API}/auth/register`, { data: { username, password, email: `${username}@example.com` } });
		expect(created.ok(), await created.text()).toBeTruthy();
		userId = (await created.json()).id;
		const session = await request.post(`${API}/auth/token`, { form: { username, password } });
		expect(session.ok()).toBeTruthy();
		token = (await session.json()).access_token;
	});

	test.afterAll(async ({ request }) => {
		if (token) {
			const deleted = await request.delete(`${API}/user/delete`, { headers: { Authorization: `Bearer ${token}` } });
			expect(deleted.ok(), await deleted.text()).toBeTruthy();
		}
	});

	test.beforeEach(async ({ page }) => {
		await page.addInitScript(() => {
			localStorage.setItem('sourceStates', JSON.stringify({ hillview: true, mapillary: false, panoramax: false }));
		});
	});

	test('compact permissions and contextual grant choices keep state until confirmed', async ({ page }) => {
        let authorizations = 0;
        page.on('request', request => { if (request.url().includes('/authorize-upload')) authorizations++; });
        await ready(page, '/settings/upload');
        await expect(page.getByTestId('license-unset')).toBeVisible();
        await expect(page.getByTestId('auto-upload-enabled')).toBeDisabled();
        await expect(page.getByTestId('auto-upload-settings').getByTestId('license-summary')).toHaveCount(0);
        await expect(page.getByTestId('photo-permissions-settings').getByTestId('auto-upload-enabled')).toHaveCount(0);
        await page.getByTestId('panoramax-sharing-checkbox').check();
        await expect(page.getByTestId('auto-upload-enabled')).toBeDisabled();
        await expect(page.getByTestId('contribution-login-notice')).toBeVisible();
        await page.getByTestId('license-change-button').click();
        const dialog = page.getByTestId('license-dialog');
        const ids = await dialog.locator('input[type=radio]').evaluateAll(inputs => inputs.map(input => (input as HTMLInputElement).value));
        expect(ids).toEqual(['full1', 'panoramax_in', 'ccbysa4+osm']);
        await dialog.getByText('Full rights to Hillview', { exact: true }).click();
        await dialog.getByTestId('license-help-full1').click();
        await expect(dialog).toContainText('including paid tiers later');
        await expect(page.getByTestId('license-current')).toHaveText('Not chosen');
        await dialog.getByTestId('license-dialog-cancel').click();
        await expect(page.getByTestId('license-unset')).toBeVisible();
        await chooseUploadLicense(page, 'full1');
        for (const grant of ['full1', 'panoramax_in']) {
            await chooseUploadLicense(page, grant);
            for (const sharing of [false, true]) {
                await page.getByTestId('panoramax-sharing-checkbox').setChecked(sharing);
                await expect(page.getByTestId('contribution-published-license')).toContainText(grant === 'full1' && !sharing ? 'All rights reserved' : 'Panoramax');
            }
        }
        // Choosing CC explicitly offers to turn sharing off; Cancel preserves both.
        await page.getByTestId('license-change-button').click();
        await dialog.getByTestId('license-checkbox').check();
        await expect(dialog).toContainText('sharing will be turned off');
        await dialog.getByTestId('license-dialog-cancel').click();
        await expect(page.getByTestId('license-current')).toHaveText('Panoramax contribution grant');
        await expect(page.getByTestId('panoramax-sharing-checkbox')).toBeChecked();
        await chooseUploadLicense(page, 'ccbysa4+osm');
        await expect(page.getByTestId('panoramax-sharing-checkbox')).not.toBeChecked();
        await page.getByTestId('panoramax-sharing-checkbox').click();
        await expect(dialog).toBeVisible();
        await expect(dialog.getByTestId('license-checkbox')).toHaveCount(0);
        await expect(dialog.getByTestId('license-dialog-confirm')).toBeDisabled();
        await dialog.getByTestId('license-option-panoramax_in').check();
        await page.keyboard.press('Escape');
        await expect(dialog).toHaveCount(0);
        await expect(page.getByTestId('license-current')).toHaveText('CC BY-SA 4.0 + OSM mapping grant');
        await expect(page.getByTestId('panoramax-sharing-checkbox')).not.toBeChecked();
        await page.getByTestId('panoramax-sharing-checkbox').click();
        await confirmLicenseChoice(page, 'full1');
        await expect(page.getByTestId('license-current')).toHaveText('Full rights to Hillview');
        await expect(page.getByTestId('panoramax-sharing-checkbox')).toBeChecked();
        await chooseUploadLicense(page, 'ccbysa4+osm');
        await page.reload();
        await expect(page.getByTestId('license-current')).toHaveText('CC BY-SA 4.0 + OSM mapping grant');
        await expect(page.getByTestId('panoramax-sharing-checkbox')).not.toBeChecked();
        await expect(page.getByTestId('auto-upload-enabled')).not.toBeChecked();
        await expect(page).toHaveURL(/\/settings\/upload$/);
        expect(authorizations).toBe(0);
    });

	test('signing in with fresh preferences accepts no grant and starts no upload', async ({ page }) => {
		await login(page);
		await ready(page, '/settings/upload');
		await expect(page.getByTestId('license-unset')).toBeVisible();
		await expect(page.getByTestId('panoramax-sharing-checkbox')).not.toBeChecked();
		await expect(page.getByTestId('auto-upload-enabled')).toBeDisabled();
		await expect(page.getByTestId('contribution-login-notice')).toHaveCount(0);
	});

	test('registering and signing in preserves explicit choices without enabling uploads', async ({ page, request }) => {
		const newName = `pano_join_${randomUUID().slice(0, 8)}`;
		await ready(page, '/settings/upload');
		await chooseUploadLicense(page, 'panoramax_in');
		await page.getByTestId('panoramax-sharing-checkbox').check();
		try {
			await ready(page, '/login');
			await page.getByTestId('login-toggle-form-button').click();
			await page.getByTestId('login-email-input').fill(`${newName}@example.com`);
			await page.getByTestId('login-username-input').fill(newName);
			await page.getByTestId('login-password-input').fill(password);
			await page.getByTestId('login-submit-button').click();
			await expect(page.getByTestId('login-success-message')).toContainText('Registration successful');
			await login(page, newName);
			await ready(page, '/settings/upload');
			await expect(page.getByTestId('license-current')).toHaveText('Panoramax contribution grant');
			await expect(page.getByTestId('panoramax-sharing-checkbox')).toBeChecked();
			await expect(page.getByTestId('auto-upload-enabled')).not.toBeChecked();
		} finally {
			const session = await request.post(`${API}/auth/token`, { form: { username: newName, password } });
			if (session.ok()) await request.delete(`${API}/user/delete`, { headers: { Authorization: `Bearer ${(await session.json()).access_token}` } });
		}
	});

	test('enabling uploads after login drains a legacy capture without inventing sharing consent', async ({ page, browserName, request }) => {
		test.skip(browserName === 'webkit', 'Playwright WebKit cannot persist Blobs in IndexedDB');
		await login(page);
		const jpeg = fs.readFileSync(path.resolve(import.meta.dirname, '../test-assets/car.jpg')).toString('base64');
		await seedBrowserPhoto(page, jpeg);
		await ready(page, '/settings/upload');
		await chooseUploadLicense(page, 'full1');
		await page.getByTestId('panoramax-sharing-checkbox').check();
		await page.getByTestId('auto-upload-enabled').check();
		await waitForUploadedCount(page, 1);
		const uploaded = (await localPhotos(page))[0];
		const photo = await request.get(`${API}/photos/public/hillview-${uploaded.server_photo_id}`, { headers: { Authorization: `Bearer ${token}` } });
		expect(await photo.json()).toMatchObject({ license_granted: 'full1', panoramax_share: false, license: 'arr' });
	});

	test('CC prompts preserve the capture screen and change only the selected queued photo', async ({ page, browserName }) => {
		test.skip(browserName !== 'chromium', 'Fake camera requires Chromium');
		await page.setViewportSize({ width: 390, height: 844 });
		await addCameraInitScript(page);
		await ready(page, '/settings/upload');
		await chooseUploadLicense(page, 'ccbysa4+osm');
		await ready(page, '/');
		await page.getByTestId('camera-button').click();
		await expect(page.getByTestId('single-capture-button')).toBeEnabled();
		await page.getByTestId('single-capture-button').click();
		await waitForPhotoCount(page, 1);
		const original = (await localPhotos(page))[0];
		await page.getByTestId('capture-panoramax-toggle').click();
		await expect(page.getByTestId('license-dialog-context')).toContainText('Future camera photos');
		await page.getByTestId('license-dialog-cancel').click();
		await expect(page).toHaveURL(/\/$/);
		await expect(page.getByTestId('capture-panoramax-toggle')).toHaveAttribute('aria-pressed', 'false');
		expect((await localPhotos(page))[0]).toMatchObject({ id: original.id, license: 'ccbysa4+osm', panoramax_share: false });
		await page.getByTestId('capture-panoramax-toggle').click();
		await confirmLicenseChoice(page, 'panoramax_in');
		await expect(page.getByTestId('single-capture-button')).toBeEnabled();
		await page.getByTestId('single-capture-button').click();
		await waitForPhotoCount(page, 2);
		expect((await localPhotos(page))[1]).toMatchObject({ license: 'panoramax_in', panoramax_share: true });
		await ready(page, '/device-photos');
		const card = page.getByTestId('photo-card').filter({ hasText: 'CC BY-SA 4.0' });
		await card.getByTestId('photo-panoramax-share-button').click();
		await expect(page.getByTestId('license-dialog-context')).toContainText('Only photo_');
		await page.getByTestId('license-dialog-cancel').click();
		expect((await localPhotos(page))[0].license).toBe('ccbysa4+osm');
		await card.getByTestId('photo-panoramax-share-button').click();
		await confirmLicenseChoice(page, 'full1');
		await expect(page).toHaveURL(/\/device-photos$/);
		const photos = await localPhotos(page);
		expect(photos[0]).toMatchObject({ id: original.id, license: 'full1', panoramax_share: true });
		expect(photos[1]).toMatchObject({ license: 'panoramax_in', panoramax_share: true });
		expect(await page.evaluate(() => JSON.parse(localStorage.getItem('autoUploadLicense')!))).toBe('panoramax_in');
	});

	test('capture snapshots survive default changes and upload after login; owner edits preserve intake', async ({ page, browserName, request }) => {
		test.skip(browserName !== 'chromium', 'Fake camera requires Chromium');
		await page.setViewportSize({ width: 390, height: 844 });
		await addCameraInitScript(page);
		await page.addInitScript(() => {
			const original = CanvasRenderingContext2D.prototype.drawImage;
			CanvasRenderingContext2D.prototype.drawImage = function (...args: any[]) {
				original.apply(this, args as any);
				if (args[0] instanceof HTMLVideoElement) {
					this.fillStyle = '#ff00aa'; this.fillText(String(Date.now()), 2, 20);
				}
			};
		});
		await ready(page, '/');
		await page.getByTestId('camera-button').click();
		await expect(page.getByTestId('single-capture-button')).toBeEnabled();
		const toggle = page.getByTestId('capture-panoramax-toggle');
		const bounds = await toggle.boundingBox();
		const camera = await page.getByTestId('camera-selector-button').boundingBox();
		expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(camera!.y);
		await toggle.click();
		await expect(toggle).toHaveAttribute('aria-pressed', 'true');
		await page.getByTestId('single-capture-button').click();
		await waitForPhotoCount(page, 1);
		expect((await localPhotos(page))[0]).toMatchObject({ license: null, panoramax_share: true, status: 'pending' });
		await ready(page, '/settings/upload');
		await chooseUploadLicense(page, 'full1');
		await page.getByTestId('panoramax-sharing-checkbox').uncheck();
		await ready(page, '/');
		await page.getByTestId('camera-button').click();
		await expect(page.getByTestId('single-capture-button')).toBeEnabled();
		await page.getByTestId('single-capture-button').click();
		await waitForPhotoCount(page, 2);
		expect((await localPhotos(page))[1]).toMatchObject({ license: 'full1', panoramax_share: false });
		await ready(page, '/device-photos');
		await page.getByTestId('photo-panoramax-share-button').first().click();
		expect((await localPhotos(page)).find(photo => photo.license === 'full1').panoramax_share).toBe(true);
		await ready(page, '/settings/upload');
		await chooseUploadLicense(page, 'panoramax_in');
		await page.getByTestId('auto-upload-enabled').check();
		await expect(page.getByTestId('alert-message')).toBeVisible();
		await login(page);
		await waitForUploadedCount(page, 2);
		const uploaded = await localPhotos(page);
		const full = uploaded.find(photo => photo.license === 'full1');
		capturedServerId = full.server_photo_id;
		for (const photo of uploaded) {
			await expect.poll(async () => {
				const response = await request.get(`${API}/photos/public/hillview-${photo.server_photo_id}`, { headers: { Authorization: `Bearer ${token}` } });
				return response.ok() ? (await response.json()).processing_status : response.status();
			}, { timeout: 90_000 }).toBe('completed');
		}
		const preChoice = uploaded.find(photo => photo.license === null);
		const server = await request.get(`${API}/photos/public/hillview-${preChoice.server_photo_id}`, { headers: { Authorization: `Bearer ${token}` } });
		expect(await server.json()).toMatchObject({ license_granted: 'panoramax_in', panoramax_share: true, license: 'panoramax' });
		await ready(page, `/photo/hillview-${capturedServerId}`);
		await expect(page.getByTestId('photo-edit-license-current')).toHaveText('Full rights to Hillview');
		await expect(page.getByTestId('photo-detail-license')).toContainText('Panoramax');
		await page.getByTestId('photo-edit-panoramax-share').uncheck();
		await page.getByTestId('photo-edit-save-button').click();
		await expect(page.getByTestId('photo-detail-license')).toContainText('All rights reserved');
		await expect(page.getByTestId('photo-detail-status')).toContainText('Saved:');
		await expect(page.getByTestId('photo-edit-license-current')).toHaveText('Full rights to Hillview');
		await page.getByTestId('photo-detail-license-history-toggle').click();
		await expect(page.getByTestId('photo-detail-outflow-history')).toContainText('sharing choice');
		expect((await localPhotos(page)).find(photo => photo.server_photo_id === capturedServerId)).toMatchObject({ license: 'full1', panoramax_share: false });
	});

	test('an existing CC photo keeps its draft and URL while resolving Panoramax consent', async ({ page, request }) => {
		test.skip(!capturedServerId, 'Requires the captured photo');
		await login(page);
		await ready(page, `/photo/hillview-${capturedServerId}`);
		await chooseUploadLicense(page, 'ccbysa4+osm', page.getByTestId('photo-edit-license-button'));
		await page.getByTestId('photo-edit-save-button').click();
		await expect(page.getByTestId('photo-detail-status')).toContainText('Saved:');
		await page.getByTestId('photo-edit-title-input').fill('Keep this unsaved description of the view');
		await page.getByTestId('photo-edit-panoramax-share').click();
		await expect(page.getByTestId('license-dialog-context')).toContainText('Only this photo');
		await page.getByTestId('license-dialog-cancel').click();
		await expect(page.getByTestId('photo-edit-title-input')).toHaveValue('Keep this unsaved description of the view');
		await expect(page.getByTestId('photo-edit-panoramax-share')).not.toBeChecked();
		await page.getByTestId('photo-edit-panoramax-share').click();
		await confirmLicenseChoice(page, 'panoramax_in');
		await expect(page.getByTestId('photo-edit-license-current')).toHaveText('Panoramax contribution grant');
		await expect(page).toHaveURL(new RegExp(`/photo/hillview-${capturedServerId}$`));
		const beforeSave = await request.get(`${API}/photos/public/hillview-${capturedServerId}`, { headers: { Authorization: `Bearer ${token}` } });
		expect(await beforeSave.json()).toMatchObject({ license_granted: 'ccbysa4+osm', panoramax_share: false });
		await page.getByTestId('photo-edit-save-button').click();
		await expect(page.getByTestId('photo-detail-license')).toContainText('Panoramax');
		await expect(page.getByTestId('photo-detail-status')).toContainText('Saved:');
		const afterSave = await request.get(`${API}/photos/public/hillview-${capturedServerId}`, { headers: { Authorization: `Bearer ${token}` } });
		expect(await afterSave.json()).toMatchObject({ id: capturedServerId, license_granted: 'panoramax_in', panoramax_share: true });
		capturedGrant = 'panoramax_in';
		expect(await page.evaluate(() => localStorage.getItem('autoUploadLicense'))).toBeNull();
	});

	test('file-upload defaults are independent and the batch sends explicit consent', async ({ page, request }) => {
		await login(page);
		await ready(page, '/settings/upload');
		await chooseUploadLicense(page, 'full1');
		await page.getByTestId('panoramax-sharing-checkbox').uncheck();
		await ready(page, '/photos');
		await chooseUploadLicense(page, 'ccbysa4+osm');
		await page.getByTestId('photo-file-input').setInputFiles(path.resolve(import.meta.dirname, '../test-assets/prosecke-skaly-fixture.jpg'));
		await page.getByLabel('Description (optional):').fill('Keep my selected file and description');
		await page.getByTestId('panoramax-sharing-checkbox').click();
		await expect(page.getByTestId('license-dialog-context')).toContainText('next file-upload batch');
		await page.getByTestId('license-dialog-cancel').click();
		await expect(page.getByLabel('Description (optional):')).toHaveValue('Keep my selected file and description');
		expect(await page.getByTestId('photo-file-input').evaluate(input => (input as HTMLInputElement).files?.length)).toBe(1);
		await page.getByTestId('panoramax-sharing-checkbox').click();
		await confirmLicenseChoice(page, 'panoramax_in');
		const authorization = page.waitForRequest(request => request.url().includes('/photos/authorize-upload') && request.method() === 'POST');
		const authorized = page.waitForResponse(response => response.url().includes('/photos/authorize-upload') && response.request().method() === 'POST');
		await page.getByTestId('upload-submit-button').click();
		expect((await authorization).postDataJSON()).toMatchObject({ license: 'panoramax_in', panoramax_share: true });
		const id = (await (await authorized).json()).photo_id;
		manualServerId = id;
		await expect.poll(async () => {
			const response = await request.get(`${API}/photos/public/hillview-${id}`, { headers: { Authorization: `Bearer ${token}` } });
			return response.ok() ? (await response.json()).processing_status : response.status();
		}, { timeout: 90_000 }).toBe('completed');
		await ready(page, '/settings/upload');
		await expect(page.getByTestId('license-current')).toHaveText('Full rights to Hillview');
		await expect(page.getByTestId('panoramax-sharing-checkbox')).not.toBeChecked();
	});

	test('moderator approval and account contribution never substitute for owner consent', async ({ page }) => {
		const photoId = capturedServerId || manualServerId;
		test.skip(!photoId, 'Requires an uploaded photo');
		await login(page, 'admin', 'StrongAdminPassword123!');
		await ready(page, `/photo/hillview-${photoId}`);
		await expect(page.getByTestId('photo-edit-panoramax-share')).toHaveCount(0);
		await expect(page.getByTestId('photo-edit-license-current')).toHaveText(capturedServerId && capturedGrant === 'full1' ? 'Full rights to Hillview' : 'Panoramax contribution grant');
		await page.getByTestId('photo-edit-panoramax-approved').uncheck();
		await page.getByTestId('photo-edit-save-button').click();
		await expect(page.getByTestId('photo-detail-status')).toContainText('Saved: panoramax_approved');
		await page.reload();
		await expect(page.getByTestId('photo-edit-panoramax-approved')).not.toBeChecked();
		await ready(page, '/admin/users');
		await page.getByTestId('admin-users-search').fill(username);
		const row = page.getByTestId('admin-user-row').filter({ has: page.locator(`[href="/users/${userId}"]`) });
		await expect(row).toHaveCount(1);
		await row.getByTestId('admin-user-panoramax').click();
		await expect(row.getByTestId('admin-user-panoramax')).toHaveText('Panoramax: disabled');
		await row.getByTestId('admin-user-panoramax').click();
		await expect(row.getByTestId('admin-user-panoramax')).toHaveText('Panoramax: enabled');
	});
});
