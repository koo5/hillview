import { $ } from '@wdio/globals';

/**
 * Page object for camera and photo capture interactions
 */
export class CameraFlowPage {

    async handlePermissions(): Promise<void> {
        console.log('📋 Handling camera and location permissions...');

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
            // Try app-specific capture button first
            const appCameraButton = await $('android=new UiSelector().text("Capture")');
            if (await appCameraButton.isDisplayed()) {
                console.log('📸 Using app camera capture button');
                await appCameraButton.click();
                await driver.pause(3000);
                return true;
            }

            // Could add other capture methods here (native camera, etc.)
            console.log('⚠️ Could not find capture mechanism');
            return false;

        } catch (e) {
            console.error('❌ Photo capture failed:', e.message);
            return false;
        }
    }

    async confirmPhoto(): Promise<boolean> {
        console.log('✅ Looking for photo confirmation options...');
        await driver.pause(2000); // Wait for confirmation UI to appear

        const confirmButtons = [
            'android=new UiSelector().text("OK")',
            'android=new UiSelector().text("Save")',
            'android=new UiSelector().text("Done")',
            'android=new UiSelector().text("Accept")',
            'android=new UiSelector().text("✓")', // Checkmark
            'android=new UiSelector().description("Done")',
            'android=new UiSelector().description("OK")',
            'android=new UiSelector().description("Save")',
            'android=new UiSelector().resourceId("android:id/button1")', // Standard OK button
        ];

        for (const buttonSelector of confirmButtons) {
            try {
                const confirmButton = await $(buttonSelector);
                if (await confirmButton.isDisplayed()) {
                    console.log(`✅ Confirming photo with: ${buttonSelector}`);
                    await confirmButton.click();
                    await driver.pause(3000);
                    return true;
                }
            } catch (e) {
                // Continue trying other confirm buttons
            }
        }

        console.log('ℹ️ No explicit confirmation required - photo may be auto-saved');
        return true; // Assume success if no confirmation needed
    }

    async returnToMainApp(maxAttempts: number = 3): Promise<boolean> {
        console.log('↩️ Returning to main app...');

        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            console.log(`↩️ Back attempt ${attempt}/${maxAttempts}`);

            await driver.back();
            await driver.pause(3000);

            // Check if we're back in the main app by looking for hamburger menu
            try {
                const hamburgerCheck = await $('android=new UiSelector().text("Toggle menu")');
                if (await hamburgerCheck.isDisplayed()) {
                    console.log('✅ Successfully returned to main app');
                    return true;
                }
            } catch (e) {
                console.log(`ℹ️ Not back to main app yet (attempt ${attempt})`);
            }

            // Special recovery for final attempt
            if (attempt === maxAttempts - 1) {
                console.log('🏠 Trying home button approach...');
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

            // Step 3: Confirm photo
            const confirmSuccess = await this.confirmPhoto();
            if (!confirmSuccess) {
                console.error('❌ Photo confirmation failed');
                return false;
            }
            await this.takeScreenshotAtStep('photo-confirmed');

            // Step 4: Return to main app
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
