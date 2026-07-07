/**
 * E2E: a photo upload recovers from a transient WORKER failure.
 *
 * The client uploads to the worker (${worker_url}/upload, from the API's
 * authorize-upload response). This faults the worker's own upload endpoint via its
 * /debug/faults (the worker half of the shared fault injector), confirms the photo
 * doesn't get stuck, and verifies it uploads once the worker heals.
 *
 * Requires the dev app (cz.hillviedev) + api at localhost:8055 + worker at
 * localhost:8056, both rebuilt with the fault middleware (DEV_MODE/DEBUG_ENDPOINTS).
 */
import { browser } from '@wdio/globals';
import { byTestId, ensureWebViewContext, TESTID } from '../helpers/selectors';
import {
    recreateTestUsers,
    loginAsTestUser,
    getTestUserToken,
    getUserPhotos,
    armWorkerFault,
    clearWorkerFaults,
} from '../helpers/backend';
import { captureOnePhoto, enableAutoUpload } from '../helpers/uploadFlow';
import { invokePlugin } from '../helpers/bridge';

async function uploadedPhotoCount(): Promise<number> {
    const token = await getTestUserToken();
    // only_processed: authorize-upload already created an "authorized" placeholder
    // row for the faulted photo; "uploaded" here means the bytes made it through
    // the worker (status completed).
    return (await getUserPhotos(token, true)).count;
}

/** Poll (re-triggering the upload worker) until the server reports `target` photos. */
async function waitForUploadedCount(target: number, timeoutMs: number): Promise<number> {
    const deadline = Date.now() + timeoutMs;
    let count = 0;
    while (Date.now() < deadline) {
        count = await uploadedPhotoCount();
        if (count >= target) return count;
        await invokePlugin('plugin:hillview|tryUploads').catch(() => {});
        await browser.pause(3000);
    }
    return count;
}

describe('Upload recovers from a transient worker failure', function () {
    this.timeout(240000);

    before(async () => {
        await recreateTestUsers(); // fresh user → 0 photos
        await browser.pause(3000);
        const menu = await byTestId(TESTID.hamburgerMenu);
        await menu.waitForDisplayed({ timeout: 30000 });
        await loginAsTestUser();
        await ensureWebViewContext();
        await browser.execute(() => localStorage.setItem('mockCamera', 'true'));
        await enableAutoUpload();
    });

    after(async () => {
        try {
            await clearWorkerFaults();
        } catch {
            // best effort
        }
    });

    it('uploads the photo only after the worker upload endpoint is healed', async () => {
        // Nuke the worker's upload endpoint.
        await armWorkerFault('/upload*', { status: 503 });

        // Capture a photo → auto-upload tries → worker 503 → upload fails, stays pending.
        await captureOnePhoto(false);
        await invokePlugin('plugin:hillview|tryUploads');
        await browser.pause(6000);
        expect(await uploadedPhotoCount()).toBe(0); // not uploaded while the worker is down

        // Heal the worker → the queued photo uploads on retry.
        await clearWorkerFaults();
        const count = await waitForUploadedCount(1, 90000);
        expect(count).toBeGreaterThanOrEqual(1);
    });
});
