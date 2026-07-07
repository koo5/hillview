/**
 * Coverage for the "background location tracking" mode.
 *
 * When location tracking is ACTIVE and the user manually pans the map, the app
 * no longer just turns tracking off — it enters a third BACKGROUND state:
 *   - the location button goes half-blue (CSS class `background`),
 *   - GPS stays subscribed (pulses continue) but the map stops following it,
 *   - GPS fixes keep flowing to the locations table tagged "<provider>-background"
 *     (GeoTrackingManager.setBackgroundLogging), so they don't win the
 *     photo-location pairing (LocationDao.getLocationNearTimestamp excludes them).
 *   - clicking again turns it fully off; the next click re-arms ACTIVE.
 *
 * Four angles:
 *   1. The `set_location_logging_mode` command round-trips through Kotlin.
 *   2. The button state machine OFF → ACTIVE → BACKGROUND → OFF, where the
 *      ACTIVE→BACKGROUND edge is driven by a real swipe/pan of the map.
 *   3. A GPS fix injected while background-logging is on lands in the exported
 *      locations CSV with a `-background` source, while a foreground fix does not
 *      — proving the Kotlin label flips end-to-end (emu geo fix → FusedLocation →
 *      PreciseLocationService → storeLocationPreciseLocationData → CSV).
 *   4. Regression: entering capture mode while BACKGROUND re-arms clean foreground
 *      ACTIVE, rather than leaving the app stuck in the half-blue background state.
 */

import { browser } from '@wdio/globals';
import {
    acceptPermissionDialogIfPresent,
    byTestId,
    ensureWebViewContext,
    TESTID,
} from '../helpers/selectors';
import { emuGeoFix } from '../helpers/location';

const APP_PACKAGE = 'cz.hillviedev';
const DUMP_DIR = `/storage/emulated/0/Android/data/${APP_PACKAGE}/files/GeoTrackingDumps`;

/** Invoke a `plugin:hillview|cmd` dispatch command from inside the WebView. */
async function invokeCmd(command: string, params: Record<string, unknown> = {}): Promise<any> {
    await ensureWebViewContext();
    const res = (await browser.executeAsync(
        `
        const done = arguments[arguments.length - 1];
        const command = arguments[0];
        const params = arguments[1];
        const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
        if (!invoke) { done({ __err: 'no invoke' }); return; }
        invoke('plugin:hillview|cmd', { command, params })
          .then(r => done(r == null ? {} : r), e => done({ __err: String(e) }));
        `,
        command,
        params,
    )) as { __err?: string };
    if (res && res.__err) throw new Error(`${command}: ${res.__err}`);
    return res;
}

/** Invoke a top-level plugin command (not via the cmd dispatch). */
async function invokePlugin(fullCommand: string): Promise<any> {
    await ensureWebViewContext();
    const res = (await browser.executeAsync(
        `
        const done = arguments[arguments.length - 1];
        const fullCommand = arguments[0];
        const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
        if (!invoke) { done({ __err: 'no invoke' }); return; }
        invoke(fullCommand).then(r => done(r == null ? {} : r), e => done({ __err: String(e) }));
        `,
        fullCommand,
    )) as { __err?: string };
    if (res && res.__err) throw new Error(`${fullCommand}: ${res.__err}`);
    return res;
}

async function trackBtnClass(): Promise<string> {
    const btn = await byTestId(TESTID.trackLocation);
    await btn.waitForDisplayed({ timeout: 5000 });
    return (await btn.getAttribute('class')) || '';
}

async function clickTrackBtn(): Promise<void> {
    const btn = await byTestId(TESTID.trackLocation);
    await btn.waitForDisplayed({ timeout: 5000 });
    await btn.click();
    await browser.pause(600);
}

/**
 * Toggle the camera button (view ↔ capture). The map panel stays mounted in a
 * split layout, so the track-location button remains queryable afterwards. Any
 * camera permission dialog is accepted best-effort — the activity flips (and the
 * capture-mode reactive runs) on the click regardless of the camera itself.
 */
async function clickCameraBtn(): Promise<void> {
    const btn = await byTestId(TESTID.cameraButton);
    await btn.waitForDisplayed({ timeout: 5000 });
    await btn.click();
    await browser.pause(600);
    await acceptPermissionDialogIfPresent(2000);
    await ensureWebViewContext();
    await browser.pause(400);
}

/** A single click collapses ACTIVE or BACKGROUND back to OFF; OFF stays OFF. */
async function normalizeOff(): Promise<void> {
    const cls = await trackBtnClass();
    if (cls.includes('active') || cls.includes('background')) {
        await clickTrackBtn();
    }
    const after = await trackBtnClass();
    expect(after.includes('active')).toBe(false);
    expect(after.includes('background')).toBe(false);
}

/** Drag the map (native gesture) to simulate a manual pan. */
async function panMap(): Promise<void> {
    // Start the drag at the exact center of the MAP COMPONENT (not the screen):
    // when photos are in range the photo viewer owns the top half of the screen,
    // and the map's own buttons/attribution hug its edges. The bearing arrow is
    // parked at the map center (tracking just recentered onto the GPS fix), but
    // it only reacts around its head, so its base — the exact center — is safe
    // to grab. The rect is measured in WebView CSS px and scaled to the device
    // px that performActions expects (the WebView is edge-to-edge, so
    // device = css × (deviceWidth / innerWidth)).
    await ensureWebViewContext();
    const m = (await browser.execute(() => {
        const el = document.querySelector('[data-testid="map-container"]');
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { x: r.left + r.width / 2, y: r.top + r.height / 2, iw: window.innerWidth };
    })) as { x: number; y: number; iw: number } | null;
    if (!m) throw new Error('panMap: [data-testid="map-container"] not found');
    await driver.switchContext('NATIVE_APP');
    const { width } = await browser.getWindowSize();
    const scale = width / m.iw;
    const cx = Math.floor(m.x * scale);
    const cy = Math.floor(m.y * scale);
    await browser.performActions([
        {
            type: 'pointer',
            id: 'finger1',
            parameters: { pointerType: 'touch' },
            actions: [
                { type: 'pointerMove', duration: 0, x: cx, y: cy },
                { type: 'pointerDown', button: 0 },
                { type: 'pointerMove', duration: 400, x: cx - 240, y: cy },
                { type: 'pointerUp', button: 0 },
            ],
        },
    ]);
    await browser.pause(800);
    await ensureWebViewContext();
}

/** Newest hillview_locations_*.csv filename in the dump folder, or null. */
async function newestLocationsCsv(): Promise<string | null> {
    let b64 = '';
    try {
        b64 = (await (driver as any).pullFolder(DUMP_DIR)) as string;
    } catch {
        return null;
    }
    // ZIP local file headers store filenames uncompressed, so a regex on the
    // latin1 byte-string finds them without inflating.
    const text = Buffer.from(b64, 'base64').toString('latin1');
    const ts = [...text.matchAll(/hillview_locations_(\d+)\.csv/g)].map((m) => Number(m[1]));
    if (ts.length === 0) return null;
    return `hillview_locations_${Math.max(...ts)}.csv`;
}

/** Source column (index 3) of every data row of a pulled locations CSV. */
function csvSources(csv: string): string[] {
    return csv
        .split(/\r?\n/)
        .filter((l) => l && !l.startsWith('#'))
        .map((l) => l.split(',')[3])
        .filter((s): s is string => Boolean(s));
}

describe('Background location tracking', () => {
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
        // Give the map a position to settle on so enabling tracking doesn't error.
        emuGeoFix(50.0755, 14.4378, { speedMps: 0 });
        await browser.pause(1000);
    });

    after(async () => {
        // Don't leave background logging on for later specs.
        try {
            await invokeCmd('set_location_logging_mode', { mode: 'active' });
            await invokePlugin('plugin:hillview|stop_precise_location_listener');
        } catch {
            // best effort
        }
    });

    it('set_location_logging_mode round-trips through Kotlin', async function () {
        this.timeout(30000);
        // Both directions should resolve without error (the command returns {}).
        await invokeCmd('set_location_logging_mode', { mode: 'background' });
        await invokeCmd('set_location_logging_mode', { mode: 'active' });
    });

    it('cycles OFF → ACTIVE → BACKGROUND → OFF (pan enters background, not off)', async function () {
        this.timeout(120000);
        await ensureWebViewContext();
        await normalizeOff();

        // OFF → ACTIVE
        await clickTrackBtn();
        await acceptPermissionDialogIfPresent(); // location permission, first enable
        await ensureWebViewContext();
        await browser.pause(400);
        expect((await trackBtnClass()).includes('active')).toBe(true);

        // ACTIVE → BACKGROUND, via a manual map pan (NOT a button click).
        await panMap();
        const bg = await trackBtnClass();
        expect(bg.includes('background')).toBe(true);
        expect(bg.includes('active')).toBe(false);

        // BACKGROUND → OFF
        await clickTrackBtn();
        const off = await trackBtnClass();
        expect(off.includes('active')).toBe(false);
        expect(off.includes('background')).toBe(false);

        // OFF → ACTIVE again: the cycle is restored, not stuck.
        await clickTrackBtn();
        await browser.pause(400);
        expect((await trackBtnClass()).includes('active')).toBe(true);

        // cleanup → OFF
        await clickTrackBtn();
    });

    // Regression: entering capture mode must re-arm a clean foreground ACTIVE
    // state. The capture reactive (Main.svelte) calls enableLocationTracking(),
    // which previously only flipped locationTracking on and left
    // backgroundLocationTracking set — leaving the button stuck half-blue, GPS
    // still logging "-background", and captures recording the live fix only as
    // alt_location. enableLocationTracking() now clears the background state, so
    // BACKGROUND → enter-capture → ACTIVE.
    it('entering capture mode from BACKGROUND restores foreground ACTIVE (not stuck half-blue)', async function () {
        this.timeout(120000);
        await ensureWebViewContext();
        await normalizeOff();

        // OFF → ACTIVE
        await clickTrackBtn();
        await acceptPermissionDialogIfPresent();
        await ensureWebViewContext();
        await browser.pause(400);
        expect((await trackBtnClass()).includes('active')).toBe(true);

        // ACTIVE → BACKGROUND, via a manual map pan.
        await panMap();
        const bg = await trackBtnClass();
        expect(bg.includes('background')).toBe(true);
        expect(bg.includes('active')).toBe(false);

        // BACKGROUND → enter capture mode: must reset to clean foreground ACTIVE.
        await clickCameraBtn();
        const inCapture = await trackBtnClass();
        expect(inCapture.includes('active')).toBe(true);
        expect(inCapture.includes('background')).toBe(false);

        // cleanup: leave capture mode (→ view) and turn tracking off.
        await clickCameraBtn();
        await normalizeOff();
    });

    it('a background-mode GPS fix is logged with a -background source in the CSV', async function () {
        this.timeout(120000);

        await invokePlugin('plugin:hillview|start_precise_location_listener');
        await acceptPermissionDialogIfPresent();
        await ensureWebViewContext();
        await browser.pause(1000);

        // Foreground fixes → plain provider source.
        await invokeCmd('set_location_logging_mode', { mode: 'active' });
        emuGeoFix(50.0800, 14.4300, { speedMps: 0 });
        await browser.pause(1600);
        emuGeoFix(50.0810, 14.4310, { speedMps: 0 });
        await browser.pause(1600);

        // Background fixes → "<provider>-background" source.
        await invokeCmd('set_location_logging_mode', { mode: 'background' });
        emuGeoFix(50.0900, 14.4400, { speedMps: 0 });
        await browser.pause(1600);
        emuGeoFix(50.0910, 14.4410, { speedMps: 0 });
        await browser.pause(1600);

        // Reset the label before exporting (export reads the already-stored rows).
        await invokeCmd('set_location_logging_mode', { mode: 'active' });

        const result = await invokeCmd('geo_tracking_export');
        expect(result.success).toBe(true);
        await browser.pause(2000);

        const filename = await newestLocationsCsv();
        expect(filename).not.toBeNull();
        const b64 = (await (driver as any).pullFile(`${DUMP_DIR}/${filename}`)) as string;
        const csv = Buffer.from(b64, 'base64').toString('utf8');
        const sources = csvSources(csv);
        console.log(`[bg-tracking] CSV sources: ${JSON.stringify([...new Set(sources)])}`);

        // The background fix flipped the label; the foreground one did not.
        expect(sources.some((s) => s.includes('background'))).toBe(true);
        expect(sources.some((s) => !s.includes('background'))).toBe(true);
    });
});
