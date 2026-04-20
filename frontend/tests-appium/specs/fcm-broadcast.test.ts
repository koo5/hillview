/**
 * True end-to-end FCM push test.
 *
 *   1. App logs in, enables notifications, selects the FCM-direct
 *      distributor, and registers its FCM endpoint with the backend.
 *   2. We truncate the backend `notifications` table so the activity-
 *      broadcast's "skip users notified in the last 12 hours" filter
 *      has nothing to skip.
 *   3. Backend fires `/api/internal/notifications/activity-broadcast`,
 *      which calls `send_fcm_batch` via Firebase Admin SDK.
 *   4. Firebase delivers to the emulator's Play Services → the app's
 *      `FcmDirectService.onMessageReceived` → `NotificationManager`
 *      fetches from the backend and posts the system notification.
 *   5. We observe via `dumpsys notification`.
 *
 * Requires Google-APIs emulator (has Play Services), `google-services.json`
 * in the dev build, and Firebase Admin SDK credentials on the backend.
 * FCM delivery is usually <10s but can spike to 60s+ under adverse
 * network conditions — bumped timeouts accordingly.
 */

import { browser } from '@wdio/globals';
import { byTestId, ensureWebViewContext, TESTID } from '../helpers/selectors';
import { recreateTestUsers, loginAsTestUser } from '../helpers/backend';

const APP_PACKAGE = 'cz.hillviedev';
const BACKEND_URL = 'http://localhost:8055';
const FCM_PACKAGE = 'com.google.firebase.messaging.direct';
// Hardcoded in _send_activity_broadcast_notification_impl (push_notifications.py:260-265).
const BROADCAST_TITLE = 'New photos uploaded';

// -------------------- plugin invoke wrappers --------------------

async function invokePlugin<T = unknown>(command: string, args?: Record<string, unknown>): Promise<T> {
    await ensureWebViewContext();
    const result = (await browser.executeAsync(
        `
        const done = arguments[arguments.length - 1];
        const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
        if (!invoke) { done({ __err: 'no invoke' }); return; }
        invoke(arguments[0], arguments[1] || {}).then(
            r => done(r),
            e => done({ __err: String(e) }),
        );
        `,
        command,
        args ?? {},
    )) as any;
    if (result?.__err) throw new Error(`${command}: ${result.__err}`);
    return result as T;
}

async function enableNotifications(): Promise<void> {
    const r = (await invokePlugin('plugin:hillview|set_notification_settings', { enabled: true })) as {
        success: boolean;
        error?: string;
    };
    if (!r.success) throw new Error(`set_notification_settings: ${r.error ?? 'unknown'}`);
}

async function getPushDistributors(): Promise<{ package_name: string; is_available: boolean }[]> {
    const r = (await invokePlugin('plugin:hillview|get_push_distributors')) as any;
    return r.distributors ?? [];
}

async function selectPushDistributor(packageName: string): Promise<void> {
    const r = (await invokePlugin('plugin:hillview|select_push_distributor', {
        request: { package_name: packageName },
    })) as { success: boolean; error?: string };
    if (!r.success) throw new Error(`select_push_distributor: ${r.error ?? 'unknown'}`);
}

async function getPushRegistrationStatus(): Promise<{ status: string; status_message?: string }> {
    return (await invokePlugin('plugin:hillview|get_push_registration_status')) as any;
}

// -------------------- backend helpers --------------------

async function clearNotificationsTable(): Promise<number> {
    const res = await fetch(`${BACKEND_URL}/api/internal/debug/clear-notifications`, { method: 'POST' });
    if (!res.ok) throw new Error(`clear-notifications failed (${res.status}): ${await res.text()}`);
    const body = (await res.json()) as { deleted: number };
    return body.deleted;
}

async function setBackendPushEnabled(enabled: boolean): Promise<void> {
    // Backend defaults push to OFF in DEV_MODE to avoid hammering real
    // FCM / UnifiedPush during unrelated tests. This spec explicitly
    // opts in; the toggle is auto-reset by recreate-test-users.
    const res = await fetch(`${BACKEND_URL}/api/internal/debug/push-enabled`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
    });
    if (!res.ok) throw new Error(`push-enabled failed (${res.status}): ${await res.text()}`);
}

async function fireActivityBroadcast(): Promise<void> {
    const res = await fetch(`${BACKEND_URL}/api/internal/notifications/activity-broadcast`, {
        method: 'POST',
    });
    if (!res.ok) {
        throw new Error(`activity-broadcast failed (${res.status}): ${await res.text()}`);
    }
}

// -------------------- dumpsys helpers --------------------

async function getNotificationsDump(): Promise<string> {
    const out = (await (driver as any).execute('mobile: shell', {
        command: 'dumpsys',
        args: ['notification', '--noredact'],
        includeStderr: true,
    })) as string | { stdout: string };
    return typeof out === 'string' ? out : out?.stdout ?? '';
}

// (No notification-shade pre-wipe here: `cmd notification cancel_all` isn't
//  supported on API 31, and a leftover activity-broadcast on the shade
//  can't false-positive us — the `clearNotificationsTable` step below
//  deletes the DB rows that the filter checks, and only a fresh FCM
//  delivery from the backend posts a new notification.)

// -------------------- test --------------------

/**
 * Extract the set of notification-key strings currently in dumpsys for
 * our app package. Includes both the active list and the mArchive ring
 * buffer — the emulator sends some notifications straight to archive
 * when the shade is never opened, so active-only misses them.
 */
function parseAppNotificationKeys(dump: string): string[] {
    // Key format: 0|cz.hillviedev|<id>|<tag>|<uid>
    const re = /key=(0\|cz\.hillviedev\|[^\s|]*\|[^\s|]*\|[^\s|)]+)/g;
    const out: string[] = [];
    let m: RegExpExecArray | null;
    while ((m = re.exec(dump)) !== null) out.push(m[1]);
    return out;
}

/**
 * Fire a fresh activity-broadcast and wait for at least one genuinely
 * new notification key to appear in dumpsys. "New" = a key we didn't
 * observe before firing (baseline snapshot). Cheaper and more robust
 * than parsing `when=` timestamps out of NotificationRecord stanzas,
 * because the emulator parks our notifications in mArchive (which
 * uses the shorter StatusBarNotification form without `when`) almost
 * immediately.
 */
async function triggerBroadcastAndAwait(label: string): Promise<string[]> {
    const beforeKeys = new Set(parseAppNotificationKeys(await getNotificationsDump()));
    console.log(`[fcm-broadcast] [${label}] pre-broadcast, ${beforeKeys.size} app keys in dumpsys`);

    const wiped = await clearNotificationsTable();
    console.log(`[fcm-broadcast] [${label}] cleared ${wiped} row(s) from notifications table`);

    await setBackendPushEnabled(true);
    await fireActivityBroadcast();

    const deadline = Date.now() + 120000;
    let newKeys: string[] = [];
    while (Date.now() < deadline) {
        const dump = await getNotificationsDump();
        // Contains-title check first — cheap; skip the diff if the FCM
        // delivery clearly hasn't landed yet.
        if (dump.includes(BROADCAST_TITLE)) {
            const current = parseAppNotificationKeys(dump);
            newKeys = current.filter((k) => !beforeKeys.has(k));
            if (newKeys.length > 0) break;
        }
        await browser.pause(1000);
    }

    if (newKeys.length === 0) {
        throw new Error(`[${label}] no new cz.hillviedev notification keys in 120s`);
    }

    console.log(`[fcm-broadcast] [${label}] ${newKeys.length} new key(s) after broadcast:`);
    for (const k of newKeys) {
        const slots = k.split('|');
        const src = slots[3] === 'activity' ? 'android-auto' : 'app';
        console.log(`[fcm-broadcast] [${label}]   ${k} (${src})`);
    }
    return newKeys;
}

async function waitForWebViewContext(timeoutMs = 30000): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        const contexts = await driver.getContexts();
        if (contexts.some((c: any) => String(c).includes('WEBVIEW'))) break;
        await browser.pause(500);
    }
    await ensureWebViewContext();
}

describe('Real-FCM broadcast delivery', function () {
    this.timeout(360000);

    before(async () => {
        await recreateTestUsers();
        await browser.pause(3000);

        await ensureWebViewContext();
        const src = await browser.getPageSource();
        if (src.includes('error sending request')) {
            await browser.refresh();
            await browser.pause(5000);
        }

        const menu = await byTestId(TESTID.hamburgerMenu);
        await menu.waitForDisplayed({ timeout: 30000 });

        await loginAsTestUser();

        // One-time FCM setup shared by all three delivery-state tests:
        // enable in-app notifications, pick the FCM distributor, wait
        // for the app's FCM token to register with the backend.
        await enableNotifications();

        const distributors = await getPushDistributors();
        const fcm = distributors.find((d) => d.package_name === FCM_PACKAGE);
        expect(fcm).toBeDefined();
        expect(fcm!.is_available).toBe(true);

        await selectPushDistributor(FCM_PACKAGE);

        let status: { status: string; status_message?: string } = { status: '' };
        const regDeadline = Date.now() + 60000;
        while (Date.now() < regDeadline) {
            status = await getPushRegistrationStatus();
            if (status.status === 'registered') break;
            await browser.pause(1500);
        }
        console.log(`[fcm-broadcast] registration status: ${status.status} (${status.status_message ?? ''})`);
        expect(status.status).toBe('registered');
    });

    after(async () => {
        // If we're the last spec of the run, recreate-test-users won't
        // fire again. Make sure outgoing push isn't left ON.
        try {
            await setBackendPushEnabled(false);
        } catch {
            // ignore
        }
    });

    function tagOf(key: string): string | null {
        // dumpsys prints "null" when no tag was set (e.g. notify(id, n)),
        // an empty slot when key came from StatusBarNotification,
        // or the actual string tag when notify(tag, id, n) was used.
        const t = key.split('|')[3];
        return t === '' || t === 'null' ? null : t;
    }

    it('delivers to the foregrounded app — via our in-app display path', async () => {
        const newKeys = await triggerBroadcastAndAwait('foreground');
        // Foreground: Android doesn't auto-display the `notification`
        // payload; our FcmDirectService.onMessageReceived runs and
        // NotificationManager posts an untagged notification. Expect at
        // least one key with tag=null, and NO tag="activity" auto-display.
        expect(newKeys.some((k) => tagOf(k) === null)).toBe(true);
        expect(newKeys.every((k) => tagOf(k) !== 'activity')).toBe(true);
    });

    it('delivers to the backgrounded app — Android auto-display, our code stays silent', async () => {
        // seconds<0 → stay in background indefinitely. Runs onPause/onStop
        // but leaves the process (and FirebaseMessagingService) alive.
        await (driver as any).execute('mobile: backgroundApp', { seconds: -1 });
        await browser.pause(2000);

        try {
            const newKeys = await triggerBroadcastAndAwait('backgrounded');
            // Android's auto-display tags with the FCM payload's tag
            // ("activity"). Our dedup in FcmDirectService.onMessageReceived
            // should skip the in-app display path, so we do NOT expect a
            // tag=null NotificationManager entry.
            expect(newKeys.some((k) => tagOf(k) === 'activity')).toBe(true);
            expect(newKeys.every((k) => tagOf(k) !== null)).toBe(true);
        } finally {
            await driver.activateApp(APP_PACKAGE);
            await browser.pause(2000);
            await waitForWebViewContext();
        }
    });

    it('delivers to a swiped-from-recents app (process killed via `am kill`)', async () => {
        // `am kill` drops the process without setting the package's
        // force-stopped flag — Android will still deliver broadcasts
        // (including FCM) and spawn a fresh FirebaseMessagingService.
        // That mirrors "user swiped the app off recents" on a real
        // device.
        //
        // NOT `driver.terminateApp()` / `am force-stop`: that sets
        // PackageManager's force-stopped state, after which Android
        // refuses to deliver any intent (FCM included) until the user
        // manually re-launches the app. That's a legitimate Android
        // guarantee, not something to test for delivery against — any
        // coverage of that state should assert "no notification", not
        // "notification arrives".
        await driver.switchContext('NATIVE_APP');
        await (driver as any).execute('mobile: shell', {
            command: 'am',
            args: ['kill', APP_PACKAGE],
            includeStderr: true,
        });
        await browser.pause(2000);

        try {
            const newKeys = await triggerBroadcastAndAwait('swiped-from-recents');
            // Minimum assertion: a notification got posted. The exact
            // path is different from both the foreground and the
            // backgrounded cases — when Firebase cold-starts the
            // service, it invokes `onMessageReceived` but does NOT
            // auto-display the payload (the auto-display path requires
            // the app process to already be alive when the push arrives).
            // So our `NotificationManager` ends up owning the display.
            // Accept any new cz.hillviedev key.
            expect(newKeys.length).toBeGreaterThan(0);
        } finally {
            await driver.activateApp(APP_PACKAGE);
            await browser.pause(3000);
            await waitForWebViewContext();
        }
    });
});
