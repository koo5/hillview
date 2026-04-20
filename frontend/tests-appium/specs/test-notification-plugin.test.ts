/**
 * Coverage for the `plugin:hillview|test_show_notification` plugin
 * command. This is what the NotificationSettings "Send Test
 * Notification" button (only visible in debug mode) invokes — the
 * simplest sanity check that the app can deliver a system notification
 * at all. Unlike the foreground-upload and auth-expired notifications
 * it has no surrounding business logic, so a failure here points
 * squarely at notification plumbing (channel, permission,
 * NotificationHelper.showNotification).
 *
 * Verifies via `dumpsys notification` that a notification with the
 * requested title + body actually got posted.
 */

import { browser } from '@wdio/globals';
import { byTestId, ensureWebViewContext, TESTID } from '../helpers/selectors';

const APP_PACKAGE = 'cz.hillviedev';
const TEST_TITLE = 'Hillview Test Notif';
const TEST_MESSAGE = 'dumpsys should see this text';

async function invokeTestShowNotification(title: string, message: string): Promise<void> {
    await ensureWebViewContext();
    const result = (await browser.executeAsync(
        `
        const done = arguments[arguments.length - 1];
        const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
        if (!invoke) { done({ __err: 'no invoke' }); return; }
        invoke('plugin:hillview|test_show_notification', { title: arguments[0], message: arguments[1] })
          .then(r => done(r), e => done({ __err: String(e) }));
        `,
        title,
        message,
    )) as { success?: boolean; message?: string; __err?: string };
    if (result.__err) throw new Error(result.__err);
    expect(result.success).toBe(true);
}

async function getNotificationsDump(): Promise<string> {
    const out = (await (driver as any).execute('mobile: shell', {
        command: 'dumpsys',
        args: ['notification', '--noredact'],
        includeStderr: true,
    })) as string | { stdout: string };
    return typeof out === 'string' ? out : out?.stdout ?? '';
}

async function cancelNotification(id: number): Promise<void> {
    try {
        await (driver as any).execute('mobile: shell', {
            command: 'cmd',
            args: ['notification', 'cancel', APP_PACKAGE, String(id)],
            includeStderr: true,
        });
    } catch {
        // best effort
    }
    await browser.pause(500);
}

async function waitForNotificationTitle(title: string, timeoutMs: number): Promise<string> {
    const deadline = Date.now() + timeoutMs;
    let last = '';
    while (Date.now() < deadline) {
        last = await getNotificationsDump();
        if (last.includes(title)) return last;
        await browser.pause(500);
    }
    return last;
}

describe('test_show_notification plugin command', function () {
    this.timeout(60000);

    before(async () => {
        // Wait for the WebView and the app's initial render before
        // invoking plugin commands — activateApp isn't guaranteed to
        // have the webview context ready on cold-start.
        await driver.activateApp(APP_PACKAGE);
        await browser.pause(3000);
        const deadline = Date.now() + 30000;
        while (Date.now() < deadline) {
            const contexts = await driver.getContexts();
            if (contexts.some((c: any) => String(c).includes('WEBVIEW'))) break;
            await browser.pause(500);
        }
        await ensureWebViewContext();
        // Sanity: confirm the hamburger menu is present (app actually
        // rendered) before we start poking plugin APIs.
        const menu = await byTestId(TESTID.hamburgerMenu);
        await menu.waitForDisplayed({ timeout: 30000 });
    });

    it('posts a notification with the requested title and message', async () => {
        // Clear the well-known test-notification id so a stale one from
        // a prior run can't false-positive the dumpsys check.
        await cancelNotification(9999);

        await invokeTestShowNotification(TEST_TITLE, TEST_MESSAGE);

        const dump = await waitForNotificationTitle(TEST_TITLE, 10000);
        expect(dump).toContain(TEST_TITLE);
        expect(dump).toContain(TEST_MESSAGE);
    });
});
