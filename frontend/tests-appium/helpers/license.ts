/**
 * The upload licence is chosen in a dialog (LicenseChoiceControl.svelte ->
 * LicenseDialog.svelte), not an inline checkbox: open it, pick the
 * CC BY-SA 4.0 + OSM radio (testid license-checkbox), confirm. Mirrors
 * tests-playwright/helpers/licenseChoice.ts. The dialog cannot unset a licence.
 */
import { browser } from '@wdio/globals';
import { byTestId, TESTID } from './selectors';

/** Whether an upload licence is set. Waits for the licence summary first. */
export async function hasUploadLicense(): Promise<boolean> {
    const summary = await byTestId(TESTID.licenseSummary);
    await summary.waitForDisplayed({ timeout: 10000 });
    return !(await (await byTestId(TESTID.licenseUnset)).isExisting());
}

/** Choose CC BY-SA 4.0 + OSM unless a licence is already set. */
export async function ensureUploadLicense(): Promise<void> {
    if (await hasUploadLicense()) return;
    const change = await byTestId(TESTID.licenseChangeButton);
    await change.waitForDisplayed({ timeout: 5000 });
    await change.click();
    const radio = await byTestId(TESTID.licenseCheckbox);
    await radio.waitForDisplayed({ timeout: 5000 });
    await radio.click();
    await (await byTestId(TESTID.licenseDialogConfirm)).click();
    await (await byTestId(TESTID.licenseUnset)).waitForExist({ reverse: true, timeout: 5000 });
    await browser.pause(500);
}
