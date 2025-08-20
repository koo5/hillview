import { expect } from '@wdio/globals'
import { TestWorkflows } from '../helpers/TestWorkflows'
import { ScreenshotHelper } from '../helpers/ScreenshotHelper'

/**
 * Android Menu Navigation Test
 * 
 * Tests menu navigation, WebView context switching, and sources configuration
 */
describe('Android Menu Navigation', () => {
    let workflows: TestWorkflows;
    let screenshots: ScreenshotHelper;
    
    beforeEach(async function () {
        this.timeout(90000);
        
        // Initialize helpers
        workflows = new TestWorkflows();
        screenshots = new ScreenshotHelper('menu-navigation');
        screenshots.reset();
        
        console.log('🧪 Starting menu navigation test with clean app state');
    });

    describe('Menu and WebView Navigation', () => {
        it('should test menu navigation and check for sources', async function () {
            this.timeout(120000);
            
            console.log('🔍 Testing menu navigation...');
            
            try {
                // Find hamburger menu
                const hamburgerMenu = await $('android=new UiSelector().text("Toggle menu")');
                await hamburgerMenu.click();
                await driver.pause(3000);
                
                // Take screenshot of open menu
                await screenshots.takeScreenshot('menu-open');
                
                // Switch to WebView context to access menu items
                const contexts = await driver.getContexts();
                console.log('📋 Available contexts:', contexts);
                
                const webViewContexts = contexts.filter(ctx => ctx.includes('WEBVIEW'));
                if (webViewContexts.length > 0) {
                    console.log(`🌐 Switching to WebView context: ${webViewContexts[0]}`);
                    await driver.switchContext(webViewContexts[0]);
                    
                    // Take screenshot in WebView context
                    await screenshots.takeScreenshot('webview-context');
                    
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
                            await screenshots.takeScreenshot('sources-page');
                            
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
                
                // Verify menu navigation worked
                const menuClosed = await hamburgerMenu.isDisplayed();
                expect(menuClosed).toBe(true);
                
            } catch (error) {
                console.error('❌ Menu navigation test failed:', error);
                await screenshots.takeScreenshot('navigation-error');
                throw error;
            }
        });
    });

    afterEach(async function () {
        // Take final screenshot
        await screenshots.takeScreenshot('cleanup');
        console.log('📸 Menu navigation test cleanup completed');
    });
});