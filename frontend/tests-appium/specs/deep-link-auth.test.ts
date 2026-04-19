/**
 * Coverage for the OAuth redirect deep link. The full OAuth flow lives in
 * the system browser, which we can't drive from this suite — but the tail
 * end (browser → cz.hillviedev://auth?token=…&expires_at=…) is what the
 * Tauri app actually has to handle, and it's entirely on our side. This
 * test fires that intent via `mobile: deepLink` and asserts the app
 * reaches a logged-in state, exercising:
 *
 *   - AndroidManifest intent-filter for scheme `cz.hillviedev`
 *   - Tauri v2 deep-link plugin's `onOpenUrl` dispatch into the running
 *     activity (launchMode=singleTask routes to onNewIntent)
 *   - authCallback.handleAuthCallback expiry check + completeAuthentication
 *
 * The backend JWT is real; the expires_at / refresh_token_expires_at on
 * the URL are synthesized (handleAuthCallback trusts URL-side timestamps,
 * and the server's `exp` claim is authoritative for later API calls).
 */

import { browser } from '@wdio/globals';
import { byTestId, ensureWebViewContext, TESTID } from '../helpers/selectors';
import { recreateTestUsers, getTestUserToken } from '../helpers/backend';

const APP_PACKAGE = 'cz.hillviedev';

async function openNavMenu(): Promise<void> {
    const menu = await byTestId(TESTID.hamburgerMenu);
    await menu.waitForDisplayed({ timeout: 30000 });
    await menu.click();
    await browser.pause(1000);
    await ensureWebViewContext();
}

function buildAuthDeepLink(token: string, expiresAtOverride?: string): string {
    const now = Date.now();
    const expiresAt = expiresAtOverride ?? new Date(now + 60 * 60 * 1000).toISOString();
    const refreshExpiresAt = new Date(now + 7 * 24 * 60 * 60 * 1000).toISOString();
    const params = new URLSearchParams({
        token,
        expires_at: expiresAt,
        refresh_token_expires_at: refreshExpiresAt,
    });
    return `cz.hillviedev://auth?${params.toString()}`;
}

async function fireDeepLink(url: string): Promise<void> {
    await (driver as any).execute('mobile: deepLink', {
        url,
        package: APP_PACKAGE,
    });
    // handleAuthCallback → completeAuthentication → myGoto('/'). 3s covers
    // the state propagation before we re-query the menu.
    await browser.pause(3000);
}

/**
 * Kill + relaunch the app so each test gets a fresh activity. Appium's
 * per-session noReset doesn't clear between tests, and back-to-back
 * `mobile: deepLink` calls on a single activity instance turned out to be
 * unreliable — the second intent was silently dropped by onNewIntent in
 * manual runs. Restarting sidesteps that without the overhead of a full
 * session reset.
 */
async function restartApp(): Promise<void> {
    await driver.switchContext('NATIVE_APP');
    await driver.terminateApp(APP_PACKAGE);
    await browser.pause(1000);
    await driver.activateApp(APP_PACKAGE);
    await browser.pause(3000);

    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
        const contexts = await driver.getContexts();
        if (contexts.some((c: any) => String(c).includes('WEBVIEW'))) break;
        await browser.pause(500);
    }
    await ensureWebViewContext();
}

describe('Deep-link auth', () => {
    before(async () => {
        await recreateTestUsers();
        await browser.pause(3000);

        await ensureWebViewContext();
        const source = await browser.getPageSource();
        if (source.includes('error sending request')) {
            await browser.refresh();
            await browser.pause(5000);
        }
    });

    beforeEach(async () => {
        await restartApp();
    });

    // Order matters: Appium's noReset is per-session, not per-test, so the
    // happy-path case leaves the user logged-in. Running the expired-token
    // case first exercises it against a clean unauthenticated state.

    it('rejects an expired deep-link token without logging in', async function () {
        this.timeout(60000);

        // handleAuthCallback expiry check (authCallback.ts:63) must reject
        // this and leave the user unauthenticated.
        const token = await getTestUserToken();
        const past = new Date(Date.now() - 60 * 1000).toISOString();
        const url = buildAuthDeepLink(token, past);
        await fireDeepLink(url);

        await openNavMenu();
        const loginLink = await $('[data-testid="nav-login-link"]');
        await loginLink.waitForDisplayed({ timeout: 10000 });
        expect(await loginLink.isDisplayed()).toBe(true);

        const logoutBtn = await $('[data-testid="nav-logout-button"]');
        expect(await logoutBtn.isExisting()).toBe(false);
    });

    it('logs the user in when an OAuth callback deep link arrives', async function () {
        this.timeout(120000);

        const token = await getTestUserToken();
        const url = buildAuthDeepLink(token);
        await fireDeepLink(url);

        await openNavMenu();
        const logoutBtn = await $('[data-testid="nav-logout-button"]');
        await logoutBtn.waitForDisplayed({ timeout: 15000 });
        expect(await logoutBtn.isDisplayed()).toBe(true);

        const loginLink = await $('[data-testid="nav-login-link"]');
        expect(await loginLink.isExisting()).toBe(false);
    });
});
