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
}