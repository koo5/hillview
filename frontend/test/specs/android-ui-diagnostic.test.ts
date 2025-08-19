import { expect } from '@wdio/globals'
// App lifecycle management is now handled by wdio.conf.ts session-level hooks

/**
 * Android UI Diagnostic Test
 * 
 * This test helps us understand the actual UI structure of the Android app
 * to create proper selectors for the photo upload workflow test.
 */
describe('Android UI Diagnostic', () => {
    beforeEach(async function () {
        this.timeout(90000);
        
        // Clean app state is automatically provided by wdio.conf.ts beforeTest hook
        console.log('🧪 Starting UI diagnostic test with clean app state');
    });

    describe('UI Structure Discovery', () => {
        it('should analyze the app UI structure', async function () {
            this.timeout(120000);
            
            console.log('🔍 Analyzing Android app UI structure...');
            
            try {
                // Take screenshot of initial state
                await driver.saveScreenshot('./test-results/android-ui-initial.png');
                
                // Get the page source to understand structure
                const pageSource = await driver.getPageSource();
                console.log('📄 Page source length:', pageSource.length);
                
                // Look for common Android UI elements
                console.log('🔍 Looking for WebView elements...');
                const webViews = await $$('android.webkit.WebView');
                console.log(`📱 Found ${webViews.length} WebView(s)`);
                
                // Look for buttons and clickable elements
                console.log('🔍 Looking for clickable elements...');
                const clickableElements = await $$('android=new UiSelector().clickable(true)');
                console.log(`🖱️ Found ${clickableElements.length} clickable elements`);
                
                // Try to find elements by content description
                console.log('🔍 Looking for elements with content descriptions...');
                try {
                    const descriptiveElements = await $$('//*[@content-desc]');
                    console.log(`📝 Found ${descriptiveElements.length} elements with content-desc`);
                    
                    // Log first few content descriptions
                    for (let i = 0; i < Math.min(descriptiveElements.length, 5); i++) {
                        try {
                            const desc = await descriptiveElements[i].getAttribute('content-desc');
                            console.log(`  ${i}: content-desc="${desc}"`);
                        } catch (e) {
                            console.log(`  ${i}: could not read content-desc`);
                        }
                    }
                } catch (e) {
                    console.log('⚠️ Could not find elements by content-desc');
                }
                
                // Try to find elements by text
                console.log('🔍 Looking for elements with text...');
                try {
                    const textElements = await $$('//*[@text]');
                    console.log(`📝 Found ${textElements.length} elements with text`);
                    
                    // Log first few text values
                    for (let i = 0; i < Math.min(textElements.length, 10); i++) {
                        try {
                            const text = await textElements[i].getAttribute('text');
                            if (text && text.trim()) {
                                console.log(`  ${i}: text="${text}"`);
                            }
                        } catch (e) {
                            console.log(`  ${i}: could not read text`);
                        }
                    }
                } catch (e) {
                    console.log('⚠️ Could not find elements by text');
                }
                
                // Try to find buttons specifically
                console.log('🔍 Looking for buttons...');
                try {
                    const buttons = await $$('android.widget.Button');
                    console.log(`🔘 Found ${buttons.length} buttons`);
                    
                    for (let i = 0; i < buttons.length; i++) {
                        try {
                            const text = await buttons[i].getText();
                            const desc = await buttons[i].getAttribute('content-desc');
                            console.log(`  Button ${i}: text="${text}", desc="${desc}"`);
                        } catch (e) {
                            console.log(`  Button ${i}: could not read properties`);
                        }
                    }
                } catch (e) {
                    console.log('⚠️ Could not find buttons');
                }
                
                // Try to interact with WebView content
                if (webViews.length > 0) {
                    console.log('🌐 Trying to interact with WebView content...');
                    try {
                        // Switch to WebView context
                        const contexts = await driver.getContexts();
                        console.log('📋 Available contexts:', contexts);
                        
                        // Look for WebView contexts
                        const webViewContexts = contexts.filter(ctx => ctx.includes('WEBVIEW'));
                        if (webViewContexts.length > 0) {
                            console.log(`🌐 Found ${webViewContexts.length} WebView contexts`);
                            
                            // Switch to first WebView context
                            await driver.switchContext(webViewContexts[0]);
                            console.log('✅ Switched to WebView context');
                            
                            // Take screenshot in WebView context
                            await driver.saveScreenshot('./test-results/android-webview-context.png');
                            
                            // Try to find elements in WebView
                            try {
                                const hamburgerMenu = await $('[data-testid="hamburger-menu"]');
                                const isDisplayed = await hamburgerMenu.isDisplayed();
                                console.log('🍔 Hamburger menu found in WebView:', isDisplayed);
                                
                                if (isDisplayed) {
                                    console.log('✅ WebView UI elements are accessible!');
                                }
                            } catch (e) {
                                console.log('⚠️ Could not find hamburger menu in WebView');
                            }
                            
                            // Switch back to native context
                            await driver.switchContext('NATIVE_APP');
                            console.log('↩️ Switched back to native context');
                        }
                    } catch (e) {
                        console.log('⚠️ Error interacting with WebView:', e.message);
                    }
                }
                
                console.log('✅ UI structure analysis completed');
                expect(true).toBe(true);
                
            } catch (error) {
                console.error('❌ UI analysis failed:', error);
                await driver.saveScreenshot('./test-results/android-ui-error.png');
                throw error;
            }
        });
    });

    afterEach(async function () {
        // Take final screenshot
        await driver.saveScreenshot('./test-results/android-ui-diagnostic-final.png');
        console.log('📸 UI diagnostic cleanup completed');
    });
});