/**
 * Coverage for incoming `click_action` intents — the pipeline FCM
 * notifications use to open the app at a specific route. Two code paths
 * both land on the same outcome, and we cover each:
 *
 *  1. Warm path: app running, intent arrives →
 *       ExamplePlugin.onNewIntent (ExamplePlugin.kt:2120) sets
 *       activity.intent, queues `notification-click` →
 *       KotlinMessageQueue.pollMessages picks it up →
 *       +layout.svelte's handleNotificationClick → navigateWithHistory.
 *
 *  2. Cold-start path: app killed, intent launches it →
 *       MainActivity starts with the intent → +layout.svelte's onMount
 *       calls handleIntentData → `plugin:hillview|get_intent_data`
 *       returns the click_action from activity.intent
 *       (ExamplePlugin.kt:2147) → handleNotificationClickRoute fires.
 *
 * Separate tests because they share no code on the app side.
 *
 * There is no ACTION_SEND intent filter in AndroidManifest, so the
 * external "share to Hillview" flow has no test here — it isn't a
 * feature of the app.
 */

import { browser } from '@wdio/globals';
import { byTestId, ensureWebViewContext, TESTID } from '../helpers/selectors';

const APP_PACKAGE = 'cz.hillviedev';

/**
 * Fire an intent at MainActivity with a `click_action` string extra.
 * UiAutomator2's `mobile: startActivity` forwards extras as `[type, key,
 * value]` triples matching the `adb shell am start --es/--ei/...` style.
 */
async function fireClickActionIntent(route: string): Promise<void> {
    await (driver as any).execute('mobile: startActivity', {
        component: `${APP_PACKAGE}/.MainActivity`,
        extras: [['s', 'click_action', route]],
    });
    // KotlinMessageQueue polls at ~1s intervals; give the poll a few ticks
    // to pick up the queued message and finish navigateWithHistory.
    await browser.pause(4000);
}

describe('Incoming click_action intent', () => {
    before(async () => {
        // activateApp guarantees MainActivity is in the foreground even if
        // a preceding spec left the emulator on a different activity (the
        // share-intent spec parks us on the chooser resolver). The 3s pause
        // gives the Tauri WebView time to load before we try to switch into
        // its context.
        await driver.activateApp(APP_PACKAGE);
        await browser.pause(3000);

        const deadline = Date.now() + 30000;
        while (Date.now() < deadline) {
            const contexts = await driver.getContexts();
            if (contexts.some((c: any) => String(c).includes('WEBVIEW'))) break;
            await browser.pause(500);
        }

        await ensureWebViewContext();
        const menu = await byTestId(TESTID.hamburgerMenu);
        await menu.waitForDisplayed({ timeout: 30000 });
    });

    /** Wait for the Tauri WebView to be listed after app start. */
    async function waitForWebView(timeoutMs = 30000): Promise<void> {
        const deadline = Date.now() + timeoutMs;
        while (Date.now() < deadline) {
            const contexts = await driver.getContexts();
            if (contexts.some((c: any) => String(c).includes('WEBVIEW'))) return;
            await browser.pause(500);
        }
        throw new Error('WebView context not available within timeout');
    }

    async function assertOnSettings(timeoutMs: number): Promise<void> {
        await ensureWebViewContext();
        const license = await byTestId(TESTID.licenseCheckbox);
        await license.waitForDisplayed({ timeout: timeoutMs });
        expect(await license.isDisplayed()).toBe(true);
    }

    it('warm path: onNewIntent routes click_action while the app is running', async function () {
        this.timeout(60000);

        // Starting state was verified in `before` (hamburger-menu visible →
        // we're on /). After the intent we expect to land on /settings.
        await fireClickActionIntent('/settings');
        await assertOnSettings(15000);
    });

    it('cold-start path: a launch intent with click_action navigates via handleIntentData', async function () {
        this.timeout(90000);

        // Kill the app first so the intent starts it fresh. This exercises
        // the +layout.svelte:111 branch (handleIntentData in onMount), not
        // the onNewIntent → message-queue path tested above.
        await driver.switchContext('NATIVE_APP');
        await driver.terminateApp(APP_PACKAGE);
        await browser.pause(1500);

        // The click_action extra is attached to the launch intent itself,
        // so get_intent_data will see it on activity.intent the first time
        // the frontend queries. Cold boot + WebView load is slower than a
        // warm onNewIntent; wait out the longer path.
        await fireClickActionIntent('/settings');
        await waitForWebView(20000);
        await assertOnSettings(20000);
    });
});
