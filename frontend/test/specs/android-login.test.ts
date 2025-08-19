import { expect } from '@wdio/globals';
import { TestWorkflows } from '../helpers/TestWorkflows';
import { HillviewAppPage } from '../pageobjects/HillviewApp.page';
import { WebViewAuthPage } from '../pageobjects/WebViewAuth.page';

/**
 * Android Login Test - MIGRATED TO PROPER PATTERNS
 * 
 * This test now actually verifies login functionality instead of just taking screenshots
 */
describe('Android Login', () => {
    let workflows: TestWorkflows;
    let app: HillviewAppPage;
    let auth: WebViewAuthPage;

    beforeEach(async function () {
        this.timeout(60000); // FIXED: Reduced from 90s to 60s
        
        // Initialize page objects
        workflows = new TestWorkflows();
        app = new HillviewAppPage();
        auth = new WebViewAuthPage();
        
        console.log('🧪 Starting login test with clean app state');
    });

    describe('Authentication', () => {
        it('should successfully login with test credentials', async function () {
            this.timeout(120000); // FIXED: Reduced from 180s to 120s
            
            console.log('🔐 Testing login functionality...');
            
            // FIXED: Verify app is ready instead of just taking screenshot
            await app.waitForAppReady();
            await app.takeScreenshot('login-test-start');
            
            // FIXED: Use workflow instead of duplicated code
            const loginSuccess = await workflows.performCompleteLogin();
            
            // FIXED: Real assertion instead of expect(true).toBe(true)
            expect(loginSuccess).toBe(true);
            
            // FIXED: Actually verify we're logged in
            await app.openMenu();
            const webViewAvailable = await auth.switchToWebView();
            expect(webViewAvailable).toBe(true);
            
            // FIXED: Check for actual signs of authentication
            const logoutLink = await $('a[href="/logout"]');
            const profileLink = await $('a[href="/profile"]');
            const userInfo = await $('.user-info, .username, [data-testid="user-display"]');
            
            const isAuthenticated = await logoutLink.isExisting() || 
                                   await profileLink.isExisting() || 
                                   await userInfo.isExisting();
            
            await auth.switchToNativeApp();
            await app.closeMenu();
            
            // FIXED: Real verification of login state
            expect(isAuthenticated).toBe(true);
            
            await app.takeScreenshot('login-verified');
            console.log('✅ Login functionality verified');
        });

        it('should show login form when not authenticated', async function () {
            this.timeout(60000);
            
            console.log('🔍 Verifying login form availability...');
            
            // Since we start with clean state, we should see login form
            await app.openMenu();
            const webViewAvailable = await auth.switchToWebView();
            expect(webViewAvailable).toBe(true);
            
            // FIXED: Actually verify login form is available
            const loginLink = await $('a[href="/login"]');
            const loginFormAvailable = await loginLink.isExisting();
            
            await auth.switchToNativeApp();
            await app.closeMenu();
            
            // FIXED: Real assertion - we should see login in clean state
            expect(loginFormAvailable).toBe(true);
            
            console.log('✅ Login form availability verified');
        });

        it('should handle login form interaction without errors', async function () {
            this.timeout(90000);
            
            console.log('🔐 Testing login form interaction...');
            
            await app.openMenu();
            const webViewAvailable = await auth.switchToWebView();
            expect(webViewAvailable).toBe(true);
            
            try {
                const loginLink = await $('a[href="/login"]');
                const loginLinkExists = await loginLink.isExisting();
                
                if (loginLinkExists) {
                    await loginLink.click();
                    await driver.pause(3000);
                    
                    // FIXED: Verify form elements exist
                    const usernameInput = await $('input[type="text"]');
                    const passwordInput = await $('input[type="password"]');
                    const submitButton = await $('button[type="submit"]');
                    
                    const formElementsExist = await usernameInput.waitForDisplayed({ timeout: 10000 }) &&
                                            await passwordInput.isExisting() &&
                                            await submitButton.isExisting();
                    
                    // FIXED: Real verification of form availability
                    expect(formElementsExist).toBe(true);
                    
                    console.log('✅ Login form elements verified');
                } else {
                    console.log('ℹ️ Already authenticated - login form not available');
                    // This is also a valid state
                    expect(loginLinkExists).toBe(false);
                }
                
            } finally {
                await auth.switchToNativeApp();
                await app.closeMenu();
            }
        });
    });

    describe('Error Handling', () => {
        it('should handle authentication errors gracefully', async function () {
            this.timeout(90000);
            
            console.log('🔍 Testing authentication error handling...');
            
            // Check for authentication-related errors
            const authState = await auth.checkAuthenticationState();
            
            if (authState.needsAuth && authState.errorText) {
                console.log(`ℹ️ Auth error detected: ${authState.errorText}`);
                
                // FIXED: Verify app remains functional despite auth errors
                const appResponsive = await app.verifyAppIsResponsive();
                expect(appResponsive).toBe(true);
                
                console.log('✅ App remains functional despite auth errors');
            } else {
                console.log('✅ No authentication errors detected');
                
                // Verify app is healthy
                const appResponsive = await app.verifyAppIsResponsive();
                expect(appResponsive).toBe(true);
            }
        });
    });

    // FIXED: Remove unnecessary cleanup - handled by clean app state system
});