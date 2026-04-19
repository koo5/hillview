import { browser } from '@wdio/globals';
import { byTestId, ensureWebViewContext, TESTID, acceptPermissionDialogIfPresent } from '../helpers/selectors';
import { recreateTestUsers } from '../helpers/backend';
import { emuGeoFix, linearPath, streamWaypoints } from '../helpers/location';

/**
 * End-to-end smoke for the car-mode gps-kalman port.
 *
 * Drives the emulator's location via `adb emu geo fix` (with velocity) and
 * asserts that the frontend's bearing indicator updates — which only happens
 * if Kotlin's HeadingFilter, mount-offset composition, gps-kalman-bearing
 * event, and the frontend listener all work together.
 */
describe('Car mode — gps-kalman heading', () => {

    before(async () => {
        await recreateTestUsers();
        await browser.pause(3000);
        await acceptPermissionDialogIfPresent(3000);
        // Seed a starting location well before any streaming so the app's
        // first GPS fix doesn't trigger the filter's "first position = anchor"
        // path mid-test.
        emuGeoFix(50.0755, 14.4378, { speedMps: 0 });
    });

    it('selects car mode via long-press menu and tracks a moving GPS heading', async () => {
        // 1. Long-press the compass button to open the mode menu.
        const compassBtn = await byTestId(TESTID.compassButton);
        await compassBtn.waitForDisplayed({ timeout: 10000 });

        // Dispatch synthetic pointerdown / wait > LONG_PRESS_DURATION(500) / pointerup via JS
        // in the WebView. Avoids having to map WebView element coords to native pointer.
        await ensureWebViewContext();
        await browser.execute(() => {
            const el = document.querySelector('[data-testid="compass-button"]') as HTMLElement | null;
            if (!el) throw new Error('compass-button not found in WebView DOM');
            const r = el.getBoundingClientRect();
            const cx = r.left + r.width / 2;
            const cy = r.top + r.height / 2;
            el.dispatchEvent(new PointerEvent('pointerdown', {
                pointerId: 1, bubbles: true, button: 0, clientX: cx, clientY: cy, pointerType: 'touch',
            }));
        });
        await browser.pause(700); // > LONG_PRESS_DURATION
        await browser.execute(() => {
            const el = document.querySelector('[data-testid="compass-button"]') as HTMLElement | null;
            if (!el) throw new Error('compass-button not found in WebView DOM');
            el.dispatchEvent(new PointerEvent('pointerup', {
                pointerId: 1, bubbles: true, button: 0, pointerType: 'touch',
            }));
        });

        // 2. Menu should be open — pick car mode. selectBearingMode() inside
        // bearingTracking.ts turns gps orientation ON as a side effect.
        const carOption = await byTestId(TESTID.carModeOption);
        await carOption.waitForDisplayed({ timeout: 5000 });
        await carOption.click();

        // Grant location permission if the runtime dialog appears now.
        await acceptPermissionDialogIfPresent(3000);
        await ensureWebViewContext();

        // 3. Capture the bearing before streaming any movement.
        const arrow = await byTestId(TESTID.bearingArrowHitarea);
        await arrow.waitForExist({ timeout: 10000 });
        const bearingBefore = parseFloat(await arrow.getAttribute('aria-valuenow') ?? 'NaN');

        // 4. Stream an eastbound path — filter needs speed >1.5 m/s and
        // positions >10 m apart. These are well above both gates.
        const path = linearPath({
            startLat: 50.0755, startLng: 14.4378,
            headingDeg: 90, stepMeters: 25, steps: 8, speedMps: 8,
        });
        await streamWaypoints(path, { intervalMs: 1200 });

        // Give the final gps-kalman-bearing event time to propagate.
        await browser.pause(1500);

        // 5. Re-read bearing. We expect movement toward ~90°.
        const bearingAfter = parseFloat(await arrow.getAttribute('aria-valuenow') ?? 'NaN');

        // Shortest angular distance to east (90°).
        const distToEast = Math.abs(((bearingAfter - 90 + 540) % 360) - 180);

        console.log(`[car-mode] bearing before=${bearingBefore}° after=${bearingAfter}° |dist-to-east|=${distToEast.toFixed(1)}°`);

        // Loose bounds — FusedLocation mixes in its own smoothing, so exact
        // convergence isn't guaranteed, but the indicator must have moved
        // AND be somewhere in the eastern hemisphere.
        if (Number.isFinite(bearingBefore) && Number.isFinite(bearingAfter)) {
            if (bearingBefore === bearingAfter) {
                throw new Error(`Bearing did not change after streaming: stayed at ${bearingAfter}°`);
            }
        }
        if (!(distToEast < 45)) {
            throw new Error(`Bearing ${bearingAfter}° is more than 45° from east (dist=${distToEast.toFixed(1)}°)`);
        }
    });
});
