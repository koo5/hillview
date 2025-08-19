import { $ } from '@wdio/globals';

/**
 * Page object for the main Hillview app interactions
 */
export class HillviewAppPage {
    // Selectors
    private get hamburgerMenu() { 
        return $('android=new UiSelector().text("Toggle menu")'); 
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
        await this.webView.waitForExist({ timeout: 15000 });
        await driver.pause(2000);
        console.log('✅ App is ready');
    }

    async verifyAppIsResponsive(): Promise<boolean> {
        try {
            // Check basic app responsiveness
            const currentActivity = await driver.getCurrentActivity();
            if (!currentActivity.includes('MainActivity')) {
                return false;
            }
            
            // Check app state
            const appState = await driver.queryAppState('io.github.koo5.hillview.dev');
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
        console.log('🔍 Page object checking for critical error: "error sending request"...');
        
        const errorEl = await $('//*[contains(@text, "error sending request")]');
        if (await errorEl.isExisting()) {
            const errorText = await errorEl.getText();
            console.error(`❌ CRITICAL ERROR DETECTED: "${errorText}"`);
            await this.takeScreenshot('page-critical-error-sending-request');
            
            // Fail the test immediately
            throw new Error(`Test failed due to critical error in app: "${errorText}". This indicates backend connectivity issues.`);
        }
        
        console.log('✅ No critical errors detected in page object');
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