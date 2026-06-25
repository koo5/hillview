/**
 * Shared auth-state UI assertions for Appium specs.
 */
import { browser } from '@wdio/globals';
import { byTestId, ensureWebViewContext, openMenu, TESTID } from './selectors';

/** Logged in ⟺ the menu shows a Logout button (and we're not on /login). */
export async function isLoggedInUI(): Promise<boolean> {
    await openMenu();
    await browser.pause(800);
    await ensureWebViewContext();
    const logoutBtn = await $('button*=Logout');
    const loggedIn = await logoutBtn.isDisplayed().catch(() => false);
    const menu = await byTestId(TESTID.hamburgerMenu); // close the menu again
    await menu.click().catch(() => {});
    await browser.pause(500);
    return loggedIn;
}

/** After a lockstep logout the app navigates to /login, which shows the username field. */
export async function waitForLoggedOutUI(timeoutMs: number): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        await ensureWebViewContext();
        const usernameInput = await $('input#username');
        if (await usernameInput.isExisting().catch(() => false)) {
            if (await usernameInput.isDisplayed().catch(() => false)) return true;
        }
        await browser.pause(500);
    }
    return false;
}
