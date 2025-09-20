import { expect } from '@wdio/globals'
import { TestWorkflows } from '../helpers/TestWorkflows'
import { ScreenshotHelper } from '../helpers/ScreenshotHelper'

/**
 * Android Photo Loading Test
 * 
 * Tests photo loading indicators, map interaction, and app responsiveness
 */
describe('Android Photo Loading', () => {
    let workflows: TestWorkflows;
    let screenshots: ScreenshotHelper;
    
    beforeEach(async function () {
        this.timeout(90000);
        
        // Initialize helpers
        workflows = new TestWorkflows();
        screenshots = new ScreenshotHelper('photo-loading');
        screenshots.reset();
        
        console.log('🧪 Starting photo loading test with clean app state');
    });

    describe('Photo Loading and Map Interaction', () => {
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
                await screenshots.takeScreenshot('photo-status');
                
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
                
                // Verify map interaction worked
                const appStillHealthy = await workflows.performQuickHealthCheck();
                expect(appStillHealthy).toBe(true);
                
            } catch (error) {
                console.error('❌ Photo status check failed:', error);
                await screenshots.takeScreenshot('status-error');
                throw error;
            }
        });
    });

    afterEach(async function () {
        // Take final screenshot
        await screenshots.takeScreenshot('cleanup');
        console.log('📸 Photo loading test cleanup completed');
    });
});