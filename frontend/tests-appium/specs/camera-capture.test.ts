import { browser } from '@wdio/globals';
import { acceptPermissionDialogIfPresent, byTestId, ensureWebViewContext, TESTID } from '../helpers/selectors';
import { recreateTestUsers } from '../helpers/backend';

describe('Camera Capture', () => {

    before(async () => {
        await recreateTestUsers();
        await browser.pause(3000);
    });

    it('should open camera and see capture button', async () => {
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

        // Verify capture button is visible
        const captureBtn = await byTestId('single-capture-button');
        await captureBtn.waitForExist({ timeout: 10000 });
        expect(await captureBtn.isDisplayed()).toBe(true);
    });

    it('should capture a photo', async () => {
        const captureBtn = await byTestId('single-capture-button');
        await captureBtn.click();
        await browser.pause(3000);

        // After capture, button should still be available for next photo
        const captureBtnAgain = await byTestId('single-capture-button');
        expect(await captureBtnAgain.isExisting()).toBe(true);
    });

    it('should close camera and return to map', async () => {
        const cameraBtn = await byTestId(TESTID.cameraButton);
        await cameraBtn.click();
        await browser.pause(1000);

        // Verify map controls are visible again
        const zoomIn = await byTestId(TESTID.zoomIn);
        await zoomIn.waitForDisplayed({ timeout: 10000 });
        expect(await zoomIn.isDisplayed()).toBe(true);
    });

    it('should reopen camera without permission dialogs', async () => {
        const cameraBtn = await byTestId(TESTID.cameraButton);
        await cameraBtn.click();
        await browser.pause(2000);

        // Permissions already granted — capture button should appear directly
        const captureBtn = await byTestId('single-capture-button');
        await captureBtn.waitForExist({ timeout: 10000 });
        expect(await captureBtn.isDisplayed()).toBe(true);

        // Close camera
        const cameraBtnAgain = await byTestId(TESTID.cameraButton);
        await cameraBtnAgain.click();
        await browser.pause(1000);
    });
});
