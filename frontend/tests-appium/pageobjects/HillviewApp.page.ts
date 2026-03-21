import { $ } from '@wdio/globals';
import { checkForCriticalErrors } from '../helpers/app-launcher';
import { byTestId, ensureNativeContext, TESTID } from '../helpers/selectors';

/**
 * Page object for the main Hillview app interactions
 */
export class HillviewAppPage {
    // Navigation actions
    async openMenu(): Promise<void> {
        console.log('🍔 Opening hamburger menu...');
        const menu = await byTestId(TESTID.hamburgerMenu);
        await menu.waitForDisplayed({ timeout: 10000 });
        await menu.click();
        await driver.pause(2000);
        console.log('✅ Menu opened');
    }

    async closeMenu(): Promise<void> {
        console.log('↩️ Closing menu...');
        await driver.back();
        await driver.pause(2000);
        console.log('✅ Menu closed');
    }

    async clickCameraButton(): Promise<void> {
        console.log('📸 Clicking camera button...');
        const btn = await byTestId(TESTID.cameraButton);
        await btn.waitForDisplayed({ timeout: 10000 });
        await btn.click();
        await driver.pause(3000);
        console.log('✅ Entered camera mode');
    }

    async waitForAppReady(): Promise<void> {
        console.log('⏳ Waiting for app to be ready...');
        try {
            await ensureNativeContext();
            const webView = await $('android.webkit.WebView');
            await webView.waitForExist({ timeout: 10000 });
            await driver.pause(2000);
            console.log('✅ App is ready (WebView found)');
        } catch (error) {
            console.log('⚠️ WebView not immediately available, checking basic app functionality...');
            try {
                const menu = await byTestId(TESTID.hamburgerMenu);
                if (await menu.isExisting()) {
                    console.log('✅ App is ready (menu button found)');
                    return;
                }
            } catch (e) {
                // fall through
            }
            throw new Error('App not ready - no WebView and no menu button found');
        }
    }

    async verifyAppIsResponsive(): Promise<boolean> {
        try {
            const currentActivity = await driver.getCurrentActivity();
            if (!currentActivity.includes('MainActivity')) {
                return false;
            }

            const appState = await driver.queryAppState('cz.hillviedev');
            if (appState < 2) {
                return false;
            }

            await ensureNativeContext();
            const webView = await $('android.webkit.WebView');
            return await webView.isExisting();
        } catch (error) {
            console.error('App responsiveness check failed:', error.message);
            return false;
        }
    }

    async takeScreenshot(name: string): Promise<void> {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = `${name}-${timestamp}.png`;

        try {
            await driver.saveScreenshot(`./test-results/${filename}`);
            console.log(`📸 Screenshot saved: ${filename}`);
        } catch (e) {
            console.warn(`⚠️ Screenshot failed: ${e.message}`);
        }
    }

    async checkForCriticalError(): Promise<void> {
        console.log('🔍 Page object delegating to centralized critical error check...');
        await checkForCriticalErrors();
    }
}
