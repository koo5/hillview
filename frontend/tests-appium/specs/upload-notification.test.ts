/**
 * Coverage for the photo-upload foreground-like notification.
 *
 * There's a `PhotoUploadForegroundService` class in the tree that's NOT
 * registered in AndroidManifest and isn't used in production. The live
 * path is `PhotoUploadWorker` (CoroutineWorker), whose getForegroundInfo
 * returns a notification titled "Uploading Photos" (PhotoUploadWorker.kt).
 * With PhotoUploadManager.startAutomaticUpload now calling setExpedited,
 * WorkManager wires that notification in while the worker drains the
 * pending queue.
 *
 * The test deliberately builds up a large queue before triggering
 * uploads — with only one photo, the worker runs too briefly for
 * the notification poll to catch it reliably. By capturing N photos
 * while offline, then flipping network back on, we get a long
 * single worker run (setOngoing notification stays up for the whole
 * queue drain) and a wide window to observe it.
 */

import { browser } from '@wdio/globals';
import {
    acceptPermissionDialogIfPresent,
    byTestId,
    ensureNativeContext,
    ensureWebViewContext,
    openMenu,
    TESTID,
} from '../helpers/selectors';
import { recreateTestUsers, loginAsTestUser, setBackendDelay } from '../helpers/backend';

const APP_PACKAGE = 'cz.hillviedev';

async function openSettings(): Promise<void> {
    await openMenu();
    await browser.pause(800);
    const link = await byTestId(TESTID.settingsMenuLink);
    await link.waitForDisplayed({ timeout: 5000 });
    await link.click();
    await browser.pause(2000);
    await ensureWebViewContext();
}

async function setLicense(checked: boolean): Promise<void> {
    const license = await byTestId(TESTID.licenseCheckbox);
    await license.waitForDisplayed({ timeout: 10000 });
    if ((await license.isSelected()) !== checked) {
        await license.click();
        await browser.pause(500);
    }
}

async function setWifiOnly(on: boolean): Promise<void> {
    const wifi = await byTestId(TESTID.wifiOnlyCheckbox);
    await wifi.waitForDisplayed({ timeout: 5000 });
    if ((await wifi.isSelected()) !== on) {
        await wifi.click();
        await browser.pause(500);
    }
}

async function setAutoUpload(on: boolean): Promise<void> {
    await openSettings();
    await setLicense(true);
    const radio = await byTestId(
        on ? TESTID.autoUploadEnabled : TESTID.autoUploadDisabledNever,
    );
    await radio.waitForDisplayed({ timeout: 5000 });
    await radio.click();
    await browser.pause(800);
    if (on) {
        // Don't let WorkManager's UNMETERED constraint (wifi-only=true by
        // default) park the worker — we want a deterministic start.
        await setWifiOnly(false);
    }
    await browser.back();
    await browser.pause(1500);
}

let permissionsGranted = false;

/**
 * Open camera, handle first-open permissions, press single-capture N
 * times as fast as the click command allows, then close. Mirrors
 * photo-workflow.test.ts's known-good permission flow.
 */
async function captureNPhotos(n: number): Promise<void> {
    const cameraBtn = await byTestId(TESTID.cameraButton);
    await cameraBtn.waitForDisplayed({ timeout: 10000 });
    await cameraBtn.click();
    await browser.pause(1000);

    if (!permissionsGranted) {
        await acceptPermissionDialogIfPresent();
        await browser.pause(1000);
        const allowCameraBtn = await byTestId(TESTID.allowCameraBtn);
        await allowCameraBtn.waitForExist({ timeout: 10000 });
        await allowCameraBtn.click();
        await browser.pause(1000);
        await acceptPermissionDialogIfPresent();
        await browser.pause(2000);
        permissionsGranted = true;
    } else {
        await browser.pause(2000);
    }

    const capture = await byTestId('single-capture-button');
    await capture.waitForExist({ timeout: 10000 });

    for (let i = 0; i < n; i++) {
        await capture.click();
    }

    // Let the webview capture queue settle the burst before navigating
    // away; closing the camera mid-processing can interrupt saves.
    await browser.pause(1000);

    await cameraBtn.click();
    await browser.pause(1000);
}

/**
 * Open the notification shade and check for the "Uploading Photos"
 * title. Returns true if found. Leaves the shade open on success so
 * the caller can screenshot or close at its discretion.
 */
async function notificationShadeContainsUploadTitle(): Promise<boolean> {
    try {
        await (driver as any).execute('mobile: openNotifications');
        await browser.pause(500);
        await ensureNativeContext();
        const notif = await $(`android=new UiSelector().textContains("Uploading Photos")`);
        return await notif.isDisplayed();
    } catch {
        return false;
    }
}

async function closeNotificationShade(): Promise<void> {
    try {
        await driver.back();
        await browser.pause(300);
    } catch {
        // no-op — best effort
    }
}

describe('Upload foreground notification', function () {
    // Override the default 60s mocha timeout for the whole suite — captures
    // plus throttled uploads plus notification polling easily exceed it.
    this.timeout(300000);

    before(async () => {
        await recreateTestUsers();
        await browser.pause(3000);

        await ensureWebViewContext();
        const source = await browser.getPageSource();
        if (source.includes('error sending request')) {
            await browser.refresh();
            await browser.pause(5000);
        }

        const menu = await byTestId(TESTID.hamburgerMenu);
        await menu.waitForDisplayed({ timeout: 30000 });

        await loginAsTestUser();

        await ensureWebViewContext();
        await browser.execute(() => localStorage.setItem('mockCamera', 'true'));

        // Start with auto-upload off and the "never prompt" variant so
        // the capture-then-prompt overlay doesn't block rapid-fire clicks
        // on the capture button.
        await setAutoUpload(false);
    });

    // Step 1: just prove the rapid-fire capture → DB-insert pipeline
    // works with auto-upload disabled. Once this is green reliably, the
    // follow-on test adds the enable-auto-upload + notification-poll
    // part on top of a known-good queue setup.
    it('rapid capture of N photos lands them in the Kotlin device-photos DB', async () => {
        const beforePhotos = await countDevicePhotos();

        const N = 50;
        await captureNPhotos(N);

        let after = beforePhotos;
        const deadline = Date.now() + 30000;
        while (Date.now() < deadline && after - beforePhotos < N) {
            await browser.pause(1000);
            after = await countDevicePhotos();
        }

        console.log(`[upload-notif] device photos before=${beforePhotos} after=${after}`);
        expect(after - beforePhotos).toBeGreaterThanOrEqual(N);
    });

    // Step 2: turn auto-upload on with the queue already populated and
    // check for the ongoing "Uploading Photos" notification via
    // `dumpsys notification`. That avoids the open-shade polling race
    // entirely — the notification is queryable whether or not the shade
    // is pulled. Throttles the emulator NIC so the worker stays
    // foreground long enough for the poll to land.
    it('surfaces the ongoing upload notification while the worker drains the queue', async () => {
        // Slow the backend authorize-upload call so each photo's upload
        // takes a measurable chunk of time. Emulator `adb emu network
        // speed` doesn't throttle the 10.0.2.2 host-loopback path the
        // app uses, but a server-side sleep is unaffected by that.
        await setBackendDelay('authorize_upload', 3);
        try {
            await setAutoUpload(true);

            // scheduleUploadWorker (triggered by set_settings) enqueues
            // periodic work that fires at WorkManager's discretion — not
            // always immediately. tryUploads enqueues our expedited
            // one-time request right away, which is what carries the
            // foreground notification. Fire it so the window is
            // deterministic.
            await invokeTryUploads();

            // Navigate to /device-photos so a human-in-the-loop can watch
            // progress while the automated assertion runs. The route is
            // orthogonal to the notification check — it's just a visual
            // companion.
            await navigateToDevicePhotos();

            let found = false;
            let lastDump = '';
            const deadline = Date.now() + 90000;
            while (Date.now() < deadline && !found) {
                lastDump = await getNotificationsDump();
                found = lastDump.includes('Uploading Photos');
                if (!found) await browser.pause(1000);
            }

            if (found) {
                // Log the relevant block of dumpsys so the operator can
                // inspect the notification fields (title/text/icon/
                // foregroundServiceType) post-hoc, then hold on the
                // emulator screen for ~20s so a human can watch the
                // notification appear/update/dismiss in real time.
                const block = extractUploadNotificationBlock(lastDump);
                console.log('[upload-notif] active notification dumpsys snippet:');
                for (const l of block) console.log(`[upload-notif]   ${l}`);
                console.log('[upload-notif] holding 20s for visual verification...');
                await browser.pause(20000);
            } else {
                // Nothing matched — dump cz.hillviedev / pkg= lines so we
                // can see what WAS posted vs. what we expected.
                const appLines = lastDump
                    .split('\n')
                    .filter((l) => l.includes('cz.hillviedev') || /pkg=/.test(l))
                    .slice(0, 40);
                console.log('[upload-notif] no "Uploading Photos" seen. Sample lines:');
                for (const l of appLines) console.log(`[upload-notif]   ${l}`);
            }

            expect(found).toBe(true);
        } finally {
            await setBackendDelay('authorize_upload', 0);
        }
    });
});

/**
 * Ask SystemUI whether an active notification with the "Uploading
 * Photos" title is currently posted. Uses `mobile: shell` (enabled via
 * allowInsecure:['adb_shell'] in wdio.conf.ts) — completely independent
 * of notification-shade UI state, no pull-down required.
 */
async function isUploadNotificationActive(): Promise<boolean> {
    const text = await getNotificationsDump();
    return text.includes('Uploading Photos');
}

/**
 * Pull the stanza around "Uploading Photos" out of a dumpsys dump.
 * dumpsys notification splits each NotificationRecord onto ~20-30
 * lines; this grabs from the preceding NotificationRecord header to
 * just after the title line so we get the fields that matter (icon,
 * channel, ongoing, foregroundServiceType, extras).
 */
function extractUploadNotificationBlock(dump: string): string[] {
    const lines = dump.split('\n');
    const titleIdx = lines.findIndex((l) => l.includes('Uploading Photos'));
    if (titleIdx < 0) return [];
    // Walk backward to the nearest NotificationRecord / sbn= line, cap
    // ~40 lines so we don't spew the whole dump.
    let start = titleIdx;
    for (let i = titleIdx; i >= Math.max(0, titleIdx - 40); i--) {
        if (/NotificationRecord|sbn=|pkg=cz\.hillviedev/.test(lines[i])) {
            start = i;
            break;
        }
    }
    const end = Math.min(lines.length, titleIdx + 12);
    return lines.slice(start, end).map((l) => l.replace(/\s+$/, ''));
}

/** Dump raw dumpsys notification output. Used by the check + diagnostics. */
async function getNotificationsDump(): Promise<string> {
    const out = (await (driver as any).execute('mobile: shell', {
        command: 'dumpsys',
        args: ['notification', '--noredact'],
        includeStderr: true,
    })) as string | { stdout: string };
    return typeof out === 'string' ? out : out?.stdout ?? '';
}

/**
 * Force-start an expedited upload worker via PhotoUploadManager.
 * Required in addition to the UI toggle because only expedited work
 * gets WorkManager's auto-foreground wiring on Android 12+; the
 * periodic worker scheduled by set_settings doesn't reliably surface
 * the notification.
 */
async function invokeTryUploads(): Promise<void> {
    await ensureWebViewContext();
    await browser.executeAsync(`
        const done = arguments[arguments.length - 1];
        const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
        if (!invoke) { done({ __err: 'no invoke' }); return; }
        invoke('plugin:hillview|tryUploads').then(r => done(r), e => done({ __err: String(e) }));
    `);
}

/**
 * Navigate to /device-photos so progress is visible while the upload
 * drains. Orthogonal to the notification assertion — purely a
 * visual aid for watching runs. Uses the SvelteKit client router
 * via history API; Tauri WebView handles this without a full reload.
 */
async function navigateToDevicePhotos(): Promise<void> {
    await ensureWebViewContext();
    await browser.execute(() => {
        window.history.pushState({}, '', '/device-photos');
        window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await browser.pause(1500);
}

/** Query the Kotlin photo DB size via the plugin `cmd.get_device_photos`. */
async function countDevicePhotos(): Promise<number> {
    await ensureWebViewContext();
    const result = (await browser.executeAsync(`
        const done = arguments[arguments.length - 1];
        const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
        if (!invoke) { done({ __err: 'no invoke' }); return; }
        invoke('plugin:hillview|cmd', {
            command: 'get_device_photos',
            params: { page: 1, page_size: 1 }
        }).then(r => done(r), e => done({ __err: String(e) }));
    `)) as any;
    if (result?.__err) throw new Error(result.__err);
    return Number(result?.total_count ?? 0);
}
