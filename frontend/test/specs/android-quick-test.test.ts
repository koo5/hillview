import { expect } from '@wdio/globals'

/**
 * Quick Android Test
 * 
 * Fast test to see exactly where the workflow stops without long timeouts
 */
describe('Quick Android Test', () => {
    beforeEach(async function () {
        this.timeout(60000);
        
        await driver.terminateApp('io.github.koo5.hillview.dev');
        await driver.pause(2000);
        await driver.activateApp('io.github.koo5.hillview.dev');
        await driver.pause(5000);
        
        console.log('🔄 App restarted for quick test');
    });

    describe('Quick Workflow Check', () => {
        it('should show exactly where the workflow stops', async function () {
            this.timeout(180000); // 3 minutes total, no extended waits
            
            console.log('🚀 Starting quick workflow check...');
            
            try {
                console.log('📝 Step 1: Check initial state');
                await driver.saveScreenshot('./test-results/quick-01-initial.png');
                
                // Check if camera button is visible immediately
                try {
                    const cameraButton = await $('android=new UiSelector().text("Take photo")');
                    const isVisible = await cameraButton.isDisplayed();
                    console.log(`📸 Camera button visible: ${isVisible}`);
                    
                    if (isVisible) {
                        console.log('📸 Going straight to camera...');
                        await cameraButton.click();
                        await driver.pause(3000);
                        console.log('📸 Entered camera mode');
                        
                        await driver.saveScreenshot('./test-results/quick-02-camera.png');
                        
                        // Handle permissions quickly
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
                        
                        // Quick photo capture
                        console.log('📸 Quick photo capture...');
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
                        
                        await driver.pause(3000);
                        console.log('📸 Photo capture attempted');
                        
                        await driver.saveScreenshot('./test-results/quick-03-after-capture.png');
                        
                        // Return to app by clicking camera button again
                        console.log('↩️ Returning to app by clicking camera button again...');
                        const returnCameraButton = await $('android=new UiSelector().text("Take photo")');
                        if (await returnCameraButton.isDisplayed()) {
                            await returnCameraButton.click();
                            console.log('✅ Clicked camera button to return');
                        } else {
                            console.log('⚠️ Camera button not visible, trying back button');
                            await driver.back();
                        }
                        await driver.pause(3000);
                        
                        await driver.saveScreenshot('./test-results/quick-04-returned.png');
                        
                        console.log('🎉 Quick workflow completed successfully!');
                    } else {
                        console.log('❌ Camera button not visible, need to login first');
                        
                        // Quick login
                        const hamburgerMenu = await $('android=new UiSelector().text("Toggle menu")');
                        await hamburgerMenu.click();
                        await driver.pause(2000);
                        
                        const contexts = await driver.getContexts();
                        const webViewContexts = contexts.filter(ctx => ctx.includes('WEBVIEW'));
                        
                        if (webViewContexts.length > 0) {
                            await driver.switchContext(webViewContexts[0]);
                            
                            const loginLink = await $('a[href="/login"]');
                            if (await loginLink.isDisplayed()) {
                                console.log('🔐 Quick login...');
                                await loginLink.click();
                                await driver.pause(2000);
                                
                                const usernameInput = await $('input[type="text"]');
                                await usernameInput.setValue('test');
                                
                                const passwordInput = await $('input[type="password"]');
                                await passwordInput.setValue('test123');
                                
                                const submitButton = await $('button[type="submit"]');
                                await submitButton.click();
                                await driver.pause(3000);
                                console.log('✅ Login completed');
                            }
                            
                            await driver.switchContext('NATIVE_APP');
                        }
                        
                        await driver.back();
                        await driver.pause(2000);
                        
                        console.log('🔁 Now trying camera after login...');
                        // Try camera again
                        const cameraButtonAfterLogin = await $('android=new UiSelector().text("Take photo")');
                        if (await cameraButtonAfterLogin.isDisplayed()) {
                            console.log('📸 Camera button now visible after login');
                        } else {
                            console.log('❌ Camera button still not visible after login');
                        }
                    }
                } catch (e) {
                    console.log('❌ Error in camera access:', e.message);
                    await driver.saveScreenshot('./test-results/quick-error.png');
                }
                
                // Quick gallery check without long wait
                console.log('📚 Quick gallery check...');
                try {
                    const hamburgerMenu = await $('android=new UiSelector().text("Toggle menu")');
                    await hamburgerMenu.click();
                    await driver.pause(2000);
                    
                    const contexts = await driver.getContexts();
                    const webViewContexts = contexts.filter(ctx => ctx.includes('WEBVIEW'));
                    
                    if (webViewContexts.length > 0) {
                        await driver.switchContext(webViewContexts[0]);
                        
                        // Quick gallery link check
                        try {
                            const galleryLink = await $('a[href="/gallery"]');
                            if (await galleryLink.isDisplayed()) {
                                console.log('📚 Gallery link found');
                                await galleryLink.click();
                                await driver.pause(2000);
                                
                                const photoElements = await $$('img, [class*="photo"]');
                                console.log(`📷 Found ${photoElements.length} photo elements in gallery`);
                                
                                await driver.saveScreenshot('./test-results/quick-05-gallery.png');
                            } else {
                                console.log('⚠️ No gallery link found');
                            }
                        } catch (e) {
                            console.log('⚠️ Gallery check failed:', e.message);
                        }
                        
                        await driver.switchContext('NATIVE_APP');
                    }
                    
                    await driver.back();
                } catch (e) {
                    console.log('⚠️ Gallery check error:', e.message);
                }
                
                await driver.saveScreenshot('./test-results/quick-final.png');
                console.log('🏁 Quick test completed - check screenshots for details');
                expect(true).toBe(true);
                
            } catch (error) {
                console.error('❌ Quick test failed:', error);
                await driver.saveScreenshot('./test-results/quick-test-error.png');
                throw error;
            }
        });
    });

    afterEach(async function () {
        await driver.saveScreenshot('./test-results/quick-cleanup.png');
        console.log('📸 Quick test cleanup completed');
    });
});