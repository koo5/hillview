/**
 * End-to-end coverage for the settings-persistence bug fixed in this branch:
 * setting auto_upload_enabled with the autoUploadLicense unchecked used to silently
 * reset auto_upload_prompt_enabled (and wifi_only) on every app restart, because
 * the frontend sent a partial params object to Kotlin's set_settings while the
 * tauriSettingsStore hadn't finished loading, and the Kotlin handler silently
 * defaulted missing keys to false instead of preserving the previous value.
 *
 * These tests exercise the full stack (Svelte UI → Tauri invoke → Kotlin
 * SharedPreferences) across a real app restart, so any regression in any
 * layer (frontend race, Kotlin merge, autoUploadLicense subscriber) would surface
 * here. Tests set their own preconditions explicitly rather than relying on
 * defaults, so they work regardless of ordering within the suite.
 */

import { browser } from '@wdio/globals';
import { byTestId, ensureWebViewContext, openMenu, TESTID } from '../helpers/selectors';
import { recreateTestUsers, loginAsTestUser } from '../helpers/backend';

const APP_PACKAGE = 'cz.hillviedev';

/** Open the nav menu and tap the Settings link. Works from any page. */
async function openSettings(): Promise<void> {
    await openMenu();
    await browser.pause(800);

    const settingsLink = await byTestId(TESTID.settingsMenuLink);
    await settingsLink.waitForDisplayed({ timeout: 5000 });
    await settingsLink.click();
    await browser.pause(2000);
    await ensureWebViewContext();
}

/**
 * Kill the app and bring it back. Preserves SharedPreferences and WebView storage.
 *
 * We have to step out of the WebView context first: terminateApp kills the
 * WebView process, which invalidates any WebView-bound Chromedriver session —
 * subsequent WebView calls then fail with "invalid session id: session deleted
 * as the browser has closed the connection from disconnected". Switching to
 * NATIVE_APP detaches Chromedriver cleanly; wdio.conf.ts's
 * `recreateChromeDriverSessions: true` then gives us a fresh Chromedriver when
 * we switch back to the new WebView.
 */
async function restartApp(): Promise<void> {
    await driver.switchContext('NATIVE_APP');
    await driver.terminateApp(APP_PACKAGE);
    await browser.pause(1000);
    await driver.activateApp(APP_PACKAGE);
    await browser.pause(3000);

    // Wait until the new WebView is listed before attempting a context switch.
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
        const contexts = await driver.getContexts();
        if (contexts.some((c: any) => String(c).includes('WEBVIEW'))) break;
        await browser.pause(500);
    }
    await ensureWebViewContext();
}

/** Set the license checkbox to the desired state. No-op if already matching. */
async function setLicense(checked: boolean): Promise<void> {
    const license = await byTestId(TESTID.licenseCheckbox);
    await license.waitForDisplayed({ timeout: 10000 });
    if ((await license.isSelected()) !== checked) {
        await license.click();
        await browser.pause(500);
    }
}

/** Click the requested radio and wait a beat for the save round-trip. */
async function selectUploadRadio(testId: string): Promise<void> {
    const radio = await byTestId(testId);
    await radio.waitForDisplayed({ timeout: 5000 });
    await radio.click();
    await browser.pause(800);
}

/** Toggle the wifi-only checkbox to the desired state. Assumes it's visible (requires auto-upload enabled). */
async function setWifiOnly(on: boolean): Promise<void> {
    const wifi = await byTestId(TESTID.wifiOnlyCheckbox);
    await wifi.waitForDisplayed({ timeout: 5000 });
    if ((await wifi.isSelected()) !== on) {
        await wifi.click();
        await browser.pause(500);
    }
}

describe('Settings persistence', () => {
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
    });

    /**
     * Regression test for the original bug: with no license selected, the
     * autoUploadLicense subscriber fires updateSettings({ auto_upload_enabled: false })
     * on every app start. Before the fix, this stomped auto_upload_prompt_enabled
     * down to false, flipping the radio from "Disabled" (prompt me) to
     * "Disabled (Never prompt)".
     */
    it('keeps auto-upload prompt enabled across restart with no license', async () => {
        await openSettings();
        // The radio group is pointer-events:none when license is unchecked, so
        // we have to check the license to seed the "Disabled" (prompt=true) state,
        // then uncheck it to land in the actual bug scenario (license null +
        // prompt_enabled true).
        await setLicense(true);
        await selectUploadRadio(TESTID.autoUploadDisabled);
        await setLicense(false);

        // Sanity check before the restart: license should be off, "Disabled"
        // radio selected, "Disabled (Never prompt)" not selected.
        const licenseBefore = await byTestId(TESTID.licenseCheckbox);
        expect(await licenseBefore.isSelected()).toBe(false);
        const disabledBefore = await byTestId(TESTID.autoUploadDisabled);
        const disabledNeverBefore = await byTestId(TESTID.autoUploadDisabledNever);
        expect(await disabledBefore.isSelected()).toBe(true);
        expect(await disabledNeverBefore.isSelected()).toBe(false);

        // Extra settle time: the license toggled true → false in quick succession,
        // and Android WebView's localStorage is flushed to disk lazily. Without
        // this pause, terminateApp may kill the process before the second write
        // reaches disk, leaving the first (true) write as the persisted value.
        await browser.pause(2000);

        await restartApp();
        await openSettings();

        // After restart, the prompt setting must NOT have flipped to "never".
        // License is still unchecked, so the autoUploadLicense subscriber fires again
        // on this startup — the regression would surface here.
        const licenseAfter = await byTestId(TESTID.licenseCheckbox);
        await licenseAfter.waitForDisplayed({ timeout: 10000 });
        expect(await licenseAfter.isSelected()).toBe(false);

        const disabledAfter = await byTestId(TESTID.autoUploadDisabled);
        const disabledNeverAfter = await byTestId(TESTID.autoUploadDisabledNever);
        expect(await disabledAfter.isSelected()).toBe(true);
        expect(await disabledNeverAfter.isSelected()).toBe(false);
    });

    /**
     * Positive coverage: a user actively opting in to auto-upload + wifi-only
     * keeps all three settings across restart.
     */
    it('persists auto-upload enabled + wifi-only across restart', async () => {
        await openSettings();
        await setLicense(true);
        await selectUploadRadio(TESTID.autoUploadEnabled);
        await setWifiOnly(true);

        await restartApp();
        await openSettings();

        const licenseAfter = await byTestId(TESTID.licenseCheckbox);
        await licenseAfter.waitForDisplayed({ timeout: 10000 });
        expect(await licenseAfter.isSelected()).toBe(true);
        expect(await (await byTestId(TESTID.autoUploadEnabled)).isSelected()).toBe(true);
        expect(await (await byTestId(TESTID.wifiOnlyCheckbox)).isSelected()).toBe(true);
    });

    /**
     * "Disabled (Never prompt)" — the state the original bug accidentally set —
     * must persist when the user explicitly chooses it. This catches regressions
     * in the other direction (e.g., a future fix that restores prompt_enabled=true
     * too aggressively on every startup).
     */
    it('persists "Disabled (Never prompt)" across restart', async () => {
        await openSettings();
        // Need license to bypass pointer-events:none on the radio group.
        await setLicense(true);
        await selectUploadRadio(TESTID.autoUploadDisabledNever);

        const neverBefore = await byTestId(TESTID.autoUploadDisabledNever);
        expect(await neverBefore.isSelected()).toBe(true);

        await restartApp();
        await openSettings();

        const licenseAfter = await byTestId(TESTID.licenseCheckbox);
        await licenseAfter.waitForDisplayed({ timeout: 10000 });
        expect(await licenseAfter.isSelected()).toBe(true);

        const neverAfter = await byTestId(TESTID.autoUploadDisabledNever);
        const disabledAfter = await byTestId(TESTID.autoUploadDisabled);
        const enabledAfter = await byTestId(TESTID.autoUploadEnabled);
        expect(await neverAfter.isSelected()).toBe(true);
        expect(await disabledAfter.isSelected()).toBe(false);
        expect(await enabledAfter.isSelected()).toBe(false);
    });

    /**
     * Canonical merge test: changing a *single* setting must not silently reset
     * the others. This is the exact invariant the Kotlin merge + frontend race
     * fix are designed to preserve. Before the fix, toggling wifi_only would
     * send a partial params object to set_settings, and the missing fields
     * (auto_upload_enabled, auto_upload_prompt_enabled) would default to false.
     */
    it('toggling wifi-only does not stomp auto-upload state', async () => {
        await openSettings();

        // Establish a known full state.
        await setLicense(true);
        await selectUploadRadio(TESTID.autoUploadEnabled);
        await setWifiOnly(true);

        await restartApp();
        await openSettings();

        // Confirm full state survived the first restart before the partial update.
        expect(await (await byTestId(TESTID.autoUploadEnabled)).isSelected()).toBe(true);
        expect(await (await byTestId(TESTID.wifiOnlyCheckbox)).isSelected()).toBe(true);

        // Partial update: flip ONLY wifi-only off.
        await setWifiOnly(false);

        await restartApp();
        await openSettings();

        // License + enabled radio must still be set; only wifi-only should have flipped.
        expect(await (await byTestId(TESTID.licenseCheckbox)).isSelected()).toBe(true);
        expect(await (await byTestId(TESTID.autoUploadEnabled)).isSelected()).toBe(true);
        expect(await (await byTestId(TESTID.wifiOnlyCheckbox)).isSelected()).toBe(false);
    });

    /**
     * Cross-category merge: the compass setting is stored in compassPrefs while
     * upload settings live in uploadPrefs, but both go through the same Kotlin
     * set_settings handler. If the merge logic only preserved upload fields and
     * stomped compass (or vice versa), this test would fail.
     */
    it('compass landscape setting persists independently of upload changes', async () => {
        await openSettings();

        // Turn the compass landscape workaround on.
        const landscape = await byTestId(TESTID.landscapeArmor22Checkbox);
        await landscape.waitForDisplayed({ timeout: 10000 });
        if (!(await landscape.isSelected())) {
            await landscape.click();
            await browser.pause(500);
        }

        await restartApp();
        await openSettings();

        // Sanity check that it survived a plain restart.
        expect(await (await byTestId(TESTID.landscapeArmor22Checkbox)).isSelected()).toBe(true);

        // Now touch an upload setting and confirm the compass flag isn't dragged along.
        await setLicense(true);
        await selectUploadRadio(TESTID.autoUploadDisabled);

        await restartApp();
        await openSettings();

        expect(await (await byTestId(TESTID.landscapeArmor22Checkbox)).isSelected()).toBe(true);
        expect(await (await byTestId(TESTID.autoUploadDisabled)).isSelected()).toBe(true);
    });
});
