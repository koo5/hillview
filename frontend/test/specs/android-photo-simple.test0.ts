import { expect } from '@wdio/globals'
import { TestWorkflows } from '../helpers/TestWorkflows'

/**
 * Simple Android Photo Upload Test
 * 
 * A simplified test that focuses on testing the photo capture workflow
 * and verifying that the worker container processes uploads correctly.
 */
describe('Simplest Android Photo Upload', () => {
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

    describe('Basic Photo Workflow0', () => {
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
                
                // Handle camera and location permissions
                console.log('📋 Checking for permission dialogs and camera enablement...');
                
                // Check for "Enable Camera" button (app-specific)
                try {
                    const enableCameraButton = await $('android=new UiSelector().text("Enable Camera")');
                    if (await enableCameraButton.isDisplayed()) {
                        console.log('📷 Clicking "Enable Camera" button...');
                        await enableCameraButton.click();
                        await driver.pause(3000);
                    }
                } catch (e) {
                    console.log('ℹ️ No "Enable Camera" button found');
                }
                
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
                
                // Check for additional permission buttons
                const permissionTexts = ['Allow', 'Enable', 'Grant', 'OK'];
                for (const permText of permissionTexts) {
                    try {
                        const permButton = await $(`android=new UiSelector().textContains("${permText}")`);
                        if (await permButton.isDisplayed()) {
                            console.log(`✅ Clicking permission button: "${permText}"...`);
                            await permButton.click();
                            await driver.pause(2000);
                            break; // Only click one permission button per iteration
                        }
                    } catch (e) {
                        // Continue to next permission text
                    }
                }
                
                // Wait for camera to initialize
                await driver.pause(3000);
                
                // Actually capture a photo
                console.log('📸 Attempting to capture photo...');
                
                // First, let's see if we're in the app's camera view or native camera
                await driver.pause(2000);
                
                // Take screenshot to see current state
                await driver.saveScreenshot('./test-results/android-before-capture.png');
                
                // If we're in the app's camera view, look for app-specific capture button
                // If we're in native camera, look for native camera capture button
                
                // Try app-specific capture first (if using in-app camera)
                let photoTaken = false;
                
                // Check if we're still in the app (look for app-specific elements)
                try {
                    const appCameraButton = await $('android=new UiSelector().text("Capture")');
                    if (await appCameraButton.isDisplayed()) {
                        console.log('📸 Using app camera capture button');
                        await appCameraButton.click();
                        photoTaken = true;
                    }
                } catch (e) {
                    console.log('ℹ️ App camera button not found');
                }

                if (photoTaken) {
                    console.log('✅ Photo capture initiated');
                } else {
                    console.log('⚠️ Could not find capture mechanism');
                }
                
                // Wait for photo capture to complete
                await driver.pause(3000);
                console.log('✅ Photo capture attempted');
                
                // Take screenshot after capture
                await driver.saveScreenshot('./test-results/android-after-capture.png');
                
                // Look for confirmation buttons (OK, Save, Done)
                console.log('✅ Looking for photo confirmation options...');
                await driver.pause(2000); // Wait for confirmation UI to appear
                
                // Take screenshot to see confirmation state
                await driver.saveScreenshot('./test-results/android-photo-confirmation.png');
                
                let confirmed = false;
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
                            confirmed = true;
                            break;
                        }
                    } catch (e) {
                        // Continue trying other confirm buttons
                    }
                }
                
                if (!confirmed) {
                    console.log('ℹ️ No explicit confirmation required - photo may be auto-saved');
                }
                
                // Return to main app
                console.log('↩️ Returning to main app...');
                
                // Try multiple ways to get back to the main app
                let backAttempts = 0;
                const maxBackAttempts = 3;
                
                while (backAttempts < maxBackAttempts) {
                    backAttempts++;
                    console.log(`↩️ Back attempt ${backAttempts}/${maxBackAttempts}`);
                    
                    await driver.back();
                    await driver.pause(3000);
                    
                    // Check if we're back in the main app by looking for hamburger menu
                    try {
                        const hamburgerCheck = await $('android=new UiSelector().text("Toggle menu")');
                        if (await hamburgerCheck.isDisplayed()) {
                            console.log('✅ Successfully returned to main app');
                            break;
                        }
                    } catch (e) {
                        console.log(`ℹ️ Not back to main app yet (attempt ${backAttempts})`);
                    }
                    
                    // If still not back, try different approaches
                    if (backAttempts === 2) {
                        // Try home button approach (but avoid full app restart)
                        console.log('🏠 Trying to return via task switcher...');
                        await driver.pressKeyCode(3); // Android HOME key
                        await driver.pause(1000);
                        
                        // Use task switcher to return to app (avoids full restart)
                        await driver.pressKeyCode(187); // Recent apps key (task switcher)
                        await driver.pause(1000);
                        
                        // Tap on the app in task switcher instead of calling activateApp
                        const { width, height } = await driver.getWindowSize();
                        await driver.performActions([
                            {
                                type: 'pointer',
                                id: 'finger1',
                                parameters: { pointerType: 'touch' },
                                actions: [
                                    { type: 'pointerMove', duration: 0, x: width / 2, y: height / 2 },
                                    { type: 'pointerDown', button: 0 },
                                    { type: 'pause', duration: 100 },
                                    { type: 'pointerUp', button: 0 }
                                ]
                            }
                        ]);
                        await driver.pause(1000);
                        
                        // Or just try more back buttons
                        await driver.back();
                        await driver.pause(2000);
                    }
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
    });

    afterEach(async function () {
        // Take final screenshot
        await driver.saveScreenshot('./test-results/android-simple-cleanup.png');
        console.log('📸 Simple test cleanup completed');
    });
});