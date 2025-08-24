import { $ } from '@wdio/globals';

/**
 * Comprehensive helper for camera workflow operations
 * Consolidates patterns from android-photo-capture.test.ts and other successful tests
 */
export class CameraWorkflowHelper {
    /**
     * Opens camera mode by finding and clicking the camera button
     * Handles WebView context switching automatically
     */
    async openCamera(): Promise<void> {
        console.log('📸 Looking for camera button...');
        
        // Switch to WebView context first since this is an HTML button
        const contexts = await driver.getContexts();
        const webViewContexts = contexts.filter(ctx => ctx.includes('WEBVIEW'));
        
        if (webViewContexts.length > 0) {
            await driver.switchContext(webViewContexts[0]);
            
            // Just find the camera button and click it - keep it simple
            const cameraButton = await $('[data-testid="camera-button"]');
            await cameraButton.click();
            console.log('✅ Clicked camera button');
            
            await driver.switchContext('NATIVE_APP');
        } else {
            throw new Error('No WebView context found');
        }
        
        await driver.pause(2000);
        console.log('📸 Opened camera mode');
    }

    /**
     * Closes camera mode by clicking the camera button again
     * Handles WebView context switching automatically
     */
    async closeCamera(): Promise<void> {
        console.log('📸 Looking for close camera button...');
        
        // Switch to WebView context first since this is an HTML button
        const contexts = await driver.getContexts();
        const webViewContexts = contexts.filter(ctx => ctx.includes('WEBVIEW'));
        
        if (webViewContexts.length > 0) {
            await driver.switchContext(webViewContexts[0]);
            
            // Just find the camera button and click it again - keep it simple
            const cameraButton = await $('[data-testid="camera-button"]');
            await cameraButton.click();
            console.log('✅ Clicked camera button to close');
            
            await driver.switchContext('NATIVE_APP');
        } else {
            throw new Error('No WebView context found');
        }
        
        await driver.pause(2000);
        console.log('📸 Closed camera mode');
    }

    /**
     * Handles camera initialization buttons like "Try Again" and "Enable Camera"
     * Also handles any permission dialogs that may appear after clicking these buttons
     */
    async handleCameraInitializationButtons(): Promise<void> {
        console.log('🔄 Handling camera initialization buttons...');
        
        let buttonClicked = false;
        
        // Check for "Try Again" button first
        try {
            const tryAgainButton = await $('android=new UiSelector().text("Try Again")');
            if (await tryAgainButton.isDisplayed()) {
                console.log('🔄 Found "Try Again" button, clicking...');
                await tryAgainButton.click();
                await driver.pause(3000);
                console.log('✅ Clicked Try Again button');
                buttonClicked = true;
            }
        } catch (e) {
            console.log('ℹ️ No "Try Again" button found');
        }
        
        // Check for "Enable Camera" button
        try {
            const enableCameraButton = await $('android=new UiSelector().text("Enable Camera")');
            if (await enableCameraButton.isDisplayed()) {
                console.log('📷 Found "Enable Camera" button, clicking...');
                await enableCameraButton.click();
                await driver.pause(3000);
                console.log('✅ Clicked Enable Camera button');
                buttonClicked = true;
            }
        } catch (e) {
            console.log('ℹ️ No "Enable Camera" button found');
        }
        
        // If we clicked any initialization button, check for permission dialogs
        if (buttonClicked) {
            console.log('📋 Checking for permission dialogs after button click...');
            await this.handlePermissionDialogs();
        }
        
        // Additional wait for camera to initialize after button clicks
        await driver.pause(2000);
    }

    /**
     * Handles permission dialogs that may appear after camera initialization
     */
    async handlePermissionDialogs(): Promise<void> {
        console.log('📋 Handling potential permission dialogs...');
        
        // Handle camera permission dialog
        try {
            const allowButton = await $('android=new UiSelector().text("Allow")');
            if (await allowButton.isDisplayed()) {
                console.log('📷 Found camera permission dialog, clicking Allow...');
                await allowButton.click();
                await driver.pause(2000);
                console.log('✅ Granted camera permission');
            }
        } catch (e) {
            console.log('ℹ️ No "Allow" button found');
        }
        
        // Handle "While using the app" option
        try {
            const whileUsingButton = await $('android=new UiSelector().text("While using the app")');
            if (await whileUsingButton.isDisplayed()) {
                console.log('📷 Found "While using the app" option, clicking...');
                await whileUsingButton.click();
                await driver.pause(2000);
                console.log('✅ Selected "While using the app"');
            }
        } catch (e) {
            console.log('ℹ️ No "While using the app" option found');
        }
        
        // Handle "Only this time" option
        try {
            const onlyThisTimeButton = await $('android=new UiSelector().text("Only this time")');
            if (await onlyThisTimeButton.isDisplayed()) {
                console.log('📍 Found "Only this time" option, clicking...');
                await onlyThisTimeButton.click();
                await driver.pause(2000);
                console.log('✅ Selected "Only this time"');
            }
        } catch (e) {
            console.log('ℹ️ No "Only this time" option found');
        }
    }

    /**
     * Attempts to capture a photo using various capture button strategies
     * Returns true if photo was successfully captured, false otherwise
     */
    async capturePhoto(): Promise<boolean> {
        console.log('📸 Looking for photo capture button...');

        const captureButtons = [
            'android=new UiSelector().text("SINGLE")',
            'android=new UiSelector().text("Capture")',
            'android=new UiSelector().text("Take Photo")',
            'android=new UiSelector().description("Take picture")',
        ];

        for (const selector of captureButtons) {
            try {
                const captureButton = await $(selector);
                if (await captureButton.isDisplayed()) {
                    console.log(`📸 Found capture button: ${selector}`);
                    await captureButton.click();
                    await driver.pause(2000);
                    console.log('✅ Photo captured successfully');
                    return true;
                }
            } catch (e) {
                console.log(`ℹ️ Capture button not found: ${selector}`);
            }
        }

        console.log('❌ No capture button found');
        return false;
    }

    /**
     * Complete camera workflow: open, initialize, capture, close
     * This is the main entry point for most camera tests
     */
    async performCompletePhotoCapture(): Promise<boolean> {
        try {
            console.log('📸 Starting complete photo capture workflow...');
            
            // Step 1: Open camera
            await this.openCamera();
            
            // Step 2: Handle initialization buttons and permissions
            await this.handleCameraInitializationButtons();
            
            // Step 3: Wait for camera to be ready and take screenshot
            await driver.pause(3000);
            
            // Step 4: Capture photo
            const photoSuccess = await this.capturePhoto();
            if (!photoSuccess) {
                console.log('❌ Photo capture failed');
                return false;
            }
            
            // Step 5: Wait for photo processing
            await driver.pause(3000);
            
            // Step 6: Close camera
            await this.closeCamera();
            
            // Step 7: Wait for UI to stabilize
            await driver.pause(3000);
            
            console.log('🎉 Complete photo capture workflow successful');
            return true;
            
        } catch (error) {
            console.error('❌ Complete photo capture workflow failed:', error);
            return false;
        }
    }

    /**
     * Handles the common "Only this time" location permission that appears
     * This is often needed after camera operations
     */
    async handleLocationPermissionIfPresent(): Promise<void> {
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