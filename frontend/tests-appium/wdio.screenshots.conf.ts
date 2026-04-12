import { config as baseConfig } from './wdio.conf.ts';

/**
 * Screenshot-specific config.
 *
 * Differences from the main test config:
 *  - Only runs the screenshot spec.
 *  - noReset: true — keeps app state between tests so we can navigate
 *    through pages without re-doing permission dialogs.
 *  - No bail — capture as many screens as possible even if one fails.
 *
 * The spec auto-detects device resolution and saves to the appropriate
 * output folder (android-phone, android-tablet-7, android-tablet-10).
 *
 * Usage:
 *   bun run screenshots
 *   # or directly:
 *   npx wdio run ./wdio.screenshots.conf.ts
 *
 * Output: docs/screenshots/android-<device>/<name>.png
 */
export const config: WebdriverIO.Config = {
    ...baseConfig,
    specs: ['./specs/screenshots.test.ts'],
    bail: 1,
    capabilities: [{
        ...baseConfig.capabilities?.[0] as object,
        'appium:noReset': true,
        'appium:fullReset': false,
    }],
    // Skip the fresh-start pause — we want a continuous session.
    beforeTest: async function (test) {
        console.log(`📸 Screenshot: ${test.title}`);
    },
    afterTest: async function (test, _context, { passed, duration }) {
        const status = passed ? '✅' : '❌';
        console.log(`${status} ${test.title} (${duration}ms)`);
    },
};
