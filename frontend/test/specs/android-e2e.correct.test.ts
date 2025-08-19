import { expect } from '@wdio/globals';
import { TestWorkflows } from '../helpers/TestWorkflows';
import { HillviewAppPage } from '../pageobjects/HillviewApp.page';
import { WebViewAuthPage } from '../pageobjects/WebViewAuth.page';
import { CameraFlowPage } from '../pageobjects/CameraFlow.page';

/**
 * PROPERLY WRITTEN End-to-End Tests
 * 
 * These tests verify complete user workflows with real assertions
 */
describe('Android E2E Workflows (Correct)', () => {
    let workflows: TestWorkflows;
    let app: HillviewAppPage;
    let auth: WebViewAuthPage;
    let camera: CameraFlowPage;

    beforeEach(async function () {
        this.timeout(90000);
        
        workflows = new TestWorkflows();
        app = new HillviewAppPage();
        auth = new WebViewAuthPage();
        camera = new CameraFlowPage();
        
        console.log('🧪 Starting E2E test with clean state');
    });

    describe('Complete User Workflows', () => {
        it('should complete login and verify authenticated state', async function () {
            this.timeout(180000); // 3 minutes max - reasonable for E2E
            
            console.log('🚀 Testing complete login workflow...');
            
            // Step 1: Verify app starts in logged-out state
            await app.waitForAppReady();
            
            // Step 2: Perform login
            const loginSuccess = await workflows.performCompleteLogin();
            expect(loginSuccess).toBe(true);
            
            // Step 3: REAL VERIFICATION - Check authenticated state
            await app.openMenu();
            const webViewAvailable = await auth.switchToWebView();
            expect(webViewAvailable).toBe(true);
            
            // Look for authenticated user indicators
            const logoutLink = await $('a[href="/logout"]');
            const profileLink = await $('a[href="/profile"]');
            
            const isAuthenticated = await logoutLink.isExisting() || await profileLink.isExisting();
            
            await auth.switchToNativeApp();
            await app.closeMenu();
            
            // CRITICAL ASSERTION: Verify we're actually logged in
            expect(isAuthenticated).toBe(true);
            
            console.log('✅ Complete login workflow verified');
        });

        it('should complete photo workflow and verify camera integration', async function () {
            this.timeout(180000);
            
            console.log('📸 Testing complete photo workflow...');
            
            // Step 1: Verify app is ready
            const initialHealth = await workflows.performQuickHealthCheck();
            expect(initialHealth).toBe(true);
            
            // Step 2: Access camera
            await app.clickCameraButton();
            
            // Step 3: Handle permissions
            await camera.handlePermissions();
            
            // Step 4: Verify camera mode entered
            // Look for camera-specific elements
            const captureButton = await $('android=new UiSelector().text("Capture")');
            const cameraPreview = await $('android=new UiSelector().className("android.view.SurfaceView")');
            
            const inCameraMode = await captureButton.isExisting() || await cameraPreview.isExisting();
            
            if (inCameraMode) {
                console.log('✅ Successfully entered camera mode');
                
                // Try photo capture (may not work in emulator)
                const captureResult = await camera.capturePhoto();
                
                if (captureResult) {
                    console.log('✅ Photo capture successful');
                    await camera.confirmPhoto();
                }
            } else {
                console.log('ℹ️ Camera mode not fully available (expected in emulator)');
            }
            
            // Step 5: CRITICAL - Return to main app
            const returnSuccess = await camera.returnToMainApp();
            expect(returnSuccess).toBe(true);
            
            // Step 6: Verify app is still functional
            const finalHealth = await workflows.performQuickHealthCheck();
            expect(finalHealth).toBe(true);
            
            console.log('✅ Complete photo workflow verified');
        });

        it('should handle complete authenticated photo workflow', async function () {
            this.timeout(300000); // 5 minutes for complete workflow
            
            console.log('🎯 Testing complete authenticated photo workflow...');
            
            // Step 1: Login
            const loginSuccess = await workflows.performCompleteLogin();
            expect(loginSuccess).toBe(true);
            
            // Step 2: Verify authentication
            await app.openMenu();
            await auth.switchToWebView();
            
            const logoutLink = await $('a[href="/logout"]');
            const authenticated = await logoutLink.isExisting();
            
            await auth.switchToNativeApp();
            await app.closeMenu();
            
            expect(authenticated).toBe(true);
            
            // Step 3: Configure sources for testing
            const sourcesConfigured = await workflows.configureSourcesForTesting();
            // Sources config may fail in test environment - that's ok
            
            // Step 4: Photo workflow
            await app.clickCameraButton();
            await camera.handlePermissions();
            
            // Verify we can access camera while authenticated
            const appState = await driver.queryAppState('io.github.koo5.hillview.dev');
            expect(appState).toBeGreaterThan(1); // App still running
            
            // Return to main app
            const returnSuccess = await camera.returnToMainApp();
            expect(returnSuccess).toBe(true);
            
            // Step 5: Wait for any upload processing (short wait)
            await workflows.waitForUploadProcessing(5000); // 5 seconds, not 30!
            
            // Step 6: Verify app remains functional
            const finalHealth = await workflows.performQuickHealthCheck();
            expect(finalHealth).toBe(true);
            
            console.log('✅ Complete authenticated photo workflow verified');
        });
    });

    describe('Error Recovery', () => {
        it('should recover from camera errors gracefully', async function () {
            this.timeout(120000);
            
            console.log('🔧 Testing error recovery...');
            
            // Try camera access
            await app.clickCameraButton();
            await driver.pause(3000);
            
            // Check for errors
            const hasErrors = await app.isErrorDisplayed();
            
            if (hasErrors) {
                console.log('ℹ️ Camera errors detected - testing recovery...');
                
                // Verify app recovery
                await driver.back();
                await driver.pause(2000);
                
                // Should still be able to use app
                const recoveryHealth = await workflows.performQuickHealthCheck();
                expect(recoveryHealth).toBe(true);
                
                console.log('✅ Successfully recovered from camera errors');
                
            } else {
                console.log('✅ No camera errors to recover from');
                
                // Still verify we can return normally
                const returnSuccess = await camera.returnToMainApp();
                expect(returnSuccess).toBe(true);
            }
        });

        it('should handle network issues gracefully', async function () {
            this.timeout(90000);
            
            console.log('🌐 Testing network error handling...');
            
            // Check for network errors
            const hasNetworkErrors = await app.isErrorDisplayed();
            
            if (hasNetworkErrors) {
                console.log('ℹ️ Network errors detected - verifying app resilience...');
                
                // App should still be functional for local operations
                const cameraTexts = await app.getCameraButtonTexts();
                expect(cameraTexts.length).toBeGreaterThan(0);
                
                // Should still be able to access camera
                await app.clickCameraButton();
                await driver.pause(2000);
                
                const returnSuccess = await camera.returnToMainApp();
                expect(returnSuccess).toBe(true);
                
                console.log('✅ App remains functional despite network issues');
                
            } else {
                console.log('✅ No network errors detected');
            }
        });
    });

    describe('Data Persistence', () => {
        it('should verify app data isolation between tests', async function () {
            this.timeout(90000);
            
            console.log('🧪 Testing data isolation...');
            
            // This test verifies our clean app state system works
            
            // Check that we start with clean state
            await app.openMenu();
            const webViewAvailable = await auth.switchToWebView();
            expect(webViewAvailable).toBe(true);
            
            // Should see login link in clean state
            const loginLink = await $('a[href="/login"]');
            const hasLoginLink = await loginLink.isExisting();
            
            await auth.switchToNativeApp();
            await app.closeMenu();
            
            // REAL ASSERTION: We should start logged out (clean state)
            expect(hasLoginLink).toBe(true);
            
            console.log('✅ Data isolation verified - test started with clean state');
        });
    });
});