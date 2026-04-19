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

async function closeNavMenu(): Promise<void> {
    await ensureWebViewContext();
    const backdrop = await $('[data-testid="menu-backdrop"]');
    if (await backdrop.isExisting()) {
        await backdrop.click();
        await browser.pause(500);
    }
}

function buildAuthDeepLink(token: string): string {
    const now = Date.now();
    const expiresAt = new Date(now + 60 * 60 * 1000).toISOString();
    const refreshExpiresAt = new Date(now + 7 * 24 * 60 * 60 * 1000).toISOString();
    const params = new URLSearchParams({
        token,
        expires_at: expiresAt,
        refresh_token_expires_at: refreshExpiresAt,
    });
    return `cz.hillviedev://auth?${params.toString()}`;
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

    it('logs the user in when an OAuth callback deep link arrives', async function () {
        this.timeout(120000);

        // Sanity: fresh-reset app should be unauthenticated. If this fails,
        // the noReset: false config isn't wiping session state between specs
        // and the next assertion would be meaningless.
        await openNavMenu();
        const loginLinkBefore = await $('[data-testid="nav-login-link"]');
        await loginLinkBefore.waitForDisplayed({ timeout: 10000 });
        const logoutBefore = await $('[data-testid="nav-logout-button"]');
        expect(await logoutBefore.isExisting()).toBe(false);
        await closeNavMenu();

        const token = await getTestUserToken();
        const url = buildAuthDeepLink(token);

        await (driver as any).execute('mobile: deepLink', {
            url,
            package: APP_PACKAGE,
        });

        // The plugin dispatches onOpenUrl → handleAuthCallback → completeAuthentication
        // → myGoto('/'). A 3s settle covers the state propagation before we
        // re-query the menu; the waitForDisplayed then covers slower cases.
        await browser.pause(3000);

        await openNavMenu();
        const logoutBtn = await $('[data-testid="nav-logout-button"]');
        await logoutBtn.waitForDisplayed({ timeout: 15000 });
        expect(await logoutBtn.isDisplayed()).toBe(true);

        const loginLinkAfter = await $('[data-testid="nav-login-link"]');
        expect(await loginLinkAfter.isExisting()).toBe(false);
    });

    it('rejects an expired deep-link token without logging in', async function () {
        this.timeout(60000);

        // Build a deep link whose expires_at is already in the past. The
        // handleAuthCallback expiry check (authCallback.ts:63) must reject
        // this and surface an error alert, leaving the user unauthenticated.
        const token = await getTestUserToken();
        const past = new Date(Date.now() - 60 * 1000).toISOString();
        const futureRefresh = new Date(Date.now() + 60 * 60 * 1000).toISOString();
        const params = new URLSearchParams({
            token,
            expires_at: past,
            refresh_token_expires_at: futureRefresh,
        });
        const url = `cz.hillviedev://auth?${params.toString()}`;

        await (driver as any).execute('mobile: deepLink', {
            url,
            package: APP_PACKAGE,
        });
        await browser.pause(3000);

        await openNavMenu();
        const loginLink = await $('[data-testid="nav-login-link"]');
        await loginLink.waitForDisplayed({ timeout: 10000 });
        expect(await loginLink.isDisplayed()).toBe(true);

        const logoutBtn = await $('[data-testid="nav-logout-button"]');
        expect(await logoutBtn.isExisting()).toBe(false);
    });
});
