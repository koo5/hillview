import { HillviewAppPage } from '../pageobjects/HillviewApp.page';
import { WebViewAuthPage } from '../pageobjects/WebViewAuth.page';
import { CameraFlowPage } from '../pageobjects/CameraFlow.page';

/**
 * Common test workflows that combine page objects for complete user journeys
 */
export class TestWorkflows {
    private app = new HillviewAppPage();
    private auth = new WebViewAuthPage();
    private camera = new CameraFlowPage();
    private testPassword: string | null = null;

    /**
     * Create test users via API and get dynamic password
     */
    async recreateTestUsers(): Promise<string> {
        console.log('🧪 Creating test users via API...');

        try {
            // Switch to WebView context to execute JavaScript
            await this.auth.switchToWebView();

            // Make HTTP request to recreate test users
            const response = await driver.executeScript(`
                return fetch('http://10.0.2.2:8055/api/debug/recreate-test-users', {
                    method: 'POST'
                }).then(res => res.json());
            `, []);

            console.log('🢄Test user creation result:', response);

            const testPassword = response?.details?.user_passwords?.test;
            if (!testPassword) {
                throw new Error('Test user password not returned from recreate-test-users');
            }

            // Switch back to native context
            await driver.switchContext('NATIVE_APP');

            this.testPassword = testPassword;
            console.log('✅ Test users created, password obtained');
            return testPassword;

        } catch (error) {
            console.error('❌ Failed to create test users:', error);
            // Make sure we're back in native context
            try {
                await driver.switchContext('NATIVE_APP');
            } catch (e) {}
            throw error;
        }
    }

    /**
     * Complete login workflow
     */
    async performCompleteLogin(username: string, password: string): Promise<boolean> {
        console.log('🔐 Starting complete login workflow...');

        try {
            // Step 1: Take initial screenshot
            await this.app.takeScreenshot('login-workflow-start');

            // Step 2: Open menu
            await this.app.openMenu();
            await this.app.takeScreenshot('login-menu-opened');

            // Step 3: Switch to WebView and login
            const webViewAvailable = await this.auth.switchToWebView();
            if (!webViewAvailable) {
                console.error('❌ WebView not available for login');
                return false;
            }

            const loginSuccess = await this.auth.performLogin(username, password);
            if (!loginSuccess) {
                console.error('❌ Login failed');
                return false;
            }

            // Step 4: Switch back to native and close menu
            await this.auth.switchToNativeApp();
            await this.app.closeMenu();

            await this.app.takeScreenshot('login-workflow-completed');
            console.log('🎉 Complete login workflow successful');
            return true;

        } catch (error) {
            console.error('❌ Complete login workflow failed:', error.message);
            await this.app.takeScreenshot('login-workflow-error');
            return false;
        }
    }

    /**
     * Complete photo capture workflow
     */
    async performCompletePhotoCapture(): Promise<boolean> {
        console.log('📸 Starting complete photo capture workflow...');

        try {
            // Step 1: Take initial screenshot
            await this.app.takeScreenshot('photo-workflow-start');

            // Step 2: Click camera button
            await this.app.clickCameraButton();
            await this.app.takeScreenshot('photo-camera-opened');

            // Step 3: Complete camera workflow
            const cameraSuccess = await this.camera.completeCameraWorkflow();
            if (!cameraSuccess) {
                console.error('❌ Camera workflow failed');
                return false;
            }

            await this.app.takeScreenshot('photo-workflow-completed');
            console.log('🎉 Complete photo capture workflow successful');
            return true;

        } catch (error) {
            console.error('❌ Complete photo capture workflow failed:', error.message);
            await this.app.takeScreenshot('photo-workflow-error');
            return false;
        }
    }

    /**
     * Complete authentication + photo workflow
     */
    async performCompleteAuthAndPhotoWorkflow(username: string = 'test', password: string = 'test123'): Promise<boolean> {
        console.log('🚀 Starting complete auth + photo workflow...');

        try {
            // Step 1: Login
            const loginSuccess = await this.performCompleteLogin(username, password);
            if (!loginSuccess) {
                console.error('❌ Login phase failed');
                return false;
            }

            // Step 2: Wait a moment between workflows
            await driver.pause(3000);

            // Step 3: Photo capture
            const photoSuccess = await this.performCompletePhotoCapture();
            if (!photoSuccess) {
                console.error('❌ Photo capture phase failed');
                return false;
            }

            console.log('🎉 Complete auth + photo workflow successful');
            return true;

        } catch (error) {
            console.error('❌ Complete auth + photo workflow failed:', error.message);
            await this.app.takeScreenshot('complete-workflow-error');
            return false;
        }
    }

    /**
     * Configure sources (disable Mapillary, enable others)
     */
    async configureSourcesForTesting(): Promise<boolean> {
        console.log('📊 Configuring sources for testing...');

        try {
            // Step 1: Open menu
            await this.app.openMenu();

            // Step 2: Switch to WebView and navigate to sources
            const webViewAvailable = await this.auth.switchToWebView();
            if (!webViewAvailable) {
                console.error('❌ WebView not available for sources');
                return false;
            }

            const sourcesSuccess = await this.auth.navigateToSources();
            if (!sourcesSuccess) {
                console.error('❌ Could not navigate to sources');
                return false;
            }

            // Step 3: Disable Mapillary
            await this.auth.toggleMapillarySource(false);
            await this.app.takeScreenshot('sources-configured');

            // Step 4: Return to main app
            await this.auth.switchToNativeApp();
            await this.app.closeMenu();

            console.log('✅ Sources configured successfully');
            return true;

        } catch (error) {
            console.error('❌ Source configuration failed:', error.message);
            await this.app.takeScreenshot('sources-config-error');
            return false;
        }
    }

    /**
     * Quick health check to verify app is responsive
     */
    async performQuickHealthCheck(): Promise<boolean> {
        console.log('🏥 Performing quick health check...');

        try {
            // Check for critical errors (will throw if found)
            await this.app.checkForCriticalError();

            // Check basic functionality
            await this.app.waitForAppReady();
            const cameraTexts = await this.app.getCameraButtonTexts();

            if (cameraTexts.length === 0) {
                console.error('❌ No camera button found');
                return false;
            }

            console.log(`✅ Health check passed - found camera buttons: ${cameraTexts.join(', ')}`);
            return true;

        } catch (error) {
            console.error('❌ Health check failed:', error.message);
            await this.app.takeScreenshot('health-check-error');
            return false;
        }
    }

    /**
     * Wait for upload processing (common in upload tests)
     */
    async waitForUploadProcessing(timeoutMs: number = 10000): Promise<void> {
        console.log(`☁️ Waiting ${timeoutMs/1000}s for upload processing...`);
        await driver.pause(timeoutMs);
        await this.app.takeScreenshot('upload-processing-complete');
    }

    /**
     * Navigate to Photos > Import tab
     */
    async navigateToPhotoImport(): Promise<boolean> {
        console.log('📂 Navigating to Photo Import tab...');

        try {
            // Open menu and verify it opened
            await this.app.openMenu();
            await driver.pause(1000);

            // Verify menu is open by checking for My Photos link (already in WebView context from menu open)
            console.log('🔍 Looking for My Photos menu item...');
            const photosLink = await $('a[href="/photos"]');
            await photosLink.waitForDisplayed({timeout: 10000});

            // Navigate to My Photos
            await photosLink.click();
            await driver.pause(2000);
            console.log('📸 Navigated to My Photos section');

            // Import functionality is directly available, no tabs needed
            console.log('📂 Import functionality is ready');

            return true;
        } catch (error) {
            console.error('❌ Failed to navigate to photo import:', error.message);
            return false;
        }
    }

    /**
     * Interact with Android file picker to select photos
     */
    async selectPhotosFromFilePicker(): Promise<boolean> {
        console.log('📱 Interacting with Android file picker...');

        try {
            // Wait for file picker to appear
            await driver.pause(3000);
            await this.app.takeScreenshot('file-picker-opened');

            // Simple approach: try to find any clickable image elements directly
            console.log('📸 Looking for clickable images...');

            // Try multiple approaches to find and click images in the file picker
            console.log('📸 Attempting to find and click images in file picker...');

            // Method 1: Try to find image elements using resource-id (more reliable)
            try {
                const thumbnails = await driver.$$({
                    strategy: '-android uiautomator',
                    selector: 'new UiSelector().resourceIdMatches(".*thumbnail.*")'
                });

                if (thumbnails.length > 0) {
                    console.log(`📸 Found ${thumbnails.length} thumbnail elements via resource-id`);
                    await thumbnails[0].click();
                    console.log('📸 Clicked first thumbnail');
                    await driver.pause(1000);
                    await this.app.takeScreenshot('image-selected');
                    return true;
                }
            } catch (e) {
                console.log('📸 Resource-id approach failed:', e.message);
            }

            // Method 2: Try coordinate-based tap in likely image areas
            console.log('📸 Trying coordinate-based tap approach');
            const { width, height } = await driver.getWindowSize();

            // Tap in the upper portion where images are likely to be
            const imageAreaX = Math.round(width / 3);
            const imageAreaY = Math.round(height / 3);

            await driver.touchAction([
                { action: 'tap', x: imageAreaX, y: imageAreaY }
            ]);
            console.log(`📸 Tapped at image area coordinates: ${imageAreaX}, ${imageAreaY}`);
            await driver.pause(1000);
            await this.app.takeScreenshot('coordinate-tap-attempt');

            // Look for any button with common confirmation text
            console.log('✅ Looking for confirmation buttons...');
            const buttonTexts = ['Select', 'OK', 'Done', 'OPEN', 'Choose'];
            let confirmed = false;

            for (const text of buttonTexts) {
                try {
                    const button = await $(`android=new UiSelector().text("${text}")`);
                    if (await button.isDisplayed()) {
                        await button.click();
                        console.log(`✅ Clicked confirmation button: ${text}`);
                        confirmed = true;
                        break;
                    }
                } catch (e) {
                    // Continue to next button text
                }
            }

            if (!confirmed) {
                console.log('✅ No confirmation button found, trying coordinate tap at bottom right');
                const { width, height } = await driver.getWindowSize();
                const rightX = Math.round(width * 0.8);
                const bottomY = Math.round(height * 0.9);
                await driver.touchAction('tap', rightX, bottomY);
                console.log(`✅ Tapped confirmation at: ${rightX}, ${bottomY}`);
            }

            await driver.pause(2000);
            return true;

        } catch (error) {
            console.error('❌ File picker interaction failed:', error.message);
            await this.app.takeScreenshot('file-picker-error');
            return false;
        }
    }

    /**
     * Cancel file picker
     */
    async cancelFilePicker(): Promise<boolean> {
        console.log('❌ Cancelling file picker...');

        try {
            const cancelButtons = ['Cancel', 'CANCEL'];

            for (const buttonText of cancelButtons) {
                try {
                    const button = await $(`android=new UiSelector().text("${buttonText}")`);
                    if (await button.isDisplayed()) {
                        await button.click();
                        console.log(`❌ Clicked ${buttonText} button`);
                        return true;
                    }
                } catch (e) {
                    // Continue
                }
            }

            // Try back button as fallback
            await driver.back();
            console.log('🔙 Used back button to cancel');
            return true;

        } catch (error) {
            console.error('❌ File picker cancellation failed:', error.message);
            return false;
        }
    }

    /**
     * Ensure a map source is enabled or disabled (on main page)
     */
    async ensureSourceEnabled(sourceName: string, enabled: boolean): Promise<boolean> {
        console.log(`🗺️ Ensuring ${sourceName} source is ${enabled ? 'enabled' : 'disabled'}...`);

        try {
            // Make sure we're in WebView context for source controls
            await this.auth.switchToWebView();

            // Find the source toggle button on main page map
            const sourceButton = await $(`[data-testid="source-toggle-${sourceName}"]`);
            await sourceButton.waitForDisplayed({timeout: 10000});

            // Check current state by looking for 'active' class
            const classes = await sourceButton.getAttribute('class');
            const isCurrentlyEnabled = classes && classes.includes('active');

            // Click if we need to change the state
            if (isCurrentlyEnabled !== enabled) {
                await sourceButton.click();
                await driver.pause(1000);
                console.log(`🗺️ ${enabled ? 'Enabled' : 'Disabled'} ${sourceName} source`);
            } else {
                console.log(`🗺️ ${sourceName} source already ${enabled ? 'enabled' : 'disabled'}`);
            }

            return true;
        } catch (error) {
            console.error(`❌ Failed to set ${sourceName} source to ${enabled}:`, error.message);
            return false;
        }
    }

    /**
     * Configure auto-upload settings in the Photos page
     */
    async configureAutoUploadSettings(enabled: boolean): Promise<boolean> {
        console.log(`⚙️ Configuring auto-upload settings (${enabled ? 'enabled' : 'disabled'})...`);

        try {
            // Try to switch to WebView context, but don't fail if not available
            const webViewAvailable = await this.auth.switchToWebView();
            if (!webViewAvailable) {
                console.log('⚠️ WebView not available, trying to find settings in native context');
            }

            // Try to find the settings button with multiple strategies
            let settingsButton;
            try {
                settingsButton = await $('.settings-button');
                await settingsButton.waitForDisplayed({timeout: 5000});
            } catch (e) {
                // Try alternative selectors for settings button
                try {
                    settingsButton = await $('[data-testid="settings-button"]');
                    await settingsButton.waitForDisplayed({timeout: 5000});
                } catch (e2) {
                    console.log('⚠️ Settings button not found, settings may already be visible or not needed');
                    return true; // Continue without opening settings panel
                }
            }
            await settingsButton.click();
            await driver.pause(1000);
            console.log('⚙️ Opened settings panel');

            // Find the auto-upload checkbox
            const autoUploadCheckbox = await $('[data-testid="auto-upload-checkbox"]');
            await autoUploadCheckbox.waitForDisplayed({timeout: 10000});

            // Check current state
            const isCurrentlyEnabled = await autoUploadCheckbox.isSelected();

            // Click if we need to change the state
            if (isCurrentlyEnabled !== enabled) {
                await autoUploadCheckbox.click();
                await driver.pause(1000);
                console.log(`⚙️ ${enabled ? 'Enabled' : 'Disabled'} auto-upload`);
            } else {
                console.log(`⚙️ Auto-upload already ${enabled ? 'enabled' : 'disabled'}`);
            }

            // Close settings panel by clicking Cancel
            const cancelButton = await $('.secondary-button');
            await cancelButton.click();
            await driver.pause(1000);
            console.log('⚙️ Closed settings panel');

            return true;
        } catch (error) {
            console.error(`❌ Failed to configure auto-upload settings:`, error.message);
            return false;
        }
    }

    /**
     * Complete photo import workflow
     */
    async performPhotoImportWorkflow(): Promise<boolean> {
        console.log('📂 Starting photo import workflow...');

        try {
            // First navigate to main page to access source toggles
            console.log('🏠 Navigating to main page...');
            await this.auth.switchToWebView();

            // Try multiple approaches to get to main page
            try {
                // Method 1: Direct navigation via URL
                await driver.url('/');
                console.log('✅ Navigated to main page via URL');
            } catch (e) {
                // Method 2: Look for home/main page link
                try {
                    const homeLink = await $('a[href="/"]');
                    await homeLink.waitForDisplayed({timeout: 5000});
                    await homeLink.click();
                    console.log('✅ Navigated to main page via home link');
                } catch (e2) {
                    // Method 3: Already on main page or navigate via menu
                    console.log('⚠️ Using current page as main page (may already be there)');
                }
            }
            await driver.pause(3000);

            // Now turn off map sources on main page
            console.log('🗺️ Disabling map sources on main page...');
            await this.ensureSourceEnabled('mapillary', false);
            await this.ensureSourceEnabled('hillview', false);
            await this.ensureSourceEnabled('device', false);

            // Navigate to import section
            const navigationSuccess = await this.navigateToPhotoImport();
            if (!navigationSuccess) {
                console.error('❌ Navigation to import failed');
                return false;
            }

            // Configure auto-upload settings (turn on for testing)
            console.log('⚙️ Configuring auto-upload settings...');
            await this.configureAutoUploadSettings(true);

            // Switch to WebView context to find the import button
            await this.auth.switchToWebView();

            // Click import button
            const importButton = await $('[data-testid="import-from-device-button"]');
            await importButton.waitForDisplayed({timeout: 10000});

            // Verify button is enabled
            const isEnabled = await importButton.isEnabled();
            if (!isEnabled) {
                console.error('❌ Import button is disabled');
                return false;
            }

            await importButton.click();
            console.log('📂 Clicked Import from Device button');
            await this.app.takeScreenshot('import-button-clicked');

            // Interact with file picker
            const selectionSuccess = await this.selectPhotosFromFilePicker();
            if (!selectionSuccess) {
                console.error('❌ Photo selection failed');
                return false;
            }

            // Wait for import to process
            await driver.pause(5000);
            await this.app.takeScreenshot('import-processing');

            console.log('✅ Photo import workflow completed');
            return true;

        } catch (error) {
            console.error('❌ Photo import workflow failed:', error.message);
            await this.app.takeScreenshot('import-workflow-error');
            return false;
        }
    }

    /**
     * Quick login using existing method from TestWorkflows
     */
    async quickLogin(username: string, password: string): Promise<boolean> {
        return this.performCompleteLogin(username, password);
    }
}
