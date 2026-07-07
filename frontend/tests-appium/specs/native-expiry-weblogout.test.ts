/**
 * E2E: native session expiry → the WebView (Svelte $auth) logs out IN LOCKSTEP.
 *
 * `relogin-notification.test.ts` proves the *native* side fires the "Login Required"
 * notification when the server rejects the refresh token. This spec asserts the
 * complementary half added this session: native clearing the session enqueues an
 * `auth-expired` message on the durable Kotlin→JS queue, the WebView's
 * KotlinMessageQueue polls it, AndroidTokenManager logs out, and the UI redirects to
 * /login — so JS and native auth state don't diverge.
 *
 * Trigger (only the native upload worker calls forceRefreshToken() on a 401, which
 * clears the session): queue a pending photo, arm server-side force-logout, run the
 * upload worker.
 *
 * Requires the dev app (cz.hillviedev) + backend at localhost:8055.
 */

import { browser } from '@wdio/globals';
import { byTestId, ensureWebViewContext, TESTID } from '../helpers/selectors';
import { recreateTestUsers, loginAsTestUser, forceLogoutUser } from '../helpers/backend';
import { captureOnePhoto } from '../helpers/uploadFlow';
import { invokePlugin } from '../helpers/bridge';
import { waitForLoggedOutUI } from '../helpers/authUi';

describe('Native session expiry logs the WebView out in lockstep', function () {
    this.timeout(240000);

    before(async () => {
        await recreateTestUsers();
        await browser.pause(3000);

        await ensureWebViewContext();
        if ((await browser.getPageSource()).includes('error sending request')) {
            await browser.refresh();
            await browser.pause(5000);
        }

        const menu = await byTestId(TESTID.hamburgerMenu);
        await menu.waitForDisplayed({ timeout: 30000 });

        await loginAsTestUser();

        // mockCamera so capture yields a real frame; keep the photo pending until
        // we've armed force-logout (don't enable auto-upload yet).
        await ensureWebViewContext();
        await browser.execute(() => localStorage.setItem('mockCamera', 'true'));
    });

    after(async () => {
        try {
            await forceLogoutUser('test', true); // clear the flag for other specs
        } catch {
            // best effort
        }
    });

    it('redirects the WebView to /login after the server invalidates the session', async () => {
        // 1. Queue a pending upload while the token is still valid.
        await captureOnePhoto(false);

        // 2. Invalidate the session server-side (access + refresh now 401).
        await forceLogoutUser('test');

        // 3. Run the upload worker → authorize-upload 401 → forceRefreshToken →
        //    /auth/refresh 401 → native clearAuthToken + queueMessage('auth-expired').
        //    Enable auto-upload via the native set_settings command, NOT the
        //    settings UI: after force-logout the WebView's own 401→forced-refresh
        //    path logs the app out to /login within seconds, yanking the settings
        //    page out from under a UI-driven toggle.
        await invokePlugin('plugin:hillview|cmd', {
            command: 'set_settings',
            params: {
                auto_upload_enabled: true,
                wifi_only: false,
                auto_upload_license: 'ccbysa4+osm',
            },
        });
        await invokePlugin('plugin:hillview|tryUploads');

        // 4. The WebView polls the queue, AndroidTokenManager logs out, and the app
        //    navigates to /login. Window covers: 150ms poll + refresh attempts + nav.
        const loggedOut = await waitForLoggedOutUI(30000);
        expect(loggedOut).toBe(true);
    });
});
