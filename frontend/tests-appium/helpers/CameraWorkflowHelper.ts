import { $ } from '@wdio/globals';
import { byTestId, ensureNativeContext, ensureWebViewContext, TESTID } from './selectors';

/**
 * Comprehensive helper for camera workflow operations.
 * The camera UI is rendered in the WebView (Svelte CameraCapture component).
 * Only permission dialogs are native Android UI.
 */
export class CameraWorkflowHelper {
    /**
     * Opens camera mode by finding and clicking the camera button
     */
    async openCamera(): Promise<void> {
        console.log('📸 Looking for camera button...');
        const cameraButton = await byTestId(TESTID.cameraButton);
        await cameraButton.click();
        console.log('✅ Clicked camera button');
        await driver.pause(2000);
        console.log('📸 Opened camera mode');
    }

    /**
     * Closes camera mode by clicking the camera button again
     */
    async closeCamera(): Promise<void> {
        console.log('📸 Looking for close camera button...');
        const cameraButton = await byTestId(TESTID.cameraButton);
        await cameraButton.click();
        console.log('✅ Clicked camera button to close');
        await driver.pause(2000);
        console.log('📸 Closed camera mode');
    }

    /**
     * Handles permission dialogs that may appear (native Android UI)
     */
    async handlePermissionDialogs(): Promise<void> {
        console.log('📋 Handling potential permission dialogs...');
        await ensureNativeContext();

        const permissionOptions = [
            { text: 'While using the app', label: 'While using the app' },
            { text: 'Only this time', label: 'Only this time' },
            { text: 'Allow', label: 'Allow' },
        ];

        for (const opt of permissionOptions) {
            try {
                const button = await $(`android=new UiSelector().text("${opt.text}")`);
                if (await button.isDisplayed()) {
                    console.log(`📷 Found "${opt.label}" option, clicking...`);
                    await button.click();
                    await driver.pause(2000);
                    console.log(`✅ Selected "${opt.label}"`);
                }
            } catch (e) {
                // Permission option not found, continue
            }
        }
    }

    /**
     * Attempts to capture a photo using the WebView capture button
     */
    async capturePhoto(): Promise<boolean> {
        console.log('📸 Looking for photo capture button...');

        try {
            const captureBtn = await byTestId('single-capture-button');
            if (await captureBtn.isDisplayed()) {
                console.log('📸 Found single capture button');
                await captureBtn.click();
                await driver.pause(2000);
                console.log('✅ Photo captured successfully');
                return true;
            }
        } catch (e) {
            console.log('ℹ️ Single capture button not found');
        }

        console.log('❌ No capture button found');
        return false;
    }

    /**
     * Complete camera workflow: open, handle permissions, capture, close
     */
    async performCompletePhotoCapture(): Promise<boolean> {
        try {
            console.log('📸 Starting complete photo capture workflow...');

            await this.openCamera();
            await this.handlePermissionDialogs();
            await driver.pause(3000);

            const photoSuccess = await this.capturePhoto();
            if (!photoSuccess) {
                console.log('❌ Photo capture failed');
                return false;
            }

            await driver.pause(3000);
            await this.closeCamera();
            await driver.pause(3000);

            console.log('🎉 Complete photo capture workflow successful');
            return true;

        } catch (error) {
            console.error('❌ Complete photo capture workflow failed:', error);
            return false;
        }
    }

    /**
     * Handles the "Only this time" location permission if present (native dialog)
     */
    async handleLocationPermissionIfPresent(): Promise<void> {
        await ensureNativeContext();
        try {
            const button = await $('android=new UiSelector().text("Only this time")');
            if (await button.isDisplayed()) {
                console.log('📍 Selecting "Only this time" for location...');
                await button.click();
                await driver.pause(2000);
            }
        } catch (e) {
            console.log('ℹ️ No "Only this time" location permission found');
        }
    }
}
