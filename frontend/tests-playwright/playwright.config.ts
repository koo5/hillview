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

    /* Accept the self-signed cert when running against the Caddy HTTPS/HTTP-2
       origin (FRONTEND_URL=https://hillview.dev4.local, `tls internal`). Harmless
       for http origins. Serving the whole stack behind one h2 origin removes the
       HTTP/1.1 connection-cap starvation (see Caddyfile). */
    ignoreHTTPSErrors: true,

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
            // ignoreHTTPSErrors does NOT cover the service-worker script fetch;
            // against the self-signed Caddy origin the SW registration fails with
            // an SSL error (a pageerror that console-checking tests flag). This
            // flag makes Chromium accept the cert for SW fetches too.
            '--ignore-certificate-errors',
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
        launchOptions: {
          firefoxUserPrefs: {
            // Trust CAs from the OS store (where the Caddy internal root is
            // installed) so the service worker registers on the self-signed
            // https origin — ignoreHTTPSErrors doesn't cover SW script fetches.
            'security.enterprise_roots.enabled': true,
          },
        },
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
      // KNOWN-FLAKY over plain-HTTP/1.1 origins (the :3000 container or the dev
      // server): WebKit/Firefox intermittently fail to load a code-split JS/CSS
      // chunk — "Importing a module script failed", a page with no CSS
      // (NS_BINDING_ABORTED), a login that never navigates, or a component that
      // never renders. Root cause: HTTP/1.1's ~6-connections-per-origin cap —
      // SSE streams + many lazy chunks starve asset fetches; WebKit/Firefox
      // connection scheduling is why chromium rarely shows it.
      //
      // FIXED by the Caddy HTTPS/HTTP-2 origin: run with
      //   FRONTEND_URL=https://hillview.dev4.local
      // (single h2 origin fronting frontend + /api + /worker + /pics — no
      // connection cap, no CORS; see /home/koom/caddy/Caddyfile). Needs the
      // Caddy container up, the hostname in /etc/hosts, and the Caddy internal
      // root CA in the system store (for the service worker; chromium also has
      // --ignore-certificate-errors, firefox security.enterprise_roots).
      // Verified: the starvation failure class drops to zero over h2.
      // Against a plain-HTTP origin these failures remain — re-run/retries.
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

  /* Run your local dev server before starting the tests — but ONLY when no
     external FRONTEND_URL is given. When FRONTEND_URL points at an already-running
     origin (the prod container on :3000, or the Caddy HTTPS/HTTP-2 origin), we
     must NOT manage a webServer: Playwright's readiness probe is Node-side and
     does not honor `ignoreHTTPSErrors`, so against a self-signed https origin it
     fails the cert check, assumes the server is down, starts `vite dev`, and then
     times out waiting for a URL vite never serves. */
  webServer: process.env.FRONTEND_URL ? undefined : {
    command: 'bun run dev',
    cwd: path.resolve(__dirname, '..'),
    url: 'http://localhost:8212',
    reuseExistingServer: !process.env.CI,
  },
});
