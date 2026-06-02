/**
 * Regression coverage for the capture-burst upload storm.
 *
 * Background: every saved photo triggers an upload via
 * device_photos.rs -> retry_failed_uploads -> PhotoUploadManager
 * .startAutomaticUpload. Before the fix, each one enqueued its own
 * expedited *foreground* worker; a burst of N captures produced ~N
 * workers each churning SystemForegroundService on the main thread,
 * which froze the UI for minutes and could crash with
 * ForegroundServiceDidNotStartInTimeException.
 *
 * The fix (PhotoUploadManager + PhotoUploadWorker):
 *   - immediate (expedited) + durable 15s batch, both enqueueUniqueWork(KEEP),
 *     so a burst collapses to ~1 worker run instead of N;
 *   - foreground-service promotion is gated on app-BACKGROUNDED state, so a
 *     burst captured while the app is foreground promotes 0 times.
 *
 * This test drives a foreground capture burst (the app is necessarily
 * foreground while WDIO operates it) and asserts the new behavior from
 * logcat + the device-photo DB. The backgrounded-promotion path (where it
 * DOES promote and shows "Uploading N of M") can't be driven here — you
 * can't issue captures while backgrounded — so that's left to manual checks.
 *
 * Marker log lines this relies on (added alongside the fix):
 *   PhotoUploadManager:  "🢄📤 enqueue photo_upload_now|batch ..."   (per save)
 *   PhotoUploadWorker:   "Starting upload work with trigger: ..."     (per worker RUN)
 *   PhotoUploadWorker:   "promote decision: backgrounded=..."
 *   PhotoUploadWorker:   "promoted to foreground (notif 2001)"
 */

import { browser } from '@wdio/globals';
import {
    acceptPermissionDialogIfPresent,
    byTestId,
    ensureWebViewContext,
    openMenu,
    TESTID,
} from '../helpers/selectors';
import { recreateTestUsers, loginAsTestUser, setBackendDelay } from '../helpers/backend';

// -------------------- settings helpers (mirror upload-notification.test.ts) --------------------

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
        // Don't let the UNMETERED (wifi-only) constraint park the worker.
        await setWifiOnly(false);
    }
    await browser.back();
    await browser.pause(1500);
}

// -------------------- capture helper --------------------

let permissionsGranted = false;

/** Open camera, handle first-open permissions, fire single-capture N times, close. */
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

    // Let the webview capture queue settle the burst before closing.
    await browser.pause(1000);
    await cameraBtn.click();
    await browser.pause(1000);
}

// -------------------- plugin / logcat helpers --------------------

/** Kotlin photo DB size via plugin cmd.get_device_photos. */
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

async function shell(command: string, args: string[]): Promise<string> {
    const out = (await (driver as any).execute('mobile: shell', {
        command,
        args,
        includeStderr: true,
    })) as string | { stdout: string };
    return typeof out === 'string' ? out : out?.stdout ?? '';
}

/** Drop the main logcat buffer so a later read only sees the burst window. */
async function clearLogcat(): Promise<void> {
    await shell('logcat', ['-c']);
}

/** Dump the main logcat buffer since the last clear. */
async function readLogcat(): Promise<string> {
    return shell('logcat', ['-d']);
}

const count = (lines: string[], needle: string) =>
    lines.filter((l) => l.includes(needle)).length;

describe('Upload coalescing (capture burst)', function () {
    this.timeout(300000);

    const N = 20;

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

        // Order matters (per design): slow the backend authorize-upload first so
        // the immediate worker's drain spans the whole burst — then every
        // in-window save's trigger is KEEP-dropped onto that one run, which is
        // exactly the coalescing we want to observe. Enable auto-upload last so
        // captures actually trigger startAutomaticUpload.
        await setBackendDelay('authorize_upload', 3);
        await setAutoUpload(true);
    });

    after(async () => {
        await setBackendDelay('authorize_upload', 0);
    });

    it('collapses N per-capture triggers into ~1 worker run with no foreground promotion', async () => {
        const before = await countDevicePhotos();

        await clearLogcat();
        await captureNPhotos(N);

        // Wait for the saves to land in the DB (the per-save triggers fire as
        // each save completes).
        let saved = before;
        const saveDeadline = Date.now() + 60000;
        while (Date.now() < saveDeadline && saved - before < N) {
            await browser.pause(1000);
            saved = await countDevicePhotos();
        }

        // Give the immediate worker time to start + log its promote decision,
        // and the 15s batch time to be scheduled. We do NOT wait for the full
        // (deliberately throttled) upload to drain — coalescing is visible from
        // worker-RUN count well before that.
        await browser.pause(20000);

        const lines = (await readLogcat()).split('\n');
        const enqueueAttempts = count(lines, 'enqueue photo_upload'); // ~one per save
        const workerRuns = count(lines, 'Starting upload work'); // actual worker runs
        const promotions = count(lines, 'promoted to foreground');
        const bgFalse = count(lines, 'promote decision: backgrounded=false');
        const bgTrue = count(lines, 'promote decision: backgrounded=true');
        const fgsCrashes = count(lines, 'ForegroundServiceDidNotStartInTimeException');

        console.log(
            `[coalescing] captured=${N} saved=${saved - before} ` +
            `enqueueAttempts=${enqueueAttempts} workerRuns=${workerRuns} ` +
            `promotions=${promotions} bgFalse=${bgFalse} bgTrue=${bgTrue} fgsCrashes=${fgsCrashes}`,
        );

        // Correctness: every capture landed in the device DB.
        expect(saved - before).toBeGreaterThanOrEqual(N);

        // The crash class is gone.
        expect(fgsCrashes).toBe(0);

        // Foreground-gating: the app is foreground throughout, so no run promotes.
        expect(promotions).toBe(0);
        expect(bgTrue).toBe(0);

        // Sanity: the per-save trigger actually fired (test isn't vacuous)...
        expect(enqueueAttempts).toBeGreaterThan(1);
        expect(workerRuns).toBeGreaterThanOrEqual(1);
        // ...and coalescing collapsed those triggers to ~1 real run, not
        // one-per-photo. Observed: workerRuns=1 (the immediate worker holds the
        // mutex through the throttled drain, so the 15s batch is still blocked
        // at read time). Bound of 3 tolerates the batch run + periodic worker
        // showing up under timing variance while still catching a regression to
        // per-photo workers (~N).
        expect(workerRuns).toBeLessThanOrEqual(3);
        expect(workerRuns).toBeLessThan(enqueueAttempts);

        // Responsiveness proxy for "no freeze/ANR": the UI is still interactive
        // right after the burst.
        const menu = await byTestId(TESTID.hamburgerMenu);
        expect(await menu.isDisplayed()).toBe(true);
    });
});
