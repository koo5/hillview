/**
 * Coverage for the photo-upload foreground-like notification.
 *
 * There's a `PhotoUploadForegroundService` class in the tree that's NOT
 * registered in AndroidManifest and isn't used in production. The live
 * path is `PhotoUploadWorker` (CoroutineWorker) whose getForegroundInfo
 * returns a notification titled "Uploading Photos" (PhotoUploadWorker.kt:77).
 * On Android 12+ WorkManager wires that into the expedited-work
 * foreground automatically; pre-12 the worker calls setForeground()
 * directly. Either way, the user sees an ongoing "Uploading Photos"
 * entry in the notification shade while a worker is active.
 *
 * The test:
 *  1. Puts a photo in the upload queue while offline (worker parked on
 *     network constraint — no notification yet).
 *  2. Flips the emulator online and opens the notification shade in a
 *     tight poll.
 *  3. Asserts the "Uploading Photos" title appears at least once before
 *     the upload completes. setOngoing(true) means the notification
 *     persists for the worker's lifetime, so a ~500ms poll window is
 *     enough even for a quick upload.
 *
 * If expedited-work quota is exhausted (possible on repeat runs inside
 * a short window), WorkManager can silently downgrade to background
 * work with no notification; a failure here is worth investigating but
 * may reflect platform quota rather than a bug.
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
import { recreateTestUsers, loginAsTestUser } from '../helpers/backend';
import { setNetwork } from '../helpers/network';

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

async function captureOnePhoto(permissionsGranted: boolean): Promise<void> {
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
    } else {
        await browser.pause(2000);
    }

    const capture = await byTestId('single-capture-button');
    await capture.waitForExist({ timeout: 10000 });
    await capture.click();
    await browser.pause(3000);

    await cameraBtn.click();
    await browser.pause(1500);
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

describe('Upload foreground notification', () => {
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

        await enableAutoUpload();
    });

    after(async () => {
        try {
            await setNetwork(true);
        } catch {
            // ignore
        }
    });

    it('shows "Uploading Photos" notification while the worker is running', async function () {
        this.timeout(180000);

        // Queue the photo offline so the worker is parked on the
        // NetworkType constraint until we flip back online — gives us
        // a predictable moment for the notification to appear.
        await setNetwork(false);
        await captureOnePhoto(false);

        await setNetwork(true);

        // Poll the notification shade on a 600ms cadence for up to 30s.
        // Re-opening the shade each iteration is necessary because
        // pressing back to dismiss is the only way to close it between
        // polls without interfering with emulator state.
        let found = false;
        const deadline = Date.now() + 30000;
        while (Date.now() < deadline && !found) {
            found = await notificationShadeContainsUploadTitle();
            if (!found) {
                await closeNotificationShade();
                await browser.pause(600);
            }
        }

        await closeNotificationShade();

        // Return to a sane UI state for any follow-up specs.
        await driver.activateApp(APP_PACKAGE);
        await browser.pause(2000);

        expect(found).toBe(true);
    });
});
