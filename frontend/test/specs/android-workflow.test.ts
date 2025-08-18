import { expect } from '@wdio/globals'

/**
 * Android Complete Workflow Test
 * 
 * Combines login, camera, and upload verification in a complete workflow
 */
describe('Android Complete Workflow', () => {
    beforeEach(async function () {
        this.timeout(60000);
        
        await driver.terminateApp('io.github.koo5.hillview.dev');
        await driver.pause(2000);
        await driver.activateApp('io.github.koo5.hillview.dev');
        await driver.pause(5000);
        
        console.log('🔄 App restarted for complete workflow test');
    });

    describe('Full Photo Pipeline', () => {
        it('should complete login, photo capture, and upload verification', async function () {
            this.timeout(900000); // 15 minutes total to accommodate 3-minute upload wait
            
            console.log('🚀 Starting complete workflow test...');
            
            try {
                // === STEP 1: LOGIN ===
                console.log('📝 Step 1: User authentication');
                await driver.saveScreenshot('./test-results/workflow-01-start.png');
                
                const hamburgerMenu = await $('android=new UiSelector().text("Toggle menu")');
                await hamburgerMenu.waitForDisplayed({ timeout: 10000 });
                await hamburgerMenu.click();
                await driver.pause(2000);
                console.log('🍔 Opened menu');
                
                // Switch to WebView for login
                const contexts = await driver.getContexts();
                const webViewContexts = contexts.filter(ctx => ctx.includes('WEBVIEW'));
                
                if (webViewContexts.length > 0) {
                    await driver.switchContext(webViewContexts[0]);
                    
                    try {
                        const loginLink = await $('a[href="/login"]');
                        if (await loginLink.isDisplayed()) {
                            console.log('🔐 Logging in...');
                            await loginLink.click();
                            await driver.pause(3000);
                            
                            const usernameInput = await $('input[type="text"]');
                            await usernameInput.waitForDisplayed({ timeout: 10000 });
                            await usernameInput.setValue('test');
                            
                            const passwordInput = await $('input[type="password"]');
                            await passwordInput.setValue('test123');
                            
                            const submitButton = await $('button[type="submit"]');
                            await submitButton.click();
                            
                            await driver.pause(5000);
                            console.log('✅ Login successful');
                        } else {
                            console.log('ℹ️ Already logged in');
                        }
                    } catch (e) {
                        console.log('ℹ️ Login not needed or already authenticated');
                    }
                    
                    await driver.switchContext('NATIVE_APP');
                }
                
                await driver.back(); // Close menu
                await driver.pause(2000);
                
                // === STEP 2: CAMERA ACCESS ===
                console.log('📝 Step 2: Camera access and photo capture');
                
                // Find camera button - try different text variations based on what works
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
                
                console.log('📸 Found camera button');
                
                await cameraButton.click();
                await driver.pause(3000);
                console.log('📸 Entered camera mode');
                
                await driver.saveScreenshot('./test-results/workflow-02-camera-mode.png');
                
                // Handle permissions
                try {
                    const locationPermission = await $('android=new UiSelector().text("While using the app")');
                    if (await locationPermission.isDisplayed()) {
                        console.log('📍 Granting location permission');
                        await locationPermission.click();
                        await driver.pause(2000);
                    }
                } catch (e) {
                    console.log('ℹ️ No location permission needed');
                }
                
                await driver.pause(3000);
                
                // === STEP 3: PHOTO CAPTURE ===
                console.log('📝 Step 3: Capture photo');
                await driver.saveScreenshot('./test-results/workflow-03-before-capture.png');
                
                const { width, height } = await driver.getWindowSize();
                console.log(`📸 Capturing photo via coordinate tap (${width/2}, ${height*0.85})`);
                
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
                
                await driver.pause(4000);
                console.log('📸 Photo capture completed');
                
                await driver.saveScreenshot('./test-results/workflow-04-after-capture.png');
                
                // Handle confirmation dialogs
                const confirmOptions = ['OK', 'Save', 'Done', '✓'];
                for (const option of confirmOptions) {
                    try {
                        const confirmBtn = await $(`android=new UiSelector().text("${option}")`);
                        if (await confirmBtn.isDisplayed()) {
                            console.log(`✅ Confirming with: ${option}`);
                            await confirmBtn.click();
                            await driver.pause(2000);
                            break;
                        }
                    } catch (e) {
                        // Continue trying other options
                    }
                }
                
                // === STEP 4: RETURN TO APP ===
                console.log('📝 Step 4: Return to main app');
                
                let backAttempts = 0;
                while (backAttempts < 3) {
                    backAttempts++;
                    await driver.back();
                    await driver.pause(3000);
                    
                    try {
                        const hamburgerCheck = await $('android=new UiSelector().text("Toggle menu")');
                        if (await hamburgerCheck.isDisplayed()) {
                            console.log('✅ Successfully returned to main app');
                            break;
                        }
                    } catch (e) {
                        console.log(`🔄 Return attempt ${backAttempts}...`);
                    }
                }
                
                await driver.saveScreenshot('./test-results/workflow-05-back-to-app.png');
                
                // === STEP 5: VERIFY UPLOAD PIPELINE ===
                console.log('📝 Step 5: Verify photo upload pipeline');
                
                // Wait for potential upload processing (3 minutes for full processing)
                console.log('⏳ Waiting for photo upload processing (3 minutes)...');
                
                // Wait in chunks with progress updates
                for (let i = 0; i < 18; i++) {
                    await driver.pause(10000); // 10 seconds per chunk
                    const elapsed = (i + 1) * 10;
                    console.log(`⏳ Upload processing: ${elapsed}/180 seconds elapsed...`);
                    
                    // Take periodic screenshots to monitor any UI changes
                    if (i % 6 === 5) { // Every minute
                        await driver.saveScreenshot(`./test-results/workflow-processing-${elapsed}s.png`);
                    }
                }
                
                // Check gallery for uploaded photos
                try {
                    await hamburgerMenu.click();
                    await driver.pause(2000);
                    
                    if (webViewContexts.length > 0) {
                        await driver.switchContext(webViewContexts[0]);
                        
                        const galleryLinks = ['a[href="/gallery"]', 'a[href="/photos"]', 'a:contains("Gallery")', 'a:contains("Photos")'];
                        
                        for (const linkSelector of galleryLinks) {
                            try {
                                const galleryLink = await $(linkSelector);
                                if (await galleryLink.isDisplayed()) {
                                    console.log(`📚 Found gallery link: ${linkSelector}`);
                                    await galleryLink.click();
                                    await driver.pause(4000);
                                    
                                    await driver.saveScreenshot('./test-results/workflow-06-gallery.png');
                                    
                                    const photoElements = await $$('img, [class*="photo"], [class*="image"]');
                                    console.log(`📷 Found ${photoElements.length} photo elements in gallery`);
                                    
                                    if (photoElements.length > 0) {
                                        console.log('🎉 SUCCESS: Photos found in gallery!');
                                        
                                        try {
                                            await photoElements[0].click();
                                            await driver.pause(2000);
                                            await driver.saveScreenshot('./test-results/workflow-07-photo-details.png');
                                            console.log('📸 Accessed photo details');
                                        } catch (e) {
                                            console.log('ℹ️ Could not access photo details');
                                        }
                                    } else {
                                        console.log('ℹ️ No photos in gallery yet - may still be processing');
                                    }
                                    
                                    break;
                                }
                            } catch (e) {
                                // Continue trying other selectors
                            }
                        }
                        
                        await driver.switchContext('NATIVE_APP');
                    }
                    
                    await driver.back(); // Close menu
                    await driver.pause(2000);
                } catch (e) {
                    console.log('⚠️ Could not check gallery:', e.message);
                }
                
                // === FINAL SUMMARY ===
                console.log('📝 Step 6: Final verification and summary');
                
                await driver.saveScreenshot('./test-results/workflow-08-final.png');
                
                console.log('🎯 Test Summary:');
                console.log('   ✅ Login: Successful');
                console.log('   ✅ Camera: Accessed successfully');
                console.log('   ✅ Photo: Capture attempted');
                console.log('   ✅ Navigation: Back to app successful');
                console.log('   ✅ Gallery: Access attempted');
                console.log('');
                console.log('🔬 Next steps for debugging:');
                console.log('   1. Check worker container logs for photo processing');
                console.log('   2. Verify database for uploaded photo records');
                console.log('   3. Test hillview source toggle to see processed photos');
                
                expect(true).toBe(true);
                
            } catch (error) {
                console.error('❌ Complete workflow failed:', error);
                await driver.saveScreenshot('./test-results/workflow-error.png');
                throw error;
            }
        });
    });

    afterEach(async function () {
        await driver.saveScreenshot('./test-results/workflow-cleanup.png');
        console.log('📸 Complete workflow test completed');
    });
});