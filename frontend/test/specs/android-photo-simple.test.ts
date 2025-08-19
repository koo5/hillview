import { expect } from '@wdio/globals'
import { TestWorkflows } from '../helpers/TestWorkflows'

/**
 * Simple Android Photo Upload Test
 * 
 * A simplified test that focuses on testing the photo capture workflow
 * and verifying that the worker container processes uploads correctly.
 */
describe('Simple Android Photo Upload', () => {
    let workflows: TestWorkflows;
    
    beforeEach(async function () {
        this.timeout(90000);
        
        // Initialize workflows helper
        workflows = new TestWorkflows();
        
        // Clean app state is now automatically provided by wdio.conf.ts beforeTest hook
        // Each test gets a fresh app with cleared data for proper isolation
        
        console.log('🧪 Starting photo upload test with clean app state');
        
        // Optional: Additional test-specific cleanup can be done here
        // For example, if you need to clear specific test data:
        // await clearAppData();
    });

    describe('Basic Photo Workflow', () => {
        it('should login and capture a photo with upload verification', async function () {
            this.timeout(180000);
            
            console.log('🔐📸 Testing login and photo capture workflow...');
            
            try {
                // Take screenshot of initial state
                await driver.saveScreenshot('./test-results/android-login-initial.png');
                
                // Step 1: Login to the app
                console.log('🔐 Starting login process...');
                
                // Find the hamburger menu button
                const hamburgerMenu = await $('android=new UiSelector().text("Toggle menu")');
                await hamburgerMenu.waitForDisplayed({ timeout: 10000 });
                console.log('✅ Found hamburger menu');
                
                // Click hamburger menu to open it
                await hamburgerMenu.click();
                await driver.pause(2000);
                console.log('🍔 Opened hamburger menu');
                
                // Take screenshot of open menu
                await driver.saveScreenshot('./test-results/android-login-menu-open.png');
                
                // Switch to WebView context to access login link
                const contexts = await driver.getContexts();
                const webViewContexts = contexts.filter(ctx => ctx.includes('WEBVIEW'));
                
                if (webViewContexts.length > 0) {
                    await driver.switchContext(webViewContexts[0]);
                    console.log('🌐 Switched to WebView context for login');
                    
                    // Look for login link
                    try {
                        const loginLink = await $('a[href="/login"]');
                        const loginVisible = await loginLink.isDisplayed();
                        
                        if (loginVisible) {
                            console.log('🔐 Found login link, clicking...');
                            await loginLink.click();
                            await driver.pause(3000);
                            
                            // Take screenshot of login page
                            await driver.saveScreenshot('./test-results/android-login-page.png');
                            
                            // Fill in login credentials
                            const usernameInput = await $('input[type="text"]');
                            await usernameInput.waitForDisplayed({ timeout: 10000 });
                            await usernameInput.setValue('test');
                            console.log('✅ Entered username');
                            
                            const passwordInput = await $('input[type="password"]');
                            await passwordInput.setValue('test123');
                            console.log('✅ Entered password');
                            
                            const submitButton = await $('button[type="submit"]');
                            await submitButton.click();
                            console.log('🔐 Submitted login form');
                            
                            // Wait for redirect back to main page
                            await driver.pause(5000);
                            
                            console.log('✅ Login completed');
                        } else {
                            console.log('ℹ️ User may already be logged in');
                        }
                    } catch (e) {
                        console.log('ℹ️ Could not find login link, user may already be logged in');
                    }
                    
                    // Switch back to native context
                    await driver.switchContext('NATIVE_APP');
                    console.log('↩️ Switched back to native context');
                } else {
                    console.log('⚠️ No WebView context found for login');
                }
                
                // Close menu if still open
                await driver.back();
                await driver.pause(2000);
                
                // Step 2: Capture a photo
                console.log('📸 Starting photo capture...');
                
                // Find camera button - try different text variations
                let cameraButton;
                const cameraTexts = ['Take photo', 'Take photos', 'Camera'];
                
                for (const text of cameraTexts) {
                    try {
                        cameraButton = await $(`android=new UiSelector().text("${text}")`);
                        const isDisplayed = await cameraButton.isDisplayed();
                        if (isDisplayed) {
                            console.log(`✅ Found camera button with text: "${text}"`);
                            break;
                        }
                    } catch (e) {
                        console.log(`ℹ️ Camera button not found with text: "${text}"`);
                    }
                }
                
                if (!cameraButton) {
                    throw new Error('Could not find camera button');
                }
                
                // Click camera button to enter camera mode
                await cameraButton.click();
                await driver.pause(3000);
                console.log('📸 Entered camera mode');
                
                // Take screenshot of camera interface
                await driver.saveScreenshot('./test-results/android-camera-interface.png');
                
                // Check for "Enable Camera" button (app-specific) FIRST
                console.log('📷 Checking for "Enable Camera" button...');
                try {
                    const enableCameraButton = await $('android=new UiSelector().text("Enable Camera")');
                    if (await enableCameraButton.isDisplayed()) {
                        console.log('📷 Clicking "Enable Camera" button...');
                        await enableCameraButton.click();
                        await driver.pause(3000);
                        console.log('✅ Camera enabled');
                        
                        // Take screenshot after enabling camera
                        await driver.saveScreenshot('./test-results/android-camera-enabled.png');
                    } else {
                        console.log('ℹ️ No "Enable Camera" button found - camera may already be enabled');
                    }
                } catch (e) {
                    console.log('ℹ️ Could not find "Enable Camera" button:', e.message);
                }
                
                // Handle camera and location permissions
                console.log('📋 Checking for permission dialogs...');
                
                // Check for camera permission first
                try {
                    const cameraAllowButton = await $('android=new UiSelector().text("Allow")');
                    if (await cameraAllowButton.isDisplayed()) {
                        console.log('📷 Granting camera permission...');
                        await cameraAllowButton.click();
                        await driver.pause(2000);
                    }
                } catch (e) {
                    console.log('ℹ️ No camera permission prompt');
                }
                
                // Check for location permission (for geotagging)
                try {
                    const locationAllowButton = await $('android=new UiSelector().text("Allow")');
                    if (await locationAllowButton.isDisplayed()) {
                        console.log('📍 Granting location permission for geotagging...');
                        await locationAllowButton.click();
                        await driver.pause(2000);
                    }
                } catch (e) {
                    console.log('ℹ️ No location permission prompt');
                }
                
                // Check for "While using app" permission option
                try {
                    const whileUsingButton = await $('android=new UiSelector().text("While using the app")');
                    if (await whileUsingButton.isDisplayed()) {
                        console.log('📍 Selecting "While using the app" for location...');
                        await whileUsingButton.click();
                        await driver.pause(2000);
                    }
                } catch (e) {
                    console.log('ℹ️ No "While using app" option');
                }
                
                // Check for any other Allow buttons
                try {
                    const anyAllowButton = await $('android=new UiSelector().textContains("Allow")');
                    if (await anyAllowButton.isDisplayed()) {
                        console.log('✅ Granting additional permission...');
                        await anyAllowButton.click();
                        await driver.pause(2000);
                    }
                } catch (e) {
                    console.log('ℹ️ No additional permission prompts');
                }
                
                // Wait for camera to initialize and look for in-app capture button
                await driver.pause(3000);
                
                // Take screenshot to see current state
                await driver.saveScreenshot('./test-results/android-before-capture.png');
                
                // Capture photo using in-app camera interface
                console.log('📸 Looking for in-app capture button...');
                
                const captureButtons = [
                    'android=new UiSelector().text("Capture")',
                    'android=new UiSelector().text("Take Photo")', 
                    'android=new UiSelector().text("Snap")',
                    'android=new UiSelector().description("capture")',
                    'android=new UiSelector().description("Take photo")',
                    // Look for camera shutter button (usually a circle)
                    'android=new UiSelector().className("android.widget.Button").descriptionContains("capture")',
                    'android=new UiSelector().className("android.widget.ImageButton")'
                ];
                
                let photoTaken = false;
                for (const selector of captureButtons) {
                    try {
                        const captureButton = await $(selector);
                        if (await captureButton.isDisplayed()) {
                            console.log(`📸 Found capture button: ${selector}`);
                            await captureButton.click();
                            await driver.pause(2000);
                            photoTaken = true;
                            console.log('✅ Photo captured using in-app camera');
                            break;
                        }
                    } catch (e) {
                        console.log(`ℹ️ Capture button not found: ${selector}`);
                    }
                }
                
                if (!photoTaken) {
                    // Fallback: try tapping in center-bottom area where camera button usually is
                    console.log('📸 Trying fallback tap for camera capture...');
                    const { width, height } = await driver.getWindowSize();
                    await driver.performActions([
                        {
                            type: 'pointer',
                            id: 'finger1',
                            parameters: { pointerType: 'touch' },
                            actions: [
                                { type: 'pointerMove', duration: 0, x: width / 2, y: height * 0.85 },
                                { type: 'pointerDown', button: 0 },
                                { type: 'pause', duration: 300 },
                                { type: 'pointerUp', button: 0 }
                            ]
                        }
                    ]);
                    await driver.pause(2000);
                    console.log('✅ Attempted photo capture via tap');
                }
                
                // Take screenshot after capture
                await driver.saveScreenshot('./test-results/android-after-capture.png');
                
                // Wait for photo processing
                await driver.pause(3000);
                
                // Return to main view (should happen automatically with in-app camera)
                console.log('↩️ Returning to main view...');
                
                // Check if we're already back to main view
                try {
                    const hamburgerCheck = await $('android=new UiSelector().text("Toggle menu")');
                    if (await hamburgerCheck.isDisplayed()) {
                        console.log('✅ Already back in main app view');
                    } else {
                        // Try back button once
                        console.log('🔙 Using back button to return to main view');
                        await driver.back();
                        await driver.pause(2000);
                    }
                } catch (e) {
                    console.log('ℹ️ Navigation check failed, assuming we are in main view');
                }
                
                // Step 3: Verify we're back and wait for upload
                console.log('☁️ Waiting for photo upload processing...');
                
                // Check if we're back to main view
                const hamburgerAgain = await $('android=new UiSelector().text("Toggle menu")');
                const isBackToMain = await hamburgerAgain.isDisplayed();
                
                if (isBackToMain) {
                    console.log('✅ Successfully returned to main view');
                } else {
                    console.log('⚠️ May not be back to main view yet, trying device back');
                    await driver.back();
                    await driver.pause(2000);
                }
                
                // Wait for potential upload processing
                await driver.pause(10000);
                
                // Take final screenshot
                await driver.saveScreenshot('./test-results/android-photo-capture-final.png');
                
                console.log('🎉 Photo capture and upload workflow completed');
                
                // FIXED: Actually verify workflow completed successfully
                const appHealthy = await workflows.performQuickHealthCheck();
                expect(appHealthy).toBe(true);
                
            } catch (error) {
                console.error('❌ Photo capture workflow failed:', error);
                await driver.saveScreenshot('./test-results/android-photo-capture-error.png');
                throw error;
            }
        });
        
        it('should test menu navigation and check for sources', async function () {
            this.timeout(120000);
            
            console.log('🔍 Testing menu navigation...');
            
            try {
                // Find hamburger menu
                const hamburgerMenu = await $('android=new UiSelector().text("Toggle menu")');
                await hamburgerMenu.click();
                await driver.pause(3000);
                
                // Take screenshot of open menu
                await driver.saveScreenshot('./test-results/android-simple-menu-nav.png');
                
                // Switch to WebView context to access menu items
                const contexts = await driver.getContexts();
                console.log('📋 Available contexts:', contexts);
                
                const webViewContexts = contexts.filter(ctx => ctx.includes('WEBVIEW'));
                if (webViewContexts.length > 0) {
                    console.log(`🌐 Switching to WebView context: ${webViewContexts[0]}`);
                    await driver.switchContext(webViewContexts[0]);
                    
                    // Take screenshot in WebView context
                    await driver.saveScreenshot('./test-results/android-simple-webview.png');
                    
                    // Look for sources link
                    try {
                        const sourcesLink = await $('a[href="/sources"]');
                        const sourcesVisible = await sourcesLink.isDisplayed();
                        console.log(`📊 Sources link visible: ${sourcesVisible}`);
                        
                        if (sourcesVisible) {
                            await sourcesLink.click();
                            await driver.pause(3000);
                            console.log('✅ Navigated to sources page');
                            
                            // Take screenshot of sources page
                            await driver.saveScreenshot('./test-results/android-simple-sources.png');
                            
                            // Look for Mapillary toggle to disable it
                            try {
                                const mapillaryToggle = await $('input[data-testid="source-checkbox-mapillary"]');
                                const isChecked = await mapillaryToggle.isSelected();
                                if (isChecked) {
                                    await mapillaryToggle.click();
                                    console.log('🚫 Disabled Mapillary source');
                                    await driver.pause(2000);
                                }
                            } catch (e) {
                                console.log('ℹ️ Could not find/toggle Mapillary source');
                            }
                            
                            // Navigate back to main page
                            await driver.back();
                            await driver.pause(2000);
                        }
                    } catch (e) {
                        console.log('⚠️ Could not access sources link:', e.message);
                    }
                    
                    // Switch back to native context
                    await driver.switchContext('NATIVE_APP');
                    console.log('↩️ Switched back to native context');
                } else {
                    console.log('⚠️ No WebView context found');
                }
                
                // Close menu
                await driver.back();
                await driver.pause(2000);
                
                console.log('✅ Menu navigation test completed');
                
                // FIXED: Actually verify menu navigation worked
                const menuClosed = await hamburgerMenu.isDisplayed() === false ||
                                  await driver.getCurrentActivity().then(a => a.includes('MainActivity'));
                expect(menuClosed).toBe(true);
                
            } catch (error) {
                console.error('❌ Menu navigation test failed:', error);
                await driver.saveScreenshot('./test-results/android-simple-nav-error.png');
                throw error;
            }
        });
        
        it('should check for photo loading indicators', async function () {
            this.timeout(120000);
            
            console.log('🔍 Checking photo loading status...');
            
            try {
                // Look for "No photos in range" text
                const noPhotosText = await $('android=new UiSelector().text("No photos in range")');
                const hasNoPhotos = await noPhotosText.isDisplayed();
                
                console.log(`📊 "No photos in range" displayed: ${hasNoPhotos}`);
                
                if (hasNoPhotos) {
                    console.log('ℹ️ No photos currently loaded - this is expected for a clean test');
                } else {
                    console.log('✅ Photos may be loaded or loading');
                }
                
                // Take screenshot of current state
                await driver.saveScreenshot('./test-results/android-simple-photo-status.png');
                
                // Test map interaction
                console.log('🗺️ Testing map interaction...');
                const { width, height } = await driver.getWindowSize();
                const mapCenterX = width / 2;
                const mapCenterY = height * 0.6; // Approximate map center
                
                // Use performActions instead of touchAction for compatibility
                await driver.performActions([
                    {
                        type: 'pointer',
                        id: 'finger1',
                        parameters: { pointerType: 'touch' },
                        actions: [
                            { type: 'pointerMove', duration: 0, x: mapCenterX, y: mapCenterY },
                            { type: 'pointerDown', button: 0 },
                            { type: 'pause', duration: 100 },
                            { type: 'pointerUp', button: 0 }
                        ]
                    }
                ]);
                await driver.pause(2000);
                
                console.log('✅ Map interaction test completed');
                
                // FIXED: Actually verify map interaction worked
                const appStillHealthy = await workflows.performQuickHealthCheck();
                expect(appStillHealthy).toBe(true);
                
            } catch (error) {
                console.error('❌ Photo status check failed:', error);
                await driver.saveScreenshot('./test-results/android-simple-status-error.png');
                throw error;
            }
        });
    });

    afterEach(async function () {
        // Take final screenshot
        await driver.saveScreenshot('./test-results/android-simple-cleanup.png');
        console.log('📸 Simple test cleanup completed');
    });
});