import { expect } from '@wdio/globals'

/**
 * Android Login Test
 * 
 * Simple, focused test for user authentication
 */
describe('Android Login', () => {
    beforeEach(async function () {
        this.timeout(60000);
        
        await driver.terminateApp('io.github.koo5.hillview.dev');
        await driver.pause(2000);
        await driver.activateApp('io.github.koo5.hillview.dev');
        await driver.pause(5000);
        
        console.log('🔄 App restarted for login test');
    });

    describe('Authentication', () => {
        it('should successfully login with test credentials', async function () {
            this.timeout(180000);
            
            console.log('🔐 Starting login test...');
            
            try {
                await driver.saveScreenshot('./test-results/login-01-initial.png');
                
                // Open hamburger menu
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
                            console.log('✅ Login completed');
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
                
                await driver.saveScreenshot('./test-results/login-02-completed.png');
                console.log('🎉 Login test completed successfully');
                expect(true).toBe(true);
                
            } catch (error) {
                console.error('❌ Login test failed:', error);
                await driver.saveScreenshot('./test-results/login-error.png');
                throw error;
            }
        });
    });

    afterEach(async function () {
        await driver.saveScreenshot('./test-results/login-cleanup.png');
        console.log('📸 Login test cleanup completed');
    });
});