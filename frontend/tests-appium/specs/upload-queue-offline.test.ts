/**
 * Coverage for the offline upload queue: photos captured without network
 * must be persisted in the Room DB queue and drained by WorkManager once
 * connectivity returns. This exercises PhotoUploadWorker's NetworkType
 * constraint (setRequiredNetworkType) plus the Kotlin enqueue path in
 * PhotoUploadManager.startAutomaticUpload — neither is reachable from the
 * web-only Playwright suite.
 */

import { browser } from '@wdio/globals';
import {
    acceptPermissionDialogIfPresent,
    byTestId,
    ensureWebViewContext,
    openMenu,
    TESTID,
} from '../helpers/selectors';
import {
    recreateTestUsers,
    loginAsTestUser,
    getTestUserToken,
    getUserPhotos,
} from '../helpers/backend';
import { setNetwork } from '../helpers/network';

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

/**
 * Enable auto-upload and disable the wifi-only gate. The wifi-only gate would
 * otherwise confound the test: the emulator's reconnected network isn't
 * guaranteed to be classified as UNMETERED, so a wifi-only worker could stay
 * parked even after NET_ONLINE. We want to assert the queue-drain behavior,
 * not the metered-network policy — there's a separate test for that.
 */
async function enableAutoUpload(): Promise<void> {
    await openSettings();
    await setLicense(true);
    const enable = await byTestId(TESTID.autoUploadEnabled);
    await enable.waitForDisplayed({ timeout: 5000 });
    await enable.click();
    await browser.pause(800);
    await setWifiOnly(false);
    await browser.back();
    await browser.pause(1500);
}

describe('Upload queue — offline resilience', () => {
    let permissionsGranted = false;

    async function openCameraAndCapture(): Promise<void> {
        const cameraBtn = await byTestId(TESTID.cameraButton);
        await cameraBtn.waitForDisplayed({ timeout: 10000 });
        await cameraBtn.click();
        await browser.pause(1000);

        if (!permissionsGranted) {
            await acceptPermissionDialogIfPresent();
            await browser.pause(1000);
            const allow = await byTestId(TESTID.allowCameraBtn);
            await allow.waitForExist({ timeout: 10000 });
            await allow.click();
            await browser.pause(1000);
            await acceptPermissionDialogIfPresent();
            await browser.pause(2000);
            permissionsGranted = true;
        } else {
            await browser.pause(2000);
        }

        const capture = await byTestId('single-capture-button');
        await capture.waitForExist({ timeout: 10000 });
        await capture.click();
        await browser.pause(3000);
    }

    async function closeCamera(): Promise<void> {
        const cameraBtn = await byTestId(TESTID.cameraButton);
        await cameraBtn.click();
        await browser.pause(2000);
    }

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

        // mockCamera keeps real-frame timestamping on so captures produce
        // unique payloads even if this spec is ever extended to multi-capture.
        await ensureWebViewContext();
        await browser.execute(() => localStorage.setItem('mockCamera', 'true'));

        await enableAutoUpload();
    });

    after(async () => {
        // Failed mid-test would otherwise leave the emulator offline for
        // subsequent specs. Safe to call on an already-online device.
        try {
            await setNetwork(true);
        } catch {
            // ignore — teardown best-effort
        }
    });

    it('queues a photo captured offline and uploads it on reconnect', async function () {
        // The capture + wait-for-upload round trip can exceed the 60s default.
        this.timeout(180000);

        const token = await getTestUserToken();

        // Sanity check: baseline is zero photos. If anything leaked through
        // from a prior spec, the final assertion wouldn't prove drain behavior.
        const baseline = await getUserPhotos(token);
        expect(baseline.count).toBe(0);

        await setNetwork(false);

        await openCameraAndCapture();
        await closeCamera();

        // While offline, the backend should still be at zero. The test runner
        // reaches localhost:8055 directly — the emulator's airplane mode only
        // blocks the app, not the runner.
        const offline = await getUserPhotos(token);
        expect(offline.count).toBe(0);

        await setNetwork(true);

        // WorkManager schedules expedited work on the next connectivity
        // callback. 90s is generous but not excessive — chromedriver
        // reconnection after context loss can itself take several seconds.
        const deadline = Date.now() + 90000;
        let photos = { count: 0, ids: [] as string[] };
        while (Date.now() < deadline) {
            photos = await getUserPhotos(token);
            if (photos.count >= 1) break;
            await browser.pause(3000);
        }

        expect(photos.count).toBeGreaterThanOrEqual(1);
    });
});
