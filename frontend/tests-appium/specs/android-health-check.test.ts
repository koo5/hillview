import { browser } from '@wdio/globals';
import { byTestId, ensureNativeContext, TESTID } from '../helpers/selectors';
import { recreateTestUsers } from '../helpers/backend';

describe('Android App Health Check', () => {

    before(async () => {
        await recreateTestUsers();
        // Wait for app to fully load WebView
        await browser.pause(3000);
    });

    it('should have no error messages visible', async () => {
        await ensureNativeContext();
        const errorPatterns = [
            'error sending request',
            'connection failed',
            'network error',
            'tauri error'
        ];

        for (const pattern of errorPatterns) {
            const errorEl = await $(`//*[contains(@text, "${pattern}") or contains(@content-desc, "${pattern}")]`);
            expect(await errorEl.isExisting()).toBe(false);
        }
    });

    it('should have core UI elements', async () => {
        const menuBtn = await byTestId(TESTID.hamburgerMenu);
        await menuBtn.waitForDisplayed({ timeout: 10000 });

        const zoomInBtn = await byTestId(TESTID.zoomIn);
        expect(await zoomInBtn.isDisplayed()).toBe(true);

        const cameraBtn = await byTestId(TESTID.cameraButton);
        expect(await cameraBtn.isDisplayed()).toBe(true);
    });

    it('should have WebView loaded', async () => {
        await ensureNativeContext();
        const webViews = await $$('android.webkit.WebView');
        expect(webViews.length).toBeGreaterThan(0);
    });
});
