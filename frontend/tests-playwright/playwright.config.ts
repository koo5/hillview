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
  },

  /* Global test timeout - 90 seconds for long-running Mapillary tests */
  timeout: 90000,

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