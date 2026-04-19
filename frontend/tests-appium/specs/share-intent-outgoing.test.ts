/**
 * Coverage for the outgoing share intent. The Kotlin side
 * (ExamplePlugin.kt:1845) builds `Intent.ACTION_SEND` with a plain-text
 * body and wraps it in `Intent.createChooser`, which Android surfaces as
 * the system share sheet. The plugin JS entry is
 * `plugin:hillview|share_photo`, called from PhotoActionsMenu /
 * OpenSeadragonViewer via shareUtils.sharePhoto.
 *
 * We invoke the plugin directly rather than driving through the full
 * photo-actions UI: sharing a photo requires a logged-in user with at
 * least one uploaded photo and a real photo marker tap, and all of that
 * is downstream of a simple `Intent.createChooser` call that we can check
 * more reliably by just watching the current activity change. The full
 * upload + pick flow is already covered by photo-workflow.test.ts.
 */

import { browser } from '@wdio/globals';
import { ensureWebViewContext } from '../helpers/selectors';

const APP_PACKAGE = 'cz.hillviedev';

/**
 * Invoke a Tauri plugin command from inside the WebView. Tauri v2 exposes
 * `window.__TAURI_INTERNALS__.invoke`, which the generated
 * `@tauri-apps/api/core` import resolves to. Going through that path
 * avoids needing any test-only globals in the app.
 */
async function invokePlugin(command: string, args: Record<string, unknown>): Promise<unknown> {
    await ensureWebViewContext();
    return await browser.executeAsync(
        `
        const done = arguments[arguments.length - 1];
        // @ts-ignore
        const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
        if (!invoke) { done({ __err: 'TAURI_INTERNALS.invoke not available' }); return; }
        invoke(arguments[0], arguments[1]).then(
            (r) => done(r),
            (e) => done({ __err: String(e) }),
        );
        `,
        command,
        args,
    );
}

/**
 * Dismiss whatever's on top and return control to the hillview activity.
 * The share sheet blocks subsequent specs if we leave it open.
 */
async function dismissChooser(): Promise<void> {
    try {
        await driver.back();
        await browser.pause(500);
    } catch {
        // no-op
    }
}

describe('Outgoing share intent', () => {
    after(async () => {
        // Best-effort cleanup in case an assertion failed mid-test.
        await dismissChooser();
    });

    it('share_photo plugin launches the system chooser', async function () {
        this.timeout(60000);

        const result = (await invokePlugin('plugin:hillview|share_photo', {
            title: 'Photo on Hillview',
            text: 'Check out this photo',
            url: 'https://hillview.cz/photo/test-share-spec',
        })) as { success?: boolean; __err?: string };

        expect(result.__err).toBeUndefined();
        expect(result.success).toBe(true);

        // Poll for the top activity to leave our app. `createChooser` can
        // present either as an IntentResolver activity (older Android) or
        // the ChooserActivity (Android S+); both are packaged under
        // `android` or `com.android.intentresolver`, never `cz.hillviedev`.
        // We don't assert the exact activity name — that varies by OEM and
        // Android version. The package-not-us check is the stable signal.
        let topPackage = APP_PACKAGE;
        const deadline = Date.now() + 10000;
        while (Date.now() < deadline && topPackage === APP_PACKAGE) {
            topPackage = (await (driver as any).getCurrentPackage()) as string;
            if (topPackage === APP_PACKAGE) await browser.pause(300);
        }

        expect(topPackage).not.toBe(APP_PACKAGE);
        expect(topPackage.length).toBeGreaterThan(0);
    });
});
