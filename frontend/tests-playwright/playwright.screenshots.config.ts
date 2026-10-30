import { T } from './helpers/timeouts';
import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { chromiumHostResolverArgs, resolveFrontendUrl } from './helpers/target';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Screenshot generation config.
 *
 * This config is separate from playwright.config.ts because:
 *  - It does not need DB globalSetup / test user recreation.
 *  - It runs multiple viewport "projects" so every spec captures at
 *    each defined screen size.
 *
 * Targets the same origin as the main suite: SCREENSHOT_URL if set, else
 * FRONTEND_URL (the host profile's, via helpers/target.ts), else the local dev
 * server, which it reuses if running and starts otherwise. Same-origin matters:
 * from the dev server on :8212 the app calls the profile's API origin
 * cross-origin, which on the Caddy profiles also needs that origin's name
 * resolved and its `tls internal` certificate accepted.
 *
 * Usage:
 *   bun run screenshots                       # all viewports, all specs
 *   bun run screenshots --project=desktop     # just desktop
 *   bun run screenshots --project=mobile      # just mobile
 *   SCREENSHOT_URL=http://localhost:3000 bun run screenshots
 *
 * Output: docs/screenshots/<project>/<name>.png
 */
const TARGET_URL = process.env.SCREENSHOT_URL || resolveFrontendUrl();
const BASE_URL = TARGET_URL || 'http://localhost:8212';
const CHROMIUM_HOST_RESOLVER_ARGS = await chromiumHostResolverArgs(BASE_URL);

export default defineConfig({
  testDir: './tests-screenshots',
  /* Acquire the same cross-suite lock the main config uses so screenshot
   * runs serialize against regular test runs that wipe / recreate DB state.
   * Screenshots themselves do NOT recreate users — they capture existing
   * content. */
  globalSetup: './helpers/globalSetupScreenshots.ts',
  globalTeardown: './helpers/globalTeardown.ts',
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  timeout: T(60_000),
  // Bail out the entire run on the first failure so missing selectors
  // (e.g. interactive buttons without data-testids) halt screenshot
  // generation instead of quietly producing broken output.
  maxFailures: 1,
  use: {
    baseURL: BASE_URL,
    // As in playwright.config.ts: the Caddy origins use `tls internal`, and
    // ignoreHTTPSErrors does not cover service-worker script fetches, which
    // --ignore-certificate-errors does. Every project here runs on Chromium.
    ignoreHTTPSErrors: true,
    launchOptions: {
      args: ['--ignore-certificate-errors', ...CHROMIUM_HOST_RESOLVER_ARGS],
    },
    // Traces / videos aren't needed — we only save explicit screenshots.
    trace: 'off',
    video: 'off',
    screenshot: 'off',
  },
  // No webServer against an explicit origin: Playwright's readiness probe is
  // Node-side and ignores ignoreHTTPSErrors (see playwright.config.ts).
  webServer: TARGET_URL ? undefined : {
    command: 'bun run dev',
    cwd: path.resolve(__dirname, '..'),
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: T(120_000),
  },
  projects: [
    {
      name: 'desktop',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 2,
      },
    },
    {
      name: 'mobile',
      use: {
        // Use iPhone 13 dimensions but run on Chromium — WebKit crashes
        // on certain pages (e.g. bestof) during screenshot capture.
        ...devices['iPhone 13'],
        defaultBrowserType: 'chromium',
      },
    },
  ],
});
