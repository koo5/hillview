import { browser } from '@wdio/globals';
import { byTestId, ensureWebViewContext, TESTID } from '../helpers/selectors';
import { recreateTestUsers, loginAsTestUser } from '../helpers/backend';

describe('App Resilience', () => {

    before(async () => {
        await recreateTestUsers();
        await browser.pause(3000);

        // Ensure the Svelte app has loaded (not stuck on a Tauri dev-server error page)
        await ensureWebViewContext();
        const source = await browser.getPageSource();
        if (source.includes('error sending request')) {
            console.log('Dev server error detected, refreshing...');
            await browser.refresh();
            await browser.pause(5000);
        }

        // Wait for app UI to be ready
        const menu = await byTestId(TESTID.hamburgerMenu);
        await menu.waitForDisplayed({ timeout: 30000 });
        await loginAsTestUser();
    });

    after(async () => {
        // Ensure portrait orientation is restored for subsequent suites
        try {
            await driver.setOrientation('PORTRAIT');
        } catch {
            // ignore if orientation change fails
        }
    });

    it('should preserve state after backgrounding', async () => {
        // Rotate bearing to create non-default state
        const ccw = await byTestId(TESTID.rotateCcw);
        await ccw.waitForDisplayed({ timeout: 10000 });
        for (let i = 0; i < 3; i++) {
            await ccw.click();
            await browser.pause(300);
        }

        // Verify authenticated before backgrounding
        const menuBtn = await byTestId(TESTID.hamburgerMenu);
        await menuBtn.click();
        await browser.pause(1000);
        await ensureWebViewContext();
        const logoutBefore = await $('button*=Logout');
        expect(await logoutBefore.isDisplayed()).toBe(true);
        // Close menu
        await (await byTestId(TESTID.hamburgerMenu)).click();
        await browser.pause(500);

        // Send app to background for 5 seconds
        await driver.background(5);
        await browser.pause(3000);

        // Verify app is responsive
        const menuAfter = await byTestId(TESTID.hamburgerMenu);
        await menuAfter.waitForDisplayed({ timeout: 15000 });

        // Verify auth preserved
        await menuAfter.click();
        await browser.pause(1000);
        await ensureWebViewContext();
        const logoutAfter = await $('button*=Logout');
        expect(await logoutAfter.isDisplayed()).toBe(true);
        await (await byTestId(TESTID.hamburgerMenu)).click();
        await browser.pause(500);

        // Verify map controls still work
        const zoomIn = await byTestId(TESTID.zoomIn);
        await zoomIn.click();
        await browser.pause(500);
    });

    it('should handle orientation changes', async () => {
        // Verify portrait baseline
        const zoomIn = await byTestId(TESTID.zoomIn);
        await zoomIn.waitForDisplayed({ timeout: 10000 });

        // Switch to landscape
        await driver.setOrientation('LANDSCAPE');
        await browser.pause(2000);

        // Verify UI still works in landscape
        await ensureWebViewContext();
        const zoomLandscape = await byTestId(TESTID.zoomIn);
        expect(await zoomLandscape.isDisplayed()).toBe(true);
        const menuLandscape = await byTestId(TESTID.hamburgerMenu);
        expect(await menuLandscape.isDisplayed()).toBe(true);

        // Switch back to portrait
        await driver.setOrientation('PORTRAIT');
        await browser.pause(2000);

        // Verify UI still works in portrait
        await ensureWebViewContext();
        const zoomPortrait = await byTestId(TESTID.zoomIn);
        expect(await zoomPortrait.isDisplayed()).toBe(true);
    });

    it('should recover from token invalidation', async () => {
        // Verify we're authenticated
        await ensureWebViewContext();
        const menuBtn = await byTestId(TESTID.hamburgerMenu);
        await menuBtn.waitForDisplayed({ timeout: 10000 });
        await menuBtn.click();
        await browser.pause(1000);
        await ensureWebViewContext();
        const logoutBtn = await $('button*=Logout');
        expect(await logoutBtn.isDisplayed()).toBe(true);
        await (await byTestId(TESTID.hamburgerMenu)).click();
        await browser.pause(500);

        // Invalidate the token by recreating test users (changes user UUIDs,
        // so the app's stored JWT now references a non-existent user)
        await recreateTestUsers();
        await browser.pause(1000);

        // Force an authenticated API call by navigating to My Photos
        await (await byTestId(TESTID.hamburgerMenu)).click();
        await browser.pause(1000);
        await ensureWebViewContext();
        const photosLink = await $('[data-testid="my-photos-link"]');
        await photosLink.waitForDisplayed({ timeout: 5000 });
        await photosLink.click();
        await browser.pause(5000);

        // The 401 → refresh fail → logout cycle should land us on the login page
        await ensureWebViewContext();
        const usernameInput = await $('input#username');
        await usernameInput.waitForDisplayed({ timeout: 15000 });
        expect(await usernameInput.isDisplayed()).toBe(true);
    });

    it('should allow re-login after forced logout', async () => {
        // We're already on the login page from the previous test.
        // loginAsTestUser() navigates via hamburger-menu (Main.svelte only),
        // but the login page uses StandardHeader with a different testid.
        // So we fill the form directly.
        await ensureWebViewContext();
        const usernameInput = await $('input#username');
        await usernameInput.waitForDisplayed({ timeout: 10000 });
        await usernameInput.setValue('test');

        const passwordInput = await $('input#password');
        await passwordInput.setValue('StrongTestPassword123!');

        const submitBtn = await $('button[type="submit"]');
        await submitBtn.click();
        await browser.pause(3000);

        // After login, we should be back on the map view with the main hamburger menu
        const menuBtn = await byTestId(TESTID.hamburgerMenu);
        await menuBtn.waitForDisplayed({ timeout: 15000 });
        await menuBtn.click();
        await browser.pause(1000);
        await ensureWebViewContext();
        const logoutBtn = await $('button*=Logout');
        expect(await logoutBtn.isDisplayed()).toBe(true);
    });
});
