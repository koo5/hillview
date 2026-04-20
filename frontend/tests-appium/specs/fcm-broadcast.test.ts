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

async function waitForTitle(title: string, timeoutMs: number): Promise<string> {
    const deadline = Date.now() + timeoutMs;
    let last = '';
    while (Date.now() < deadline) {
        last = await getNotificationsDump();
        if (last.includes(title)) return last;
        await browser.pause(1000);
    }
    return last;
}

/**
 * Wait for a notification whose title + `when` timestamp both satisfy
 * the predicate. `when` is posted-at time in epoch ms, parsed out of
 * dumpsys stanzas that precede our target title. Using a post-broadcast
 * cutoff lets repeat tests within a single session tell genuinely new
 * deliveries apart from stale notifications left over from prior runs.
 */
async function waitForFreshTitle(title: string, minWhenMs: number, timeoutMs: number): Promise<{ dump: string; when: number } | null> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        const dump = await getNotificationsDump();
        const lines = dump.split('\n');
        // Scan every "when=<ms>" line and check whether the adjacent
        // stanza (next ~40 lines) contains our title. The stanza layout
        // puts when= near the top of a NotificationRecord and the title
        // a few lines later inside extras.
        for (let i = 0; i < lines.length; i++) {
            const m = lines[i].match(/when=(\d+)/);
            if (!m) continue;
            const when = Number(m[1]);
            if (when < minWhenMs) continue;
            const tail = lines.slice(i, i + 50).join('\n');
            if (tail.includes(title)) {
                return { dump, when };
            }
        }
        await browser.pause(1000);
    }
    return null;
}

function extractNotificationBlock(dump: string, title: string): string[] {
    const lines = dump.split('\n');
    const idx = lines.findIndex((l) => l.includes(title));
    if (idx < 0) return [];
    let start = idx;
    for (let i = idx; i >= Math.max(0, idx - 40); i--) {
        if (/NotificationRecord|sbn=|pkg=cz\.hillviedev/.test(lines[i])) {
            start = i;
            break;
        }
    }
    const end = Math.min(lines.length, idx + 14);
    return lines.slice(start, end).map((l) => l.replace(/\s+$/, ''));
}

// -------------------- test --------------------

/**
 * Fire a fresh activity-broadcast and assert a notification arrives.
 * Logs every stanza carrying the expected title with its `when` and
 * notification key, so we can see what actually showed up — useful for
 * understanding how Android's auto-display vs. our in-app path differ
 * across foreground/backgrounded/terminated states.
 */
async function triggerBroadcastAndAwait(label: string): Promise<{ dump: string }> {
    const wiped = await clearNotificationsTable();
    console.log(`[fcm-broadcast] [${label}] cleared ${wiped} rows from notifications table`);

    await setBackendPushEnabled(true);
    await fireActivityBroadcast();

    const deadline = Date.now() + 90000;
    let dump = '';
    while (Date.now() < deadline) {
        dump = await getNotificationsDump();
        if (dump.includes(BROADCAST_TITLE)) break;
        await browser.pause(1000);
    }

    if (!dump.includes(BROADCAST_TITLE)) {
        throw new Error(`[${label}] no "${BROADCAST_TITLE}" notification in 90s`);
    }

    // Enumerate every matching stanza so we can tell duplicates apart.
    const lines = dump.split('\n');
    const hits: { when?: number; key?: string }[] = [];
    let current: { when?: number; key?: string } = {};
    for (const line of lines) {
        const whenMatch = line.match(/when=(\d+)/);
        if (whenMatch) current.when = Number(whenMatch[1]);
        const keyMatch = line.match(/\bkey=(\S+)/);
        if (keyMatch) current.key = keyMatch[1];
        if (line.includes(BROADCAST_TITLE)) {
            hits.push({ ...current });
            current = {};
        }
    }
    console.log(`[fcm-broadcast] [${label}] found ${hits.length} notification(s) with title`);
    for (const h of hits) {
        console.log(`[fcm-broadcast] [${label}]   when=${h.when ?? '?'} key=${h.key ?? '?'}`);
    }

    return { dump };
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

    it('delivers to the foregrounded app', async () => {
        const { dump } = await triggerBroadcastAndAwait('foreground');
        const block = extractNotificationBlock(dump, BROADCAST_TITLE);
        console.log('[fcm-broadcast] [foreground] snippet:');
        for (const line of block) console.log(`[fcm-broadcast]   ${line}`);
    });

    it('delivers to the backgrounded app (process alive, activity stopped)', async () => {
        // seconds<0 → stay in background indefinitely. Runs onPause/onStop
        // but leaves the process (and FirebaseMessagingService) alive.
        await (driver as any).execute('mobile: backgroundApp', { seconds: -1 });
        await browser.pause(2000);

        try {
            await triggerBroadcastAndAwait('backgrounded');
        } finally {
            await driver.activateApp(APP_PACKAGE);
            await browser.pause(2000);
            await waitForWebViewContext();
        }
    });

    it('delivers to the terminated app (process killed, FCM service restarts)', async () => {
        // Real "user swiped from recents" path: process killed outright.
        // Android spawns a fresh process hosting FirebaseMessagingService
        // when the FCM message arrives, which then posts the notification.
        await driver.switchContext('NATIVE_APP');
        await driver.terminateApp(APP_PACKAGE);
        await browser.pause(2000);

        try {
            await triggerBroadcastAndAwait('terminated');
        } finally {
            await driver.activateApp(APP_PACKAGE);
            await browser.pause(3000);
            await waitForWebViewContext();
        }
    });
});
