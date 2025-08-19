import { $ } from '@wdio/globals';

/**
 * Page object for WebView-based authentication interactions
 */
export class WebViewAuthPage {
    // Navigation
    async switchToWebView(): Promise<boolean> {
        console.log('🌐 Switching to WebView context...');
        
        const contexts = await driver.getContexts();
        const webViewContexts = contexts.filter(ctx => ctx.includes('WEBVIEW'));
        
        if (webViewContexts.length > 0) {
            await driver.switchContext(webViewContexts[0]);
            console.log(`✅ Switched to WebView: ${webViewContexts[0]}`);
            return true;
        } else {
            console.log('⚠️ No WebView context found');
            return false;
        }
    }

    async switchToNativeApp(): Promise<void> {
        console.log('📱 Switching back to native context...');
        await driver.switchContext('NATIVE_APP');
        console.log('✅ Switched to native context');
    }

    // Auth actions
    async performLogin(username: string = 'test', password: string = 'test123'): Promise<boolean> {
        console.log('🔐 Performing login...');
        
        try {
            const loginLink = await $('a[href="/login"]');
            const loginVisible = await loginLink.isDisplayed();
            
            if (!loginVisible) {
                console.log('ℹ️ Already logged in or login link not found');
                return true;
            }

            console.log('🔗 Clicking login link...');
            await loginLink.click();
            await driver.pause(3000);
            
            // Fill credentials
            const usernameInput = await $('input[type="text"]');
            await usernameInput.waitForDisplayed({ timeout: 10000 });
            await usernameInput.setValue(username);
            console.log('✅ Username entered');
            
            const passwordInput = await $('input[type="password"]');
            await passwordInput.setValue(password);
            console.log('✅ Password entered');
            
            const submitButton = await $('button[type="submit"]');
            await submitButton.click();
            console.log('✅ Login form submitted');
            
            await driver.pause(5000);
            console.log('🎉 Login completed');
            return true;
            
        } catch (e) {
            console.error('❌ Login failed:', e.message);
            return false;
        }
    }

    async navigateToSources(): Promise<boolean> {
        console.log('📊 Navigating to sources page...');
        
        try {
            const sourcesLink = await $('a[href="/sources"]');
            const sourcesVisible = await sourcesLink.isDisplayed();
            
            if (!sourcesVisible) {
                console.log('⚠️ Sources link not found');
                return false;
            }

            await sourcesLink.click();
            await driver.pause(3000);
            console.log('✅ Navigated to sources page');
            return true;
            
        } catch (e) {
            console.error('❌ Navigation to sources failed:', e.message);
            return false;
        }
    }

    async toggleMapillarySource(enable: boolean): Promise<boolean> {
        console.log(`🗺️ ${enable ? 'Enabling' : 'Disabling'} Mapillary source...`);
        
        try {
            const mapillaryToggle = await $('input[data-testid="source-checkbox-mapillary"]');
            const isChecked = await mapillaryToggle.isSelected();
            
            if (isChecked !== enable) {
                await mapillaryToggle.click();
                console.log(`✅ Mapillary source ${enable ? 'enabled' : 'disabled'}`);
                await driver.pause(2000);
                return true;
            } else {
                console.log(`ℹ️ Mapillary source already ${enable ? 'enabled' : 'disabled'}`);
                return true;
            }
        } catch (e) {
            console.error('❌ Failed to toggle Mapillary source:', e.message);
            return false;
        }
    }

    async checkAuthenticationState(): Promise<{needsAuth: boolean, errorText?: string}> {
        console.log('🔍 Checking authentication state...');
        
        try {
            // Look for authentication-related elements or error states
            const errorElement = await $('android=new UiSelector().textContains("error")');
            const loginPrompt = await $('android=new UiSelector().textContains("Login")');
            const signInPrompt = await $('android=new UiSelector().textContains("Sign")');
            const authPrompt = await $('android=new UiSelector().textContains("Auth")');
            
            const needsAuth = await errorElement.isDisplayed() || 
                            await loginPrompt.isDisplayed() || 
                            await signInPrompt.isDisplayed() ||
                            await authPrompt.isDisplayed();
            
            let errorText: string | undefined;
            if (await errorElement.isDisplayed()) {
                errorText = await errorElement.getText();
                console.log(`📍 Error state detected: "${errorText}"`);
            }
            
            if (needsAuth) {
                console.log('ℹ️ App indicates authentication is required');
            } else {
                console.log('✅ App appears to be authenticated');
            }
            
            return { needsAuth, errorText };
            
        } catch (error) {
            console.error('❌ Failed to check authentication state:', error.message);
            return { needsAuth: false };
        }
    }
}