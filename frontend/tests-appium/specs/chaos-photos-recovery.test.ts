/**
 * E2E demo of the chaos-monkey fault injector: nuke an API endpoint and verify
 * the app surfaces the failure gracefully, then recovers once the fault clears.
 *
 * Targets the My Photos list (`GET /api/photos/`). With a fresh test user (0
 * photos), a fault makes the list error; clearing it and re-entering the screen
 * loads cleanly ("You haven't uploaded any photos yet.").
 *
 * Requires the dev app (cz.hillviedev) + backend at localhost:8055 with the
 * fault-injection middleware (api container rebuilt) and DEBUG_ENDPOINTS enabled.
 */

import { browser } from '@wdio/globals';
import { byTestId, ensureWebViewContext, openMenu, TESTID } from '../helpers/selectors';
import { recreateTestUsers, loginAsTestUser, armFault, clearFaults } from '../helpers/backend';

async function goToMyPhotos(): Promise<void> {
    await openMenu();
    await browser.pause(800);
    await ensureWebViewContext();
    const link = await $('[data-testid="my-photos-link"]');
    await link.waitForDisplayed({ timeout: 5000 });
    await link.click();
    await browser.pause(2500);
    await ensureWebViewContext();
}

/** Text of the empty/error message on the My Photos page, lowercased. */
async function myPhotosMessage(): Promise<string> {
    await ensureWebViewContext();
    const msg = await byTestId('no-photos-message');
    await msg.waitForDisplayed({ timeout: 8000 });
    return (await msg.getText()).toLowerCase();
}

describe('My Photos recovers from an injected API failure', function () {
    this.timeout(180000);

    before(async () => {
        await recreateTestUsers(); // fresh test user → 0 photos
        await browser.pause(3000);
        const menu = await byTestId(TESTID.hamburgerMenu);
        await menu.waitForDisplayed({ timeout: 30000 });
        await loginAsTestUser();
    });

    after(async () => {
        try {
            await clearFaults();
        } catch {
            // best effort
        }
    });

    it('shows an error while /api/photos is faulted, then recovers when cleared', async () => {
        // Nuke the photo-list endpoint for the next several requests.
        await armFault('/api/photos/*', { status: 500, count: 8 });

        await goToMyPhotos();
        expect(await myPhotosMessage()).toContain('error');

        // Heal the backend and re-mount the screen → it should load cleanly.
        await clearFaults();
        await browser.refresh();
        await browser.pause(3000);

        expect(await myPhotosMessage()).toContain("haven't uploaded");
    });
});
