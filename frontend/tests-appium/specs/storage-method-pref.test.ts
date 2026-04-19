/**
 * Coverage for the three user-selectable storage methods in
 * StorageSettings.svelte. The capture pipeline in device_photos.rs
 * (save_to_pictures_directory) tries the preferred method first and
 * falls back through the other two on failure. Which method actually
 * wins depends on the Android API level and the app's runtime state,
 * and a given preference won't always land in its "named" location —
 * that's by design.
 *
 * What this spec asserts:
 *   - Each radio-driven capture produces a photo saved somewhere valid
 *     (one of the three known patterns). That guarantees the fallback
 *     chain functions end-to-end and catches silent save failures.
 *
 * What this spec does NOT assert:
 *   - That the preferred method is the one that actually ran. That
 *     varies per API level; a strict assertion would produce API-
 *     dependent noise. Each test logs the path it observed so running
 *     against multiple emulator API levels yields a reference matrix.
 */

import { browser } from '@wdio/globals';
import {
    acceptPermissionDialogIfPresent,
    byTestId,
    ensureWebViewContext,
    openMenu,
    TESTID,
} from '../helpers/selectors';

const APP_PACKAGE = 'cz.hillviedev';

const PATH_PATTERNS: Record<string, RegExp> = {
    public_folder: /^\/storage\/emulated\/0\/DCIM\/(\.?)Hillview\//,
    private_folder: new RegExp(
        `^/storage/emulated/0/Android/data/${APP_PACKAGE}/files/Pictures/(\\.?)Hillview/`,
    ),
    mediastore_api: /^content:\/\//,
};

/** Identify which storage method a saved path matches; null if unrecognized. */
function classifyPath(path: string): keyof typeof PATH_PATTERNS | null {
    for (const method of Object.keys(PATH_PATTERNS) as (keyof typeof PATH_PATTERNS)[]) {
        if (PATH_PATTERNS[method].test(path)) return method;
    }
    return null;
}

interface DevicePhoto {
    id: string;
    file_path: string;
    file_name: string;
    created_at: number;
}

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

async function openSettings(): Promise<void> {
    await openMenu();
    await browser.pause(800);
    const link = await byTestId(TESTID.settingsMenuLink);
    await link.waitForDisplayed({ timeout: 5000 });
    await link.click();
    await browser.pause(2000);
    await ensureWebViewContext();
}

async function selectStorageRadio(testId: string): Promise<void> {
    await openSettings();
    const radio = await byTestId(testId);
    await radio.waitForDisplayed({ timeout: 10000 });
    await radio.click();
    await browser.pause(800);
    await browser.back();
    await browser.pause(1500);
}

async function captureOnePhoto(permissionsAlreadyGranted: boolean): Promise<void> {
    const cameraBtn = await byTestId(TESTID.cameraButton);
    await cameraBtn.waitForDisplayed({ timeout: 10000 });
    await cameraBtn.click();
    await browser.pause(1000);

    if (!permissionsAlreadyGranted) {
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
    // The capture → chunk → Rust save → Kotlin addPhotoToDatabase round
    // trip isn't instantaneous; 5s leaves headroom for the DB row to land.
    await browser.pause(5000);

    // Close camera so subsequent settings navigation works.
    await cameraBtn.click();
    await browser.pause(1500);
}

/**
 * Invoke `cmd.get_device_photos` from inside the WebView and return the
 * most recent photo row. The Kotlin handler reads Room DB directly, so
 * this sees whatever `save_to_pictures_directory` stored during capture.
 */
async function latestDevicePhoto(): Promise<DevicePhoto | null> {
    await ensureWebViewContext();
    const result = (await browser.executeAsync(`
        const done = arguments[arguments.length - 1];
        const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
        if (!invoke) { done({ __err: 'no invoke' }); return; }
        invoke('plugin:hillview|cmd', {
            command: 'get_device_photos',
            params: { page: 1, page_size: 100 }
        }).then((r) => done(r), (e) => done({ __err: String(e) }));
    `)) as any;

    if (result?.__err) throw new Error(result.__err);
    const photos: DevicePhoto[] = result?.photos ?? [];
    if (photos.length === 0) return null;
    // The response may or may not be sorted; pick the newest by created_at.
    return photos.reduce((a, b) => (a.created_at >= b.created_at ? a : b));
}

describe('Storage method preference — photo save path', () => {
    let permissionsGranted = false;

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

        // mockCamera makes every capture include a fresh timestamp so
        // duplicate-hash detection doesn't drop consecutive captures.
        await browser.execute(() => localStorage.setItem('mockCamera', 'true'));
    });

    /**
     * Restart to ensure each test starts with the menu reliably reachable.
     * App data (permissions, localStorage, Room DB) persists — we rely on
     * that for permissions being pre-granted after the first capture.
     */
    beforeEach(async () => {
        await restartApp();
    });

    async function runCase(radioTestId: string, preference: keyof typeof PATH_PATTERNS): Promise<void> {
        await selectStorageRadio(radioTestId);
        await captureOnePhoto(permissionsGranted);
        permissionsGranted = true;

        const photo = await latestDevicePhoto();
        expect(photo).not.toBeNull();

        const actual = classifyPath(photo!.file_path);
        // Log the matrix cell: which method actually won for this preference
        // on this API level. Picked up by the `spec` reporter output.
        console.log(
            `[storage] preference=${preference} → landed via ${actual ?? 'UNRECOGNIZED'} (${photo!.file_path})`,
        );

        expect(actual).not.toBeNull();
    }

    it('public_folder preference saves to a recognized storage location', async function () {
        this.timeout(180000);
        await runCase(TESTID.storagePublicFolder, 'public_folder');
    });

    it('private_folder preference saves to a recognized storage location', async function () {
        this.timeout(180000);
        await runCase(TESTID.storagePrivateFolder, 'private_folder');
    });

    it('mediastore_api preference saves to a recognized storage location', async function () {
        this.timeout(180000);
        await runCase(TESTID.storageMediaStoreApi, 'mediastore_api');
    });
});
