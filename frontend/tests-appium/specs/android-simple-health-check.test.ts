import { browser } from '@wdio/globals';
import { acceptPermissionDialogIfPresent, byTestId, ensureNativeContext, ensureWebViewContext, TESTID } from '../helpers/selectors';
import { recreateTestUsers } from '../helpers/backend';

describe('Android Simple Health Check', () => {

    before(async () => {
        await recreateTestUsers();
    });

    it('should launch app with WebView', async () => {
        await browser.pause(3000);
        await ensureNativeContext();

        const pageSource = await browser.getPageSource();
        expect(pageSource).toContain('android.webkit.WebView');
        expect(pageSource).toContain('cz.hillviedev');
    });

    it('should have core UI elements', async () => {
        const menuBtn = await byTestId(TESTID.hamburgerMenu);
        await menuBtn.waitForDisplayed({ timeout: 10000 });

        const cameraBtn = await byTestId(TESTID.cameraButton);
        expect(await cameraBtn.isDisplayed()).toBe(true);

        const zoomIn = await byTestId(TESTID.zoomIn);
        expect(await zoomIn.isDisplayed()).toBe(true);
    });

    it('should open and close menu', async () => {
        const menuBtn = await byTestId(TESTID.hamburgerMenu);
        await menuBtn.click();
        await browser.pause(1000);

        await ensureWebViewContext();
        const nav = await $('nav');
        expect(await nav.isDisplayed()).toBe(true);

        const menuBtn2 = await byTestId(TESTID.hamburgerMenu);
        await menuBtn2.click();
        await browser.pause(500);
    });

    it('should open camera view', async () => {
        const cameraBtn = await byTestId(TESTID.cameraButton);
        await cameraBtn.click();
        await browser.pause(1000);

        // Accept location permission dialog (native)
        await acceptPermissionDialogIfPresent();
        await browser.pause(1000);

        // Click "Allow Camera" button in WebView
        const allowCameraBtn = await byTestId('allow-camera-btn');
        await allowCameraBtn.waitForExist({ timeout: 10000 });
        await allowCameraBtn.click();
        await browser.pause(1000);

        // Accept camera permission dialog (native)
        await acceptPermissionDialogIfPresent();
        await browser.pause(2000);

        const captureBtn = await byTestId('single-capture-button');
        await captureBtn.waitForExist({ timeout: 10000 });
        expect(await captureBtn.isDisplayed()).toBe(true);

        // Close camera
        const cameraBtnAgain = await byTestId(TESTID.cameraButton);
        await cameraBtnAgain.click();
        await browser.pause(1000);
    });
});
