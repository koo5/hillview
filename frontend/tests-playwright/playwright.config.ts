import { T } from './helpers/timeouts';
import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * @see https://playwright.dev/docs/test-configuration
 *
 * IMPORTANT: Do not run multiple `npx playwright test` processes at the same
 * time against the same backend. Many tests call recreate-test-users which
 * wipes shared database state. Running concurrent processes causes 500 errors
 * and login failures. Use a single `npx playwright test` invocation instead.
 */
export default defineConfig({
  testDir: '.',
  testIgnore: ['tests-screenshots/**'],
  /* Global setup for database initialization */
  globalSetup: './helpers/globalSetup.ts',
  /* Global teardown to release cross-suite test lock */
  globalTeardown: './helpers/globalTeardown.ts',
  /* Run tests in series to avoid database conflicts */
  fullyParallel: false,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,
  /* Use single worker to avoid database race conditions */
  workers: 1,
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: 'html',
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /* Base URL to use in actions like `await page.goto('/')`. */
    baseURL: process.env.FRONTEND_URL || 'http://localhost:8212',

    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: 'on-first-retry',

    /* Cap navigations (`goto`, `waitForLoadState`, `waitForURL`) at T(30000)
       — 90s at the default 3x multiplier, and it scales with PW_TIMEOUT_MULT
       like every other timeout (see helpers/timeouts.ts). The Playwright default
       (0) lets a navigation wait up to the whole per-test timeout, turning a
       stuck navigation — or a WebKit "internal error" on goto — into a
       multi-minute hang. This cap fails such hangs fast while staying far above
       any healthy navigation.

       IMPORTANT: this key MUST be camelCase `navigationTimeout`. It was
       previously misspelled `navigationtimeout` (lowercase t), which Playwright
       silently ignores — so navigations were effectively UNCAPPED and rode the
       full per-test timeout. Fixing the casing is what actually activates the
       cap. Keep it camelCase.

       `actionTimeout` is left at the default because some actions (batch photo
       uploads, long `expect().toBeVisible` waits) can legitimately take a while
       and pass their own per-call timeout. */
    navigationTimeout: T(30000),
  },

  /* Per-test timeout. Has to accommodate long-running Mapillary/photo-upload
     tests plus the navigation timeout above. */
  timeout: T(180000),

  /* Configure projects for major browsers */
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        permissions: ['camera'],
        launchOptions: {
          args: [
            '--use-fake-ui-for-media-stream',
            '--use-fake-device-for-media-stream',
          ]
        }
      },
    },

    {
      name: 'firefox',
      use: {
        ...devices['Desktop Firefox'],
        // Firefox doesn't support camera permission in Playwright yet
        // Skip camera-related tests for Firefox
      },
    },

    {
      name: 'webkit',
      use: {
        ...devices['Desktop Safari'],
        // WebKit doesn't support camera permissions in Playwright yet
      },
      // NOTE: deliberately NOT giving WebKit extra retries. Its residual failures
      // are timeout-bound HANGS ("WebKit encountered an internal error" on goto),
      // not fast assertion failures. They're now bounded by navigationTimeout
      // (90s) and the per-test timeout (T(180000) = 9min at the default 3x), so a
      // hang no longer costs ~33min — but a retry still re-runs the whole test,
      // so extra WebKit retries would add real wall-clock. Global retries:2
      // already applies; revisit only if the flake rate warrants it.
      // KNOWN-FLAKY: WebKit against the built frontend *container* (prod build,
      // served over HTTP/1.1) intermittently fails to load a code-split JS chunk —
      // surfacing as "Importing a module script failed", a login that never
      // navigates, or a component that never renders (e.g. license-checkbox timing
      // out). Measured ~1-in-3 runs, never consistent. Root cause is the same
      // HTTP/1.1 ~6-connections-per-origin starvation that made networkidle unusable
      // on the dev server (SSE streams + many lazy chunks starve a fetch); WebKit's
      // stricter connection scheduling is why only it shows this. It is NOT a
      // networkidle-cleanup regression and NOT reproducible on chromium.
      // Don't chase a webkit-only-against-container failure — re-run it; CI absorbs
      // it via retries. The real fix (if ever wanted) is serving the container over
      // HTTP/2 through Caddy (multiplexing removes the connection cap).
    },

    /* Test against mobile viewports. */
    // {
    //   name: 'Mobile Chrome',
    //   use: { ...devices['Pixel 5'] },
    // },
    // {
    //   name: 'Mobile Safari',
    //   use: { ...devices['iPhone 12'] },
    // },

    /* Test against branded browsers. */
    // {
    //   name: 'Microsoft Edge',
    //   use: { ...devices['Desktop Edge'], channel: 'msedge' },
    // },
    // {
    //   name: 'Google Chrome',
    //   use: { ...devices['Desktop Chrome'], channel: 'chrome' },
    // },
  ],

  /* Run your local dev server before starting the tests */
  webServer: {
    command: 'bun run dev',
    cwd: path.resolve(__dirname, '..'),
    url: process.env.FRONTEND_URL || 'http://localhost:8212',
    reuseExistingServer: !process.env.CI,
  },
});
