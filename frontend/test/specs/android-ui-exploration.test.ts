import { expect } from '@wdio/globals'

/**
 * Android UI Exploration Test
 * Explores the actual UI structure to understand what elements are available
 */
describe('Android UI Exploration', () => {
    it('should explore the app UI structure and find authentication elements', async function () {
        this.timeout(120000);
        
        console.log('🔍 Starting Android UI exploration...');
        
        // Wait for app to fully load
        await driver.pause(5000);
        
        // Take initial screenshot
        await driver.saveScreenshot('./test-results/android-ui-initial.png');
        console.log('📸 Initial screenshot saved');
        
        // Get page source to understand the UI structure
        console.log('📄 Getting page source...');
        const pageSource = await driver.getPageSource();
        console.log('Page source length:', pageSource.length);
        
        // Look for any text elements that might indicate the current screen
        console.log('🔍 Looking for text elements...');
        
        // Common authentication-related text
        const authTexts = [
            'login', 'Login', 'LOGIN',
            'sign in', 'Sign In', 'SIGN IN', 
            'username', 'Username', 'USERNAME',
            'password', 'Password', 'PASSWORD',
            'email', 'Email', 'EMAIL',
            'auth', 'Auth', 'AUTH',
            'oauth', 'OAuth', 'OAUTH',
            'google', 'Google', 'GOOGLE',
            'github', 'GitHub', 'GITHUB'
        ];
        
        for (const text of authTexts) {
            try {
                const element = await $(`android=new UiSelector().textContains("${text}")`);
                if (await element.isDisplayed()) {
                    console.log(`✓ Found text element: "${text}"`);
                    const elementText = await element.getText();
                    console.log("🢄  Full text: "${elementText}"`);
                }
            } catch (error) {
                // Element not found, continue
            }
        }
        
        // Look for all EditText elements (input fields)
        console.log('🔍 Looking for EditText elements...');
        try {
            const editTexts = await $$('android=new UiSelector().className("android.widget.EditText")');
            console.log(`Found ${editTexts.length} EditText elements`);
            
            for (let i = 0; i < editTexts.length; i++) {
                try {
                    const editText = editTexts[i];
                    const isDisplayed = await editText.isDisplayed();
                    const hint = await editText.getAttribute('hint') || 'No hint';
                    const text = await editText.getText() || 'No text';
                    console.log("🢄  EditText[${i}]: displayed=${isDisplayed}, hint="${hint}", text="${text}"`);
                } catch (error) {
                    console.log("🢄  EditText[${i}]: Error getting properties - ${error.message}`);
                }
            }
        } catch (error) {
            console.log('❌ Error finding EditText elements:', error.message);
        }
        
        // Look for all Button elements
        console.log('🔍 Looking for Button elements...');
        try {
            const buttons = await $$('android=new UiSelector().className("android.widget.Button")');
            console.log(`Found ${buttons.length} Button elements`);
            
            for (let i = 0; i < buttons.length; i++) {
                try {
                    const button = buttons[i];
                    const isDisplayed = await button.isDisplayed();
                    const text = await button.getText() || 'No text';
                    const enabled = await button.isEnabled();
                    console.log("🢄  Button[${i}]: displayed=${isDisplayed}, enabled=${enabled}, text="${text}"`);
                } catch (error) {
                    console.log("🢄  Button[${i}]: Error getting properties - ${error.message}`);
                }
            }
        } catch (error) {
            console.log('❌ Error finding Button elements:', error.message);
        }
        
        // Look for TextView elements that might contain navigation or status info
        console.log('🔍 Looking for TextView elements...');
        try {
            const textViews = await $$('android=new UiSelector().className("android.widget.TextView")');
            console.log(`Found ${textViews.length} TextView elements`);
            
            for (let i = 0; i < Math.min(textViews.length, 10); i++) { // Limit to first 10
                try {
                    const textView = textViews[i];
                    const isDisplayed = await textView.isDisplayed();
                    const text = await textView.getText() || 'No text';
                    if (text.length > 0 && text.length < 100) { // Skip empty or very long text
                        console.log("🢄  TextView[${i}]: displayed=${isDisplayed}, text="${text}"`);
                    }
                } catch (error) {
                    console.log("🢄  TextView[${i}]: Error getting text`);
                }
            }
        } catch (error) {
            console.log('❌ Error finding TextView elements:', error.message);
        }
        
        // Try to find any clickable elements
        console.log('🔍 Looking for clickable elements...');
        try {
            const clickables = await $$('android=new UiSelector().clickable(true)');
            console.log(`Found ${clickables.length} clickable elements`);
            
            for (let i = 0; i < Math.min(clickables.length, 10); i++) { // Limit to first 10
                try {
                    const clickable = clickables[i];
                    const isDisplayed = await clickable.isDisplayed();
                    const className = await clickable.getAttribute('className') || 'Unknown class';
                    const text = await clickable.getText() || 'No text';
                    const contentDesc = await clickable.getAttribute('contentDescription') || 'No description';
                    
                    if (isDisplayed) {
                        console.log("🢄  Clickable[${i}]: class="${className}", text="${text}", desc="${contentDesc}"`);
                    }
                } catch (error) {
                    console.log("🢄  Clickable[${i}]: Error getting properties`);
                }
            }
        } catch (error) {
            console.log('❌ Error finding clickable elements:', error.message);
        }
        
        // Check for WebView elements (in case it's a web-based UI)
        console.log('🔍 Looking for WebView elements...');
        try {
            const webViews = await $$('android=new UiSelector().className("android.webkit.WebView")');
            console.log(`Found ${webViews.length} WebView elements`);
            
            if (webViews.length > 0) {
                console.log('📱 App appears to use WebView - might be a hybrid app');
                
                // Try to switch to WebView context
                const contexts = await driver.getContexts();
                console.log('Available contexts:', contexts);
                
                for (const context of contexts) {
                    if (context.includes('WEBVIEW')) {
                        console.log(`🌐 Switching to WebView context: ${context}`);
                        await driver.switchContext(context);
                        
                        // Take screenshot in WebView context
                        await driver.saveScreenshot('./test-results/android-webview.png');
                        
                        // Try to find HTML elements
                        try {
                            const body = await $('body');
                            if (await body.isDisplayed()) {
                                console.log('✓ WebView HTML content is accessible');
                                
                                // Look for common form elements
                                const inputs = await $$('input');
                                const buttons = await $$('button');
                                console.log(`Found ${inputs.length} input elements and ${buttons.length} button elements in WebView`);
                                
                                // Look for authentication-related elements
                                const loginElements = await $$('[type="text"], [type="email"], [type="password"], button');
                                console.log(`Found ${loginElements.length} potential auth elements in WebView`);
                                
                                for (let i = 0; i < Math.min(loginElements.length, 5); i++) {
                                    try {
                                        const element = loginElements[i];
                                        const tagName = await element.getTagName();
                                        const type = await element.getAttribute('type') || 'no type';
                                        const placeholder = await element.getAttribute('placeholder') || 'no placeholder';
                                        const text = await element.getText() || 'no text';
                                        console.log("🢄  WebView Element[${i}]: ${tagName} type="${type}" placeholder="${placeholder}" text="${text}"`);
                                    } catch (error) {
                                        console.log("🢄  WebView Element[${i}]: Error getting properties`);
                                    }
                                }
                            }
                        } catch (error) {
                            console.log('❌ Could not access WebView HTML content:', error.message);
                        }
                        
                        // Switch back to native context
                        await driver.switchContext('NATIVE_APP');
                        break;
                    }
                }
            }
        } catch (error) {
            console.log('❌ Error checking for WebView elements:', error.message);
        }
        
        // Take final screenshot
        await driver.saveScreenshot('./test-results/android-ui-final.png');
        console.log('📸 Final screenshot saved');
        
        // Check app package info
        console.log('📱 App package info:');
        try {
            const activity = await driver.getCurrentActivity();
            const packageName = await driver.getCurrentPackage();
            console.log("🢄  Current package: ${packageName}`);
            console.log("🢄  Current activity: ${activity}`);
        } catch (error) {
            console.log('❌ Could not get app package info:', error.message);
        }
        
        console.log('✅ UI exploration completed');
        
        // Test always passes - this is just for exploration
        expect(true).toBe(true);
    });
});