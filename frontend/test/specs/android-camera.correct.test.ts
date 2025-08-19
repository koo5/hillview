import { expect } from '@wdio/globals';
import { TestWorkflows } from '../helpers/TestWorkflows';
import { HillviewAppPage } from '../pageobjects/HillviewApp.page';
import { CameraFlowPage } from '../pageobjects/CameraFlow.page';

/**
 * PROPERLY WRITTEN Android Camera Tests
 * 
 * These tests actually verify camera functionality instead of just taking screenshots
 */
describe('Android Camera (Correct)', () => {
    let workflows: TestWorkflows;
    let app: HillviewAppPage;
    let camera: CameraFlowPage;

    beforeEach(async function () {
        this.timeout(60000);
        
        workflows = new TestWorkflows();
        app = new HillviewAppPage();
        camera = new CameraFlowPage();
        
        console.log('🧪 Starting camera test with clean state');
    });

    describe('Camera Access', () => {
        it('should successfully access camera and enter camera mode', async function () {
            this.timeout(90000);
            
            console.log('📸 Testing camera access...');
            
            // Verify app is ready
            await app.waitForAppReady();
            
            // Verify camera button exists and is functional
            const cameraTexts = await app.getCameraButtonTexts();
            expect(cameraTexts.length).toBeGreaterThan(0);
            
            console.log(`📸 Found camera button(s): ${cameraTexts.join(', ')}`);
            
            // Click camera button
            await app.clickCameraButton();
            
            // Wait for camera mode to load
            await driver.pause(3000);
            
            // REAL VERIFICATION: Check if we're actually in camera mode
            // Look for camera-specific UI elements
            const captureButton = await $('android=new UiSelector().text("Capture")');
            const shutterButton = await $('android=new UiSelector().resourceId("*shutter*")');
            const cameraPreview = await $('android=new UiSelector().className("android.view.SurfaceView")');
            
            const inCameraMode = await captureButton.isExisting() || 
                                await shutterButton.isExisting() || 
                                await cameraPreview.isExisting();
            
            // Verify we successfully entered some kind of camera interface
            expect(inCameraMode).toBe(true);
            
            console.log('✅ Successfully entered camera mode');
            
            // Return to main app for cleanup
            await camera.returnToMainApp();
        });

        it('should handle camera permissions properly', async function () {
            this.timeout(90000);
            
            console.log('📋 Testing camera permission handling...');
            
            // Access camera to trigger permissions
            await app.clickCameraButton();
            
            // Handle permissions - this should not throw errors
            await camera.handlePermissions();
            
            // Wait a moment for permissions to be processed
            await driver.pause(2000);
            
            // REAL VERIFICATION: Check that permissions were handled without crashes
            // Verify app is still responsive
            const currentActivity = await driver.getCurrentActivity();
            expect(currentActivity).toContain('MainActivity');
            
            // Verify we didn't crash or get stuck
            const appState = await driver.queryAppState('io.github.koo5.hillview.dev');
            expect(appState).toBeGreaterThan(1); // App should still be running
            
            console.log('✅ Camera permissions handled successfully');
            
            // Return to main app
            await camera.returnToMainApp();
        });
    });

    describe('Photo Capture Workflow', () => {
        it('should complete camera workflow steps without errors', async function () {
            this.timeout(120000);
            
            console.log('📸 Testing complete camera workflow...');
            
            // Start camera workflow
            await app.clickCameraButton();
            
            // Handle permissions
            await camera.handlePermissions();
            
            // Try to capture photo (may not work in emulator, but shouldn't crash)
            const captureResult = await camera.capturePhoto();
            
            // REAL VERIFICATION: Check that capture attempt didn't crash the app
            const appState = await driver.queryAppState('io.github.koo5.hillview.dev');
            expect(appState).toBeGreaterThan(1);
            
            if (captureResult) {
                console.log('✅ Photo capture successful');
                
                // Try confirmation
                const confirmResult = await camera.confirmPhoto();
                expect(confirmResult).toBe(true);
                
            } else {
                console.log('ℹ️ Photo capture not available (expected in emulator)');
                // This is fine - emulators often can't capture photos
            }
            
            // CRITICAL: Verify we can return to main app
            const returnSuccess = await camera.returnToMainApp();
            expect(returnSuccess).toBe(true);
            
            // Verify we're back in main app
            const hamburgerMenu = await $('android=new UiSelector().text("Toggle menu")');
            const backInMainApp = await hamburgerMenu.isExisting();
            expect(backInMainApp).toBe(true);
            
            console.log('✅ Camera workflow completed and returned to main app');
        });
    });

    describe('Camera Error Handling', () => {
        it('should handle camera unavailable gracefully', async function () {
            this.timeout(60000);
            
            console.log('🔍 Testing camera error handling...');
            
            // Try camera access
            await app.clickCameraButton();
            await driver.pause(3000);
            
            // Check for camera-related errors
            const hasErrors = await app.isErrorDisplayed();
            
            if (hasErrors) {
                console.log('ℹ️ Camera errors detected (expected in some emulators)');
                
                // REAL VERIFICATION: App should still be functional despite camera issues
                const currentActivity = await driver.getCurrentActivity();
                expect(currentActivity).toContain('MainActivity');
                
                // Should be able to return to main app
                await driver.back();
                await driver.pause(2000);
                
                const hamburgerMenu = await $('android=new UiSelector().text("Toggle menu")');
                const canAccessMenu = await hamburgerMenu.isExisting();
                expect(canAccessMenu).toBe(true);
                
                console.log('✅ App remains functional despite camera issues');
                
            } else {
                console.log('✅ No camera errors detected');
                
                // Clean return to main app
                await camera.returnToMainApp();
            }
        });

        it('should not get stuck in camera mode', async function () {
            this.timeout(90000);
            
            console.log('🔄 Testing camera mode exit...');
            
            // Enter camera mode
            await app.clickCameraButton();
            await driver.pause(3000);
            
            // Try to exit camera mode multiple ways
            const returnSuccess = await camera.returnToMainApp(3);
            
            // REAL VERIFICATION: We should be able to exit camera mode
            expect(returnSuccess).toBe(true);
            
            // Double-check we're actually back
            const hamburgerMenu = await $('android=new UiSelector().text("Toggle menu")');
            const backInMainApp = await hamburgerMenu.isDisplayed();
            expect(backInMainApp).toBe(true);
            
            console.log('✅ Successfully exited camera mode');
        });
    });

    describe('Camera Integration', () => {
        it('should maintain app state after camera usage', async function () {
            this.timeout(120000);
            
            console.log('🔄 Testing app state after camera usage...');
            
            // Check initial app health
            const initialHealth = await workflows.performQuickHealthCheck();
            expect(initialHealth).toBe(true);
            
            // Use camera
            await app.clickCameraButton();
            await camera.handlePermissions();
            await camera.returnToMainApp();
            
            // REAL VERIFICATION: App should still be healthy after camera usage
            const finalHealth = await workflows.performQuickHealthCheck();
            expect(finalHealth).toBe(true);
            
            // Verify specific functionality still works
            const cameraTexts = await app.getCameraButtonTexts();
            expect(cameraTexts.length).toBeGreaterThan(0);
            
            console.log('✅ App state maintained after camera usage');
        });
    });
});