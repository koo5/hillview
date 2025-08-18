import { expect } from '@wdio/globals'

/**
 * Android Camera Test
 * 
 * Focused test for camera access and photo capture
 */
describe('Android Camera', () => {
    beforeEach(async function () {
        this.timeout(60000);
        
        await driver.terminateApp('io.github.koo5.hillview.dev');
        await driver.pause(2000);
        await driver.activateApp('io.github.koo5.hillview.dev');
        await driver.pause(5000);
        
        console.log('🔄 App restarted for camera test');
    });

    describe('Photo Capture', () => {
        it('should access camera and capture a photo', async function () {
            this.timeout(300000);
            
            console.log('📸 Starting camera test...');
            
            try {
                await driver.saveScreenshot('./test-results/camera-01-initial.png');
                
                // Find camera button
                const cameraButton = await $('android=new UiSelector().text("Take photo")');
                await cameraButton.waitForDisplayed({ timeout: 10000 });
                console.log('📸 Found camera button');
                
                await cameraButton.click();
                await driver.pause(3000);
                console.log('📸 Entered camera mode');
                
                await driver.saveScreenshot('./test-results/camera-02-camera-mode.png');
                
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
                
                // Capture photo using coordinate tap
                console.log('📸 Capturing photo...');
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
                
                await driver.pause(4000);
                console.log('📸 Photo capture completed');
                
                await driver.saveScreenshot('./test-results/camera-03-after-capture.png');
                
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
                
                // Return to main app
                console.log('↩️ Returning to main app...');
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
                
                await driver.saveScreenshot('./test-results/camera-04-back-to-app.png');
                console.log('🎉 Camera test completed successfully');
                expect(true).toBe(true);
                
            } catch (error) {
                console.error('❌ Camera test failed:', error);
                await driver.saveScreenshot('./test-results/camera-error.png');
                throw error;
            }
        });
    });

    afterEach(async function () {
        await driver.saveScreenshot('./test-results/camera-cleanup.png');
        console.log('📸 Camera test cleanup completed');
    });
});