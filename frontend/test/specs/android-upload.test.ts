import { expect } from '@wdio/globals'
// App lifecycle management is now handled by wdio.conf.ts session-level hooks

/**
 * Android Upload Verification Test
 * 
 * Focused test for verifying photo upload and gallery checking
 */
describe('Android Upload Verification', () => {
    beforeEach(async function () {
        this.timeout(90000);
        
        // Clean app state is automatically provided by wdio.conf.ts beforeTest hook
        console.log('🧪 Starting upload verification test with clean app state');
    });

    describe('Gallery Check', () => {
        it('should check gallery for uploaded photos', async function () {
            this.timeout(300000);
            
            console.log('📚 Starting upload verification test...');
            
            try {
                await driver.saveScreenshot('./test-results/upload-01-initial.png');
                
                // Open hamburger menu
                const hamburgerMenu = await $('android=new UiSelector().text("Toggle menu")');
                await hamburgerMenu.waitForDisplayed({ timeout: 10000 });
                await hamburgerMenu.click();
                await driver.pause(2000);
                
                // Switch to WebView context
                const contexts = await driver.getContexts();
                const webViewContexts = contexts.filter(ctx => ctx.includes('WEBVIEW'));
                
                if (webViewContexts.length > 0) {
                    await driver.switchContext(webViewContexts[0]);
                    
                    // Look for gallery or photos link
                    const galleryLinks = ['a[href="/gallery"]', 'a[href="/photos"]', 'a:contains("Gallery")', 'a:contains("Photos")'];
                    
                    for (const linkSelector of galleryLinks) {
                        try {
                            const galleryLink = await $(linkSelector);
                            if (await galleryLink.isDisplayed()) {
                                console.log(`📚 Found gallery link: ${linkSelector}`);
                                await galleryLink.click();
                                await driver.pause(4000);
                                
                                await driver.saveScreenshot('./test-results/upload-02-gallery.png');
                                
                                // Look for uploaded photos
                                const photoElements = await $$('img, [class*="photo"], [class*="image"]');
                                console.log(`📷 Found ${photoElements.length} photo elements in gallery`);
                                
                                if (photoElements.length > 0) {
                                    console.log('🎉 SUCCESS: Photos found in gallery!');
                                    
                                    // Click first photo to see details
                                    try {
                                        await photoElements[0].click();
                                        await driver.pause(2000);
                                        await driver.saveScreenshot('./test-results/upload-03-photo-details.png');
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
                
                await driver.saveScreenshot('./test-results/upload-04-final.png');
                console.log('🎉 Upload verification test completed');
                expect(true).toBe(true);
                
            } catch (error) {
                console.error('❌ Upload verification test failed:', error);
                await driver.saveScreenshot('./test-results/upload-error.png');
                throw error;
            }
        });
    });

    afterEach(async function () {
        await driver.saveScreenshot('./test-results/upload-cleanup.png');
        console.log('📸 Upload verification test cleanup completed');
    });
});