/**
 * Coverage for incoming `click_action` intents — the pipeline FCM
 * notifications use to resume the app at a specific route.
 *
 * Flow:
 *   Intent with `click_action` extra arrives →
 *     ExamplePlugin.onNewIntent (ExamplePlugin.kt:2120) sets activity.intent
 *     and queues a `notification-click` message via queueMessage →
 *   JS KotlinMessageQueue.pollMessages picks it up (KotlinMessageQueue.ts:88)
 *   +layout.svelte's handleNotificationClick calls navigateWithHistory(route).
 *
 * We exercise the warm path (app already running, onNewIntent dispatches)
 * because it's the reliable case: a fresh LAUNCHER intent has no
 * click_action extra, so the cold-start branch in handleIntentData
 * (+layout.svelte:111) needs the extra to have been attached to the
 * original launch intent — harder to arrange from Appium without
 * restarting through the intent.
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
        // Make sure we're running; the reset between sessions already
        // gives us a fresh app on /. The map's hamburger menu confirms the
        // WebView is alive before we fire an intent at it.
        await ensureWebViewContext();
        const menu = await byTestId(TESTID.hamburgerMenu);
        await menu.waitForDisplayed({ timeout: 30000 });
    });

    it('navigates to the click_action route when an intent is delivered', async function () {
        this.timeout(60000);

        await fireClickActionIntent('/settings');

        // Settings page is identifiable by the license-checkbox, which is
        // always rendered on it regardless of auth state.
        await ensureWebViewContext();
        const license = await byTestId(TESTID.licenseCheckbox);
        await license.waitForDisplayed({ timeout: 15000 });
        expect(await license.isDisplayed()).toBe(true);
    });
});
