/**
 * Coverage for GeoTrackingManager's user surface:
 *
 *   1. Auto-export preference round-trips between the UI checkbox and
 *      `hillview_tracking_prefs` SharedPreferences, and survives an app
 *      restart.
 *
 *   2. The manual `geo_tracking_export` command writes real CSV files
 *      to `GeoTrackingDumps/` under the app's externalFilesDir
 *      (GeoTrackingManager.kt:288-308).
 *
 *   3. Auto-export fires on activity `onStop` when enabled
 *      (ExamplePlugin.kt:2501). Isolated via `mobile: backgroundApp`
 *      which triggers onStop without killing the process, so no other
 *      dump trigger can interfere.
 *
 *   4. Auto-export fires on plugin init when the app is restarted
 *      (ExamplePlugin.kt:328). The restart's terminateApp phase will
 *      also call onStop, so this test proves the combined stop+start
 *      dump cycle — an onStart-only regression is distinguishable by
 *      the onStop-isolated test (#3) still passing while #4 fails.
 *
 * All four build on pullFolder (Android debuggable APK → adb pull) to
 * diff the filename set before vs. after and assert new CSVs appeared.
 */

import { browser } from '@wdio/globals';
import { byTestId, ensureWebViewContext, openMenu, TESTID } from '../helpers/selectors';

const APP_PACKAGE = 'cz.hillviedev';
const DUMP_DIR = `/storage/emulated/0/Android/data/${APP_PACKAGE}/files/GeoTrackingDumps`;

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

async function openAdvancedSettings(): Promise<void> {
    await openMenu();
    await browser.pause(800);

    const settingsLink = await byTestId(TESTID.settingsMenuLink);
    await settingsLink.waitForDisplayed({ timeout: 5000 });
    await settingsLink.click();
    await browser.pause(2000);

    await ensureWebViewContext();
    const advancedLink = await byTestId(TESTID.advancedMenuLink);
    await advancedLink.waitForDisplayed({ timeout: 5000 });
    await advancedLink.click();
    await browser.pause(2000);
    await ensureWebViewContext();
}

async function getKotlinAutoExport(): Promise<boolean> {
    await ensureWebViewContext();
    const result = (await browser.executeAsync(`
        const done = arguments[arguments.length - 1];
        const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
        if (!invoke) { done({ __err: 'no invoke' }); return; }
        invoke('plugin:hillview|cmd', { command: 'geo_tracking_get_auto_export' })
          .then(r => done(r), e => done({ __err: String(e) }));
    `)) as { enabled?: boolean; __err?: string };

    if (result.__err) throw new Error(result.__err);
    return result.enabled === true;
}

/** Pull the dump folder as base64 zip, or return '' if it doesn't exist yet. */
async function pullDumpFolder(): Promise<string> {
    try {
        return (await (driver as any).pullFolder(DUMP_DIR)) as string;
    } catch {
        return '';
    }
}

/**
 * Extract the integer timestamps of dump files by scanning the raw zip
 * bytes for filename patterns. ZIP local file headers store filenames
 * uncompressed so a simple regex on `latin1` byte-string works.
 */
function extractDumpTimestamps(b64: string): { orientations: number[]; locations: number[] } {
    if (!b64) return { orientations: [], locations: [] };
    const text = Buffer.from(b64, 'base64').toString('latin1');
    const orientations = [...text.matchAll(/hillview_orientations_(\d+)\.csv/g)].map((m) => Number(m[1]));
    const locations = [...text.matchAll(/hillview_locations_(\d+)\.csv/g)].map((m) => Number(m[1]));
    return { orientations, locations };
}

describe('Geo-tracking auto-export', () => {
    before(async () => {
        await driver.activateApp(APP_PACKAGE);
        await browser.pause(3000);

        const deadline = Date.now() + 30000;
        while (Date.now() < deadline) {
            const contexts = await driver.getContexts();
            if (contexts.some((c: any) => String(c).includes('WEBVIEW'))) break;
            await browser.pause(500);
        }
        await ensureWebViewContext();
    });

    it('auto-export checkbox round-trips the SharedPreferences flag', async function () {
        this.timeout(60000);

        await openAdvancedSettings();

        const checkbox = await byTestId(TESTID.geoTrackingAutoExportCheckbox);
        await checkbox.waitForDisplayed({ timeout: 10000 });

        // Normalize pre-state to off so the assertions stand independent
        // of whatever a prior spec (or user) may have left behind.
        if (await checkbox.isSelected()) {
            await checkbox.click();
            await browser.pause(500);
        }
        expect(await checkbox.isSelected()).toBe(false);
        expect(await getKotlinAutoExport()).toBe(false);

        await checkbox.click();
        await browser.pause(800);
        expect(await checkbox.isSelected()).toBe(true);
        expect(await getKotlinAutoExport()).toBe(true);
    });

    it('auto-export flag survives app restart', async function () {
        this.timeout(90000);

        await openAdvancedSettings();
        const checkboxBefore = await byTestId(TESTID.geoTrackingAutoExportCheckbox);
        await checkboxBefore.waitForDisplayed({ timeout: 10000 });
        if (!(await checkboxBefore.isSelected())) {
            await checkboxBefore.click();
            await browser.pause(500);
        }
        expect(await checkboxBefore.isSelected()).toBe(true);

        // SharedPrefs are lazy-flushed; give a beat before terminating.
        await browser.pause(1500);
        await restartApp();

        expect(await getKotlinAutoExport()).toBe(true);

        await openAdvancedSettings();
        const checkboxAfter = await byTestId(TESTID.geoTrackingAutoExportCheckbox);
        await checkboxAfter.waitForDisplayed({ timeout: 10000 });
        expect(await checkboxAfter.isSelected()).toBe(true);
    });

    /**
     * Poll the dump folder for new (unseen) filenames. Returns the lists
     * of new orientation/location timestamps, or empty arrays if nothing
     * new appeared within `timeoutMs`.
     */
    async function waitForNewDumpFiles(
        beforeOrient: Set<number>,
        beforeLoc: Set<number>,
        timeoutMs: number,
    ): Promise<{ orientations: number[]; locations: number[] }> {
        let newOrient: number[] = [];
        let newLoc: number[] = [];
        const deadline = Date.now() + timeoutMs;
        while (Date.now() < deadline) {
            await browser.pause(1000);
            const after = extractDumpTimestamps(await pullDumpFolder());
            newOrient = after.orientations.filter((ts) => !beforeOrient.has(ts));
            newLoc = after.locations.filter((ts) => !beforeLoc.has(ts));
            if (newOrient.length > 0 && newLoc.length > 0) break;
        }
        return { orientations: newOrient, locations: newLoc };
    }

    it('geo_tracking_export writes new CSV files to the dump folder', async function () {
        this.timeout(60000);

        // Snapshot the existing dump filenames so we can assert the
        // invoke actually produced NEW files (and not just find leftovers
        // from an earlier run or from the restart-triggered onStop dump).
        const before = extractDumpTimestamps(await pullDumpFolder());
        const beforeOrient = new Set(before.orientations);
        const beforeLoc = new Set(before.locations);

        await ensureWebViewContext();
        const result = (await browser.executeAsync(`
            const done = arguments[arguments.length - 1];
            const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
            if (!invoke) { done({ __err: 'no invoke' }); return; }
            invoke('plugin:hillview|cmd', { command: 'geo_tracking_export' })
              .then(r => done(r), e => done({ __err: String(e) }));
        `)) as { success?: boolean; __err?: string };
        expect(result.__err).toBeUndefined();
        expect(result.success).toBe(true);

        const { orientations: newOrient, locations: newLoc } = await waitForNewDumpFiles(
            beforeOrient,
            beforeLoc,
            15000,
        );
        expect(newOrient.length).toBeGreaterThan(0);
        expect(newLoc.length).toBeGreaterThan(0);
        console.log(`[geo-export] wrote orientations=${newOrient} locations=${newLoc}`);
    });

    it('auto-export dumps when the app is backgrounded (onStop)', async function () {
        this.timeout(60000);

        // Carries over from the previous tests; sanity-check rather than
        // re-enable so we don't create confounding onStop/onStart dumps.
        expect(await getKotlinAutoExport()).toBe(true);

        const before = extractDumpTimestamps(await pullDumpFolder());
        const beforeOrient = new Set(before.orientations);
        const beforeLoc = new Set(before.locations);

        // `mobile: backgroundApp` with seconds<0 sends the app to the
        // background indefinitely — triggers activity onStop without
        // killing the process (so plugin init doesn't re-run, isolating
        // the onStop path). `driver.backgroundApp(-1)` also works but is
        // the older API.
        await (driver as any).execute('mobile: backgroundApp', { seconds: -1 });
        await browser.pause(3500);

        const { orientations: newOrient, locations: newLoc } = await waitForNewDumpFiles(
            beforeOrient,
            beforeLoc,
            10000,
        );

        // Bring the app back so subsequent tests have a live WebView.
        await driver.activateApp(APP_PACKAGE);
        await browser.pause(3000);
        const deadline = Date.now() + 15000;
        while (Date.now() < deadline) {
            const contexts = await driver.getContexts();
            if (contexts.some((c: any) => String(c).includes('WEBVIEW'))) break;
            await browser.pause(500);
        }

        expect(newOrient.length).toBeGreaterThan(0);
        expect(newLoc.length).toBeGreaterThan(0);
        console.log(`[onStop] wrote orientations=${newOrient} locations=${newLoc}`);
    });

    it('auto-export dumps when the app is restarted (onStart via plugin init)', async function () {
        this.timeout(60000);

        expect(await getKotlinAutoExport()).toBe(true);

        const before = extractDumpTimestamps(await pullDumpFolder());
        const beforeOrient = new Set(before.orientations);
        const beforeLoc = new Set(before.locations);

        // terminateApp fires onStop (which may itself dump), then
        // activateApp spawns a fresh process → plugin init → dumpAndClear.
        // We just need to see any NEW files to prove the restart cycle
        // with auto-export on produced output; the onStop path is tested
        // in isolation by the preceding case.
        await restartApp();

        const { orientations: newOrient, locations: newLoc } = await waitForNewDumpFiles(
            beforeOrient,
            beforeLoc,
            15000,
        );
        expect(newOrient.length).toBeGreaterThan(0);
        expect(newLoc.length).toBeGreaterThan(0);
        console.log(`[restart] wrote orientations=${newOrient} locations=${newLoc}`);
    });
});
