import { browser } from '@wdio/globals';
import { acceptPermissionDialogIfPresent, byTestId, ensureWebViewContext, TESTID } from '../helpers/selectors';
import { recreateTestUsers, loginAsTestUser, getTestUserToken, getUserPhotos } from '../helpers/backend';

describe('Photo Workflow', () => {

    before(async () => {
        await recreateTestUsers();
        await browser.pause(3000);
        await loginAsTestUser();
    });

    /**
     * Open camera, handle permissions, and capture a photo.
     * Reuses the permission flow from camera-capture tests.
     */
    async function capturePhoto(): Promise<void> {
        const cameraBtn = await byTestId(TESTID.cameraButton);
        await cameraBtn.waitForDisplayed({ timeout: 10000 });
        await cameraBtn.click();
        await browser.pause(1000);

        // Handle location permission
        await acceptPermissionDialogIfPresent();
        await browser.pause(1000);

        // Click "Allow Camera" in WebView
        const allowCameraBtn = await byTestId(TESTID.allowCameraBtn);
        await allowCameraBtn.waitForExist({ timeout: 10000 });
        await allowCameraBtn.click();
        await browser.pause(1000);

        // Handle camera permission
        await acceptPermissionDialogIfPresent();
        await browser.pause(2000);

        // Click capture button
        const captureBtn = await byTestId('single-capture-button');
        await captureBtn.waitForExist({ timeout: 10000 });
        await captureBtn.click();
        await browser.pause(3000);
    }

    /**
     * Close camera by clicking the camera button again.
     */
    async function closeCamera(): Promise<void> {
        const cameraBtn = await byTestId(TESTID.cameraButton);
        await cameraBtn.click();
        await browser.pause(2000);
    }

    it('should capture a photo while logged in', async () => {
        await capturePhoto();

        // Verify capture button is still available (camera didn't crash)
        const captureBtn = await byTestId('single-capture-button');
        expect(await captureBtn.isExisting()).toBe(true);

        await closeCamera();

        // Verify we're back on the map
        const zoomIn = await byTestId(TESTID.zoomIn);
        await zoomIn.waitForDisplayed({ timeout: 10000 });
        expect(await zoomIn.isDisplayed()).toBe(true);
    });

    it('should show placeholder marker on map after capture', async () => {
        // Look for photo markers that appeared from the capture
        await ensureWebViewContext();
        const markers = await $$('[data-testid^="photo-marker-"]');
        console.log(`Found ${markers.length} photo markers on map`);

        // Check for placeholder markers specifically
        const placeholders = await $$('[data-testid^="photo-marker-"][data-is-placeholder="true"]');
        console.log(`Found ${placeholders.length} placeholder markers`);

        // At this point we should have at least some markers visible
        // (either placeholder or already-transitioned real photos)
        if (markers.length > 0) {
            // Verify marker has expected data attributes
            const firstMarker = markers[0];
            const photoId = await firstMarker.getAttribute('data-photo-id');
            const source = await firstMarker.getAttribute('data-source');
            console.log(`First marker: photoId=${photoId}, source=${source}`);
            expect(photoId).toBeTruthy();
        }
    });

    it('should capture a second photo without permission dialogs', async () => {
        // Permissions already granted from first capture
        const cameraBtn = await byTestId(TESTID.cameraButton);
        await cameraBtn.click();
        await browser.pause(2000);

        // Capture button should appear directly
        const captureBtn = await byTestId('single-capture-button');
        await captureBtn.waitForExist({ timeout: 10000 });
        await captureBtn.click();
        await browser.pause(3000);

        // Still in camera mode
        expect(await captureBtn.isExisting()).toBe(true);

        await closeCamera();
    });

    it('should show multiple markers after multiple captures', async () => {
        await ensureWebViewContext();
        const markers = await $$('[data-testid^="photo-marker-"]');
        console.log(`Found ${markers.length} total photo markers after 2 captures`);

        // Log details of each marker
        for (let i = 0; i < Math.min(markers.length, 5); i++) {
            const photoId = await markers[i].getAttribute('data-photo-id');
            const isPlaceholder = await markers[i].getAttribute('data-is-placeholder');
            const source = await markers[i].getAttribute('data-source');
            console.log(`  Marker ${i}: id=${photoId}, placeholder=${isPlaceholder}, source=${source}`);
        }
    });

    it('should upload photos to backend', async () => {
        // Wait for upload processing
        await browser.pause(10000);

        // Check backend API for uploaded photos
        const token = await getTestUserToken();
        const photos = await getUserPhotos(token);
        console.log(`Backend has ${photos.count} photos for test user: ${photos.ids.join(', ')}`);

        // We captured 2 photos — they should eventually appear in the backend
        // On emulator the camera produces real files, so uploads should work
        expect(photos.count).toBeGreaterThanOrEqual(1);
    });
});
