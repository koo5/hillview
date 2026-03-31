import { browser } from '@wdio/globals';
import { acceptPermissionDialogIfPresent, byTestId, ensureWebViewContext, TESTID } from '../helpers/selectors';
import { recreateTestUsers, loginAsTestUser, getTestUserToken, getUserPhotos } from '../helpers/backend';

describe('Photo Workflow', () => {

    before(async () => {
        await recreateTestUsers();
        await browser.pause(3000);
        await loginAsTestUser();

        // Enable mock camera — draws timestamp overlay on real camera frames
        // so consecutive captures produce unique images (avoids duplicate detection).
        await ensureWebViewContext();
        await browser.execute(() => localStorage.setItem('mockCamera', 'true'));
    });

    let permissionsGranted = false;

    /**
     * Open camera, handle permissions on first call, and capture a photo.
     */
    async function openCameraAndCapture(): Promise<void> {
        const cameraBtn = await byTestId(TESTID.cameraButton);
        await cameraBtn.waitForDisplayed({ timeout: 10000 });
        await cameraBtn.click();
        await browser.pause(1000);

        if (!permissionsGranted) {
            await acceptPermissionDialogIfPresent();
            await browser.pause(1000);

            const allowCameraBtn = await byTestId(TESTID.allowCameraBtn);
            await allowCameraBtn.waitForExist({ timeout: 10000 });
            await allowCameraBtn.click();
            await browser.pause(1000);

            await acceptPermissionDialogIfPresent();
            await browser.pause(2000);
            permissionsGranted = true;
        } else {
            await browser.pause(2000);
        }

        const captureBtn = await byTestId('single-capture-button');
        await captureBtn.waitForExist({ timeout: 10000 });
        await captureBtn.click();
        await browser.pause(3000);
    }

    async function closeCamera(): Promise<void> {
        const cameraBtn = await byTestId(TESTID.cameraButton);
        await cameraBtn.click();
        await browser.pause(2000);
    }

    it('should capture and enable auto-upload via prompt', async () => {
        await openCameraAndCapture();

        // Auto-upload prompt appears in camera view after first capture
        await ensureWebViewContext();
        const configureBtn = await $('[data-testid="configure-auto-upload"]');
        await configureBtn.waitForDisplayed({ timeout: 12000 });
        await configureBtn.click();
        await browser.pause(2000);

        // Now on /settings/upload — accept license first
        await ensureWebViewContext();
        const licenseCheckbox = await $('[data-testid="license-checkbox"]');
        await licenseCheckbox.waitForDisplayed({ timeout: 5000 });
        if (!(await licenseCheckbox.isSelected())) {
            await licenseCheckbox.click();
            await browser.pause(1000);
        }

        // Enable auto-upload
        const enableRadio = await $('[data-testid="auto-upload-enabled"]');
        await enableRadio.waitForDisplayed({ timeout: 5000 });
        await enableRadio.click();
        await browser.pause(1000);

        // Navigate back to map
        await browser.back();
        await browser.pause(2000);
    });

    it('should capture with auto-upload enabled', async () => {
        await openCameraAndCapture();

        const captureBtn = await byTestId('single-capture-button');
        expect(await captureBtn.isExisting()).toBe(true);

        await closeCamera();
    });

    it('should show photo markers on map', async () => {
        await ensureWebViewContext();

        // Toggle hillview source off/on to trigger area reloads until markers appear
        const deadline = Date.now() + 30000;
        let markers: WebdriverIO.ElementArray = [];

        while (Date.now() < deadline) {
            markers = await $$('[data-testid^="photo-marker-"]');
            if (markers.length > 0) break;

            const toggle = await $('[data-testid="source-toggle-hillview"]');
            if (await toggle.isExisting()) {
                await toggle.click();
                await browser.pause(1000);
                await toggle.click();
            }

            console.log(`Waiting for markers... (${Math.round((deadline - Date.now()) / 1000)}s left)`);
            await browser.pause(3000);
        }

        console.log(`Found ${markers.length} photo markers on map`);
        expect(markers.length).toBeGreaterThanOrEqual(1);

        for (let i = 0; i < Math.min(markers.length, 5); i++) {
            const photoId = await markers[i].getAttribute('data-photo-id');
            const isPlaceholder = await markers[i].getAttribute('data-is-placeholder');
            const source = await markers[i].getAttribute('data-source');
            console.log(`  Marker ${i}: id=${photoId}, placeholder=${isPlaceholder}, source=${source}`);
        }
    });

    it('should upload photos to backend', async () => {
        const token = await getTestUserToken();

        // Poll for uploaded photos — upload pipeline needs time
        let photos = { count: 0, ids: [] as string[] };
        const deadline = Date.now() + 30000;

        while (Date.now() < deadline) {
            photos = await getUserPhotos(token);
            if (photos.count > 0) break;
            console.log(`Waiting for uploads... (${Math.round((deadline - Date.now()) / 1000)}s left)`);
            await browser.pause(3000);
        }

        console.log(`Backend has ${photos.count} photos for test user: ${photos.ids.join(', ')}`);
        expect(photos.count).toBeGreaterThanOrEqual(1);
    });
});
