/**
 * Shared UI flow for exercising the photo upload worker (capture a pending photo,
 * enable auto-upload). Used by specs that need the native upload worker to run —
 * e.g. to drive a token refresh on a 401 (relogin-notification, native-expiry).
 */
import { browser } from '@wdio/globals';
import {
    acceptPermissionDialogIfPresent,
    byTestId,
    ensureWebViewContext,
    openMenu,
    TESTID,
} from './selectors';

export async function openSettings(): Promise<void> {
    await openMenu();
    await browser.pause(800);
    const link = await byTestId(TESTID.settingsMenuLink);
    await link.waitForDisplayed({ timeout: 5000 });
    await link.click();
    await browser.pause(2000);
    await ensureWebViewContext();
}

export async function enableAutoUpload(): Promise<void> {
    await openSettings();
    const license = await byTestId(TESTID.licenseCheckbox);
    await license.waitForDisplayed({ timeout: 10000 });
    if (!(await license.isSelected())) {
        await license.click();
        await browser.pause(500);
    }
    const radio = await byTestId(TESTID.autoUploadEnabled);
    await radio.waitForDisplayed({ timeout: 5000 });
    await radio.click();
    await browser.pause(800);
    const wifi = await byTestId(TESTID.wifiOnlyCheckbox);
    await wifi.waitForDisplayed({ timeout: 5000 });
    if (await wifi.isSelected()) {
        await wifi.click();
        await browser.pause(500);
    }
    await browser.back();
    await browser.pause(1500);
}

export async function captureOnePhoto(permissionsGranted: boolean): Promise<void> {
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
    await browser.pause(2000);
}
