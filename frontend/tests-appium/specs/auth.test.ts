import { browser } from '@wdio/globals';
import { byTestId, ensureWebViewContext, TESTID } from '../helpers/selectors';
import { recreateTestUsers, loginAsTestUser, logout } from '../helpers/backend';

describe('Authentication', () => {

    before(async () => {
        await recreateTestUsers();
        await browser.pause(3000);
    });

    it('should show login link in menu when not authenticated', async () => {
        const menuBtn = await byTestId(TESTID.hamburgerMenu);
        await menuBtn.waitForDisplayed({ timeout: 10000 });
        await menuBtn.click();
        await browser.pause(1000);

        await ensureWebViewContext();
        const loginLink = await $('a[href="/login"]');
        expect(await loginLink.isDisplayed()).toBe(true);

        // Close menu
        const menuBtn2 = await byTestId(TESTID.hamburgerMenu);
        await menuBtn2.click();
        await browser.pause(500);
    });

    it('should login with test credentials', async () => {
        await loginAsTestUser();

        // Verify we're back on the main page and logged in
        const menuBtn = await byTestId(TESTID.hamburgerMenu);
        await menuBtn.waitForDisplayed({ timeout: 10000 });
        await menuBtn.click();
        await browser.pause(1000);

        // Should see Logout button instead of Login link
        await ensureWebViewContext();
        const logoutBtn = await $('button*=Logout');
        expect(await logoutBtn.isDisplayed()).toBe(true);

        // Close menu
        const menuBtn2 = await byTestId(TESTID.hamburgerMenu);
        await menuBtn2.click();
        await browser.pause(500);
    });

    it('should logout successfully', async () => {
        await logout();

        // After logout, app redirects to /login page
        // Verify we're on the login page by checking for the login form
        await ensureWebViewContext();
        const usernameInput = await $('input#username');
        await usernameInput.waitForDisplayed({ timeout: 10000 });
        expect(await usernameInput.isDisplayed()).toBe(true);
    });
});
