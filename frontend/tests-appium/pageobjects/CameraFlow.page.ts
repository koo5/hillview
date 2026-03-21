import { $ } from '@wdio/globals';
import { byTestId, ensureNativeContext, ensureWebViewContext, TESTID } from '../helpers/selectors';

/**
 * Page object for camera and photo capture interactions.
 * The camera UI is rendered in the WebView (Svelte CameraCapture component),
 * not as a native Android camera activity.
 */
export class CameraFlowPage {

    async handlePermissions(): Promise<void> {
        console.log('📋 Handling camera and location permissions...');
        await ensureNativeContext();

        const permissionButtons = [
            { selector: 'android=new UiSelector().text("Allow")', name: 'Allow' },
            { selector: 'android=new UiSelector().text("While using the app")', name: 'While using app' },
            { selector: 'android=new UiSelector().textContains("Allow")', name: 'Allow (contains)' }
        ];

        for (const button of permissionButtons) {
            try {
                const permissionButton = await $(button.selector);
                if (await permissionButton.isDisplayed()) {
                    console.log(`✅ Granting permission: ${button.name}`);
                    await permissionButton.click();
                    await driver.pause(2000);
                }
            } catch (e) {
                // Permission prompt not found, continue
            }
        }

        console.log('✅ Permission handling completed');
    }

    async capturePhoto(): Promise<boolean> {
        console.log('📸 Attempting to capture photo...');

        await driver.pause(2000); // Wait for camera to initialize

        try {
            // Camera UI is in the WebView — use data-testid selectors
            const captureBtn = await byTestId('single-capture-button');
            if (await captureBtn.isDisplayed()) {
                console.log('📸 Using single capture button');
                await captureBtn.click();
                await driver.pause(3000);
                return true;
            }

            console.log('⚠️ Could not find capture button');
            return false;

        } catch (e) {
            console.error('❌ Photo capture failed:', e.message);
            return false;
        }
    }

    async returnToMainApp(maxAttempts: number = 3): Promise<boolean> {
        console.log('↩️ Returning to main app...');

        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            console.log(`↩️ Back attempt ${attempt}/${maxAttempts}`);

            await driver.back();
            await driver.pause(3000);

            // Check if we're back in the main app by looking for hamburger menu
            try {
                const menu = await byTestId(TESTID.hamburgerMenu);
                if (await menu.isDisplayed()) {
                    console.log('✅ Successfully returned to main app');
                    return true;
                }
            } catch (e) {
                console.log(`ℹ️ Not back to main app yet (attempt ${attempt})`);
            }

            // Special recovery for final attempt
            if (attempt === maxAttempts - 1) {
                console.log('🏠 Trying home button approach...');
                await ensureNativeContext();
                await driver.pressKeyCode(3); // Android HOME key
                await driver.pause(2000);

                // Reactivate the app
                await driver.activateApp('cz.hillviedev');
                await driver.pause(3000);
            }
        }

        console.log('⚠️ Could not return to main app reliably');
        return false;
    }

    async takeScreenshotAtStep(stepName: string): Promise<void> {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = `camera-${stepName}-${timestamp}.png`;

        try {
            await ensureNativeContext();
            await driver.saveScreenshot(`./test-results/${filename}`);
            console.log(`📸 Camera screenshot saved: ${filename}`);
        } catch (e) {
            console.warn(`⚠️ Camera screenshot failed: ${e.message}`);
        }
    }

    async completeCameraWorkflow(): Promise<boolean> {
        console.log('📸 Starting complete camera workflow...');

        try {
            // Step 1: Handle permissions
            await this.handlePermissions();
            await this.takeScreenshotAtStep('permissions-handled');

            // Step 2: Capture photo
            const captureSuccess = await this.capturePhoto();
            if (!captureSuccess) {
                console.error('❌ Photo capture failed');
                return false;
            }
            await this.takeScreenshotAtStep('photo-captured');

            // Step 3: Return to main app
            const returnSuccess = await this.returnToMainApp();
            if (!returnSuccess) {
                console.error('❌ Could not return to main app');
                return false;
            }
            await this.takeScreenshotAtStep('returned-to-app');

            console.log('🎉 Camera workflow completed successfully');
            return true;

        } catch (error) {
            console.error('❌ Camera workflow failed:', error.message);
            await this.takeScreenshotAtStep('workflow-error');
            return false;
        }
    }
}
