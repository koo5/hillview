import { $ } from '@wdio/globals';
import { checkForCriticalErrors } from '../helpers/app-launcher';

/**
 * Page object for the main Hillview app interactions
 */
export class HillviewAppPage {
    // Selectors
    private get hamburgerMenu() {
        // Use data-testid which requires WebView context - main page uses hamburger-menu
        return $('[data-testid="hamburger-menu"]');
    }

    private get cameraButton() {
        return $('android=new UiSelector().text("Take photo")');
    }

    private get webView() {
        return $('android.webkit.WebView');
    }

    // Navigation actions
    async openMenu(): Promise<void> {
        console.log('🍔 Opening hamburger menu...');
        // Switch to WebView context to access data-testid
        await driver.switchContext('WEBVIEW_cz.hillviedev');
        await this.hamburgerMenu.waitForDisplayed({ timeout: 10000 });
        await this.hamburgerMenu.click();
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
        await this.cameraButton.waitForDisplayed({ timeout: 10000 });
        await this.cameraButton.click();
        await driver.pause(3000);
        console.log('✅ Entered camera mode');
    }

    async waitForAppReady(): Promise<void> {
        console.log('⏳ Waiting for app to be ready...');
        try {
            await this.webView.waitForExist({ timeout: 10000 });
            await driver.pause(2000);
            console.log('✅ App is ready (WebView found)');
        } catch (error) {
            console.log('⚠️ WebView not immediately available, checking basic app functionality...');
            // Fallback: check if app is at least responsive with basic elements
            const menuExists = await this.hamburgerMenu.isExisting();
            if (menuExists) {
                console.log('✅ App is ready (menu button found)');
                return;
            }
            throw new Error('App not ready - no WebView and no menu button found');
        }
    }

    async verifyAppIsResponsive(): Promise<boolean> {
        try {
            // Check basic app responsiveness
            const currentActivity = await driver.getCurrentActivity();
            if (!currentActivity.includes('MainActivity')) {
                return false;
            }

            // Check app state
            const appState = await driver.queryAppState('cz.hillviedev');
            if (appState < 2) { // Not running
                return false;
            }

            // Check for critical UI elements
            const webViewExists = await this.webView.isExisting();
            if (!webViewExists) {
                return false;
            }

            return true;
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
        // Use the centralized critical error check
        await checkForCriticalErrors();
    }

    async getCameraButtonTexts(): Promise<string[]> {
        const possibleTexts = ['Take photo', 'Take photos', 'Camera'];
        const foundTexts: string[] = [];

        for (const text of possibleTexts) {
            try {
                const button = await $(`android=new UiSelector().text("${text}")`);
                if (await button.isDisplayed()) {
                    foundTexts.push(text);
                }
            } catch (e) {
                // Button not found with this text
            }
        }

        return foundTexts;
    }
}
