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

    /**
     * Complete login workflow
     */
    async performCompleteLogin(username: string = 'test', password: string = 'test123'): Promise<boolean> {
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
            // Open menu
            await this.app.openMenu();
            await driver.pause(1000);

            // Navigate to Photos
            const photosLink = await $('android=new UiSelector().text("Photos")');
            await photosLink.waitForDisplayed({timeout: 10000});
            await photosLink.click();
            await driver.pause(2000);
            console.log('📸 Navigated to Photos section');

            // Switch to Import tab
            const importTab = await $('[data-testid="import-tab"]');
            await importTab.waitForDisplayed({timeout: 10000});
            await importTab.click();
            await driver.pause(1000);
            console.log('📂 Switched to Import tab');

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

            // Look for Photos/Images category
            const photosCategory = await $('android=new UiSelector().textContains("Photos")').catch(() => null) ||
                                  await $('android=new UiSelector().textContains("Images")').catch(() => null) ||
                                  await $('android=new UiSelector().textContains("Gallery")').catch(() => null);

            if (photosCategory && await photosCategory.isDisplayed()) {
                await photosCategory.click();
                console.log('📷 Found and clicked Photos/Images category');
                await driver.pause(2000);
            }

            // Find and select first available image
            const imageFiles = await $$('android=new UiSelector().className("android.widget.ImageView")');
            
            if (imageFiles.length > 0) {
                console.log(`📸 Found ${imageFiles.length} image elements`);
                await imageFiles[0].click();
                console.log('📸 Selected first image');
                await driver.pause(1000);
                await this.app.takeScreenshot('image-selected');

                // Click confirmation button
                const selectButtons = ['OK', 'Done', 'Select', 'DONE', 'SELECT'];
                for (const buttonText of selectButtons) {
                    try {
                        const button = await $(`android=new UiSelector().text("${buttonText}")`);
                        if (await button.isDisplayed()) {
                            await button.click();
                            console.log(`✅ Clicked ${buttonText} button`);
                            return true;
                        }
                    } catch (e) {
                        // Continue to next button
                    }
                }

                console.warn('⚠️ Could not find confirmation button');
                return false;
            } else {
                console.warn('⚠️ No image files found in file picker');
                return false;
            }
        } catch (error) {
            console.error('❌ File picker interaction failed:', error.message);
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
     * Complete photo import workflow
     */
    async performPhotoImportWorkflow(): Promise<boolean> {
        console.log('📂 Starting photo import workflow...');
        
        try {
            // Navigate to import section
            const navigationSuccess = await this.navigateToPhotoImport();
            if (!navigationSuccess) {
                console.error('❌ Navigation to import failed');
                return false;
            }

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
    async quickLogin(username: string = 'test', password: string = 'test123'): Promise<boolean> {
        return this.performCompleteLogin(username, password);
    }
}