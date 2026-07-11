/**
 * E2E: session expiry survives PROCESS DEATH — the level-triggered reconcile path.
 *
 * The edge path (queued 'auth-expired' message → WebView logout) is covered by
 * native-expiry-weblogout.test.ts. This spec proves the complementary guarantee:
 * when the queued message is LOST (process killed between the native session
 * death and delivery — the dev-server-redeploy-while-backgrounded case), the
 * persisted session-expired flag alone must surface the expiry at next launch:
 * the startup reconciler (AndroidTokenManager.reconcileSessionState) reads the
 * flag, shows the in-app "session has expired" alert, and the app is logged out.
 *
 * Determinism note: the flag is deliberately NOT cleared by clear_auth_token
 * (the lockstep logout funnels through it), so it survives no matter how much
 * of the live session's edge-path logout raced ahead before the kill.
 *
 * Requires the dev app (cz.hillviedev) + backend at localhost:8055.
 */

import { browser } from '@wdio/globals';
import { byTestId, ensureWebViewContext, TESTID } from '../helpers/selectors';
import { recreateTestUsers, loginAsTestUser, forceLogoutUser } from '../helpers/backend';
import { invokePlugin } from '../helpers/bridge';
import { isLoggedInUI } from '../helpers/authUi';

const APP_PACKAGE = 'cz.hillviedev';

describe('Session expiry reconciled across process death', function () {
    this.timeout(240000);

    before(async () => {
        await recreateTestUsers();
        await browser.pause(3000);

        await ensureWebViewContext();
        const menu = await byTestId(TESTID.hamburgerMenu);
        await menu.waitForDisplayed({ timeout: 30000 });

        await loginAsTestUser();
        expect(await isLoggedInUI()).toBe(true);
    });

    after(async () => {
        try {
            await forceLogoutUser('test', true); // clear the flag for other specs
        } catch {
            // best effort
        }
    });

    it('surfaces the expiry after kill + relaunch, from the persisted flag alone', async () => {
        // 1. Invalidate the session server-side (access + refresh now 401).
        await forceLogoutUser('test');

        // 2. Force a native refresh → 401 → sessionExpired(): tokens cleared,
        //    expired flag PERSISTED, message queued. Whether the live WebView
        //    gets to process that message before the kill below is a race — and
        //    irrelevant, because the flag survives either way.
        //    NOT refresh_auth_token: that maps to refreshTokenIfNeeded(), which
        //    no-ops while the freshly-minted access token is still locally valid
        //    and never contacts the (now-rejecting) server. get_auth_token with
        //    force goes through forceRefreshToken() → unconditional refresh → 401.
        await invokePlugin('plugin:hillview|get_auth_token', { force: true });
        await browser.pause(1000);

        // Checkpoint: the death must be persisted BEFORE the kill — that's the
        // whole premise. Probe without consuming.
        const st = (await invokePlugin('plugin:hillview|cmd', {
            command: 'get_session_state',
            params: { consume_expired: false },
        })) as { expired?: boolean };
        expect(st.expired).toBe(true);

        // 3. Kill the process: any undelivered queue message dies with it.
        //    Switch to NATIVE first — killing the app while chromedriver is
        //    bound to its WebView leaves a dead session that poisons every
        //    later element call ("not connected to DevTools"); from NATIVE,
        //    the post-relaunch context switch creates a fresh one (same
        //    pattern as geo-tracking-export's restartApp()).
        await driver.switchContext('NATIVE_APP');
        await driver.terminateApp(APP_PACKAGE);
        await browser.pause(2000);

        // 4. Relaunch. The startup reconciler must read the persisted flag.
        await driver.activateApp(APP_PACKAGE);
        await browser.pause(3000);
        const deadline = Date.now() + 15000;
        while (Date.now() < deadline) {
            const contexts = await driver.getContexts();
            if (contexts.some((c: unknown) => String(c).includes('WEBVIEW'))) break;
            await browser.pause(500);
        }
        await ensureWebViewContext();
        const menu = await byTestId(TESTID.hamburgerMenu);
        await menu.waitForDisplayed({ timeout: 30000 });

        // 5. The in-app alert is surfaced (persistent — duration 0 — so no
        //    timing window to race).
        const alertMsg = await $('.alert-message');
        await alertMsg.waitForDisplayed({ timeout: 30000 });
        expect((await alertMsg.getText()).toLowerCase()).toContain('session has expired');

        // 6. And the app is logged out in lockstep with native.
        expect(await isLoggedInUI()).toBe(false);
    });
});
