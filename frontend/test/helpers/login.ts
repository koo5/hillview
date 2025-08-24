import { $ } from '@wdio/globals';
import { checkForCriticalErrors } from './app-launcher';

/**
 * Shared login utilities for Appium tests
 */
export class LoginHelper {
    static readonly DEFAULT_CREDENTIALS = {
        username: 'test',
        password: 'test123'
    };

    // Use the Android-specific backend URL from environment
    static readonly DEFAULT_BASE_URL = process.env.VITE_BACKEND_ANDROID || 'http://10.0.2.2:8055';

    /**
     * Switch to WebView context for web-based interactions
     */
    static async switchToWebView(): Promise<boolean> {
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

    /**
     * Switch back to native Android context
     */
    static async switchToNativeApp(): Promise<void> {
        console.log('📱 Switching back to native context...');
        await driver.switchContext('NATIVE_APP');
        console.log('✅ Switched to native context');
    }

    /**
     * Open the hamburger menu
     */
    static async openMenu(): Promise<void> {
        console.log('🍔 Opening hamburger menu...');
        const hamburgerMenu = await $('android=new UiSelector().text("Toggle menu")');
        await hamburgerMenu.waitForDisplayed({ timeout: 10000 });
        await hamburgerMenu.click();
        await driver.pause(2000);
        console.log('✅ Menu opened');
    }

    /**
     * Close the hamburger menu
     */
    static async closeMenu(): Promise<void> {
        console.log('↩️ Closing menu...');
        await driver.back();
        await driver.pause(2000);
        console.log('✅ Menu closed');
    }

    /**
     * Perform login in WebView context
     */
    static async performLoginInWebView(
        username: string = LoginHelper.DEFAULT_CREDENTIALS.username,
        password: string = LoginHelper.DEFAULT_CREDENTIALS.password
    ): Promise<boolean> {
        console.log('🔐 Performing login in WebView...');
        
        try {
            // Check if already logged in
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

    /**
     * Complete login workflow: open menu, switch to WebView, login, switch back, close menu
     */
    static async performCompleteLogin(
        username: string = LoginHelper.DEFAULT_CREDENTIALS.username,
        password: string = LoginHelper.DEFAULT_CREDENTIALS.password
    ): Promise<boolean> {
        console.log('🔐 Starting complete login workflow...');
        
        try {
            // First check for critical errors
            await checkForCriticalErrors();

            // Step 1: Open menu
            await LoginHelper.openMenu();
            
            // Step 2: Switch to WebView and login
            const webViewAvailable = await LoginHelper.switchToWebView();
            if (!webViewAvailable) {
                console.error('❌ WebView not available for login');
                return false;
            }
            
            const loginSuccess = await LoginHelper.performLoginInWebView(username, password);
            if (!loginSuccess) {
                console.error('❌ Login failed');
                return false;
            }
            
            // Step 3: Switch back to native and close menu
            await LoginHelper.switchToNativeApp();
            await LoginHelper.closeMenu();
            
            console.log('🎉 Complete login workflow successful');
            return true;
            
        } catch (error) {
            console.error('❌ Complete login workflow failed:', error.message);
            // Take screenshot for debugging
            try {
                await driver.saveScreenshot('./test-results/login-workflow-error.png');
            } catch (e) {
                console.warn('⚠️ Could not save error screenshot');
            }
            return false;
        }
    }

    /**
     * Check if user is already authenticated by looking for profile elements
     */
    static async isUserAuthenticated(): Promise<boolean> {
        console.log('🔍 Checking authentication state...');
        
        try {
            await LoginHelper.openMenu();
            
            const webViewAvailable = await LoginHelper.switchToWebView();
            if (!webViewAvailable) {
                await LoginHelper.closeMenu();
                return false;
            }
            
            // Look for profile link (indicates logged in)
            try {
                const profileLink = await $('a[href="/profile"]');
                const isAuthenticated = await profileLink.isDisplayed();
                
                await LoginHelper.switchToNativeApp();
                await LoginHelper.closeMenu();
                
                console.log(`🔍 User is ${isAuthenticated ? 'authenticated' : 'not authenticated'}`);
                return isAuthenticated;
            } catch (e) {
                await LoginHelper.switchToNativeApp();
                await LoginHelper.closeMenu();
                return false;
            }
            
        } catch (error) {
            console.error('❌ Failed to check authentication state:', error.message);
            return false;
        }
    }

    /**
     * Login only if not already authenticated
     */
    static async ensureAuthenticated(
        username: string = LoginHelper.DEFAULT_CREDENTIALS.username,
        password: string = LoginHelper.DEFAULT_CREDENTIALS.password
    ): Promise<boolean> {
        console.log('🔐 Ensuring user is authenticated...');
        
        const isAuthenticated = await LoginHelper.isUserAuthenticated();
        if (isAuthenticated) {
            console.log('✅ User already authenticated');
            return true;
        }
        
        console.log('🔑 User not authenticated, performing login...');
        return await LoginHelper.performCompleteLogin(username, password);
    }

    /**
     * API-based login using HTTP requests (for tests that need tokens)
     */
    static async loginViaApi(
        username: string = LoginHelper.DEFAULT_CREDENTIALS.username,
        password: string = LoginHelper.DEFAULT_CREDENTIALS.password,
        baseUrl: string = LoginHelper.DEFAULT_BASE_URL
    ): Promise<string | null> {
        try {
            console.log('🌐 Logging in via API...');
            const bodyParams = `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`;
            
            const response = await driver.executeAsync((url, bodyParams, done) => {
                const xhr = new XMLHttpRequest();
                xhr.open('POST', url);
                xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                
                xhr.onload = function() {
                    try {
                        const response = {
                            status: xhr.status,
                            ok: xhr.status >= 200 && xhr.status < 300,
                            json: function() {
                                try {
                                    return JSON.parse(xhr.responseText);
                                } catch (e) {
                                    return null;
                                }
                            }
                        };
                        done(response);
                    } catch (e) {
                        done({ error: e.message });
                    }
                };
                
                xhr.onerror = function() {
                    done({ error: 'Network error' });
                };
                
                xhr.send(bodyParams);
            }, `${baseUrl}/api/auth/token`, bodyParams);

            if (response && response.ok) {
                const result = response.json();
                console.log('✅ API login successful');
                return result?.access_token || null;
            } else {
                console.warn('⚠️ API login failed:', response?.status || 'unknown error');
                return null;
            }
        } catch (error) {
            console.warn('❌ API login error:', error);
            return null;
        }
    }
}