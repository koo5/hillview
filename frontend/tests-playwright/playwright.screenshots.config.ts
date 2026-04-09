import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Screenshot generation config.
 *
 * This config is separate from playwright.config.ts because:
 *  - It does not need DB globalSetup / test user recreation.
 *  - It runs multiple viewport "projects" so every spec captures at
 *    each defined screen size.
 *
 * Targets the local dev server by default. It will reuse an already
 * running dev server if present, otherwise it starts one. Override
 * with SCREENSHOT_URL if you want to point it elsewhere.
 *
 * Usage:
 *   bun run screenshots                       # all viewports, all specs
 *   bun run screenshots --project=desktop     # just desktop
 *   bun run screenshots --project=mobile      # just mobile
 *   SCREENSHOT_URL=http://localhost:3000 bun run screenshots
 *
 * Output: docs/screenshots/<project>/<name>.png
 */
const BASE_URL = process.env.SCREENSHOT_URL || 'http://localhost:8212';

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
  timeout: 60_000,
  // Bail out the entire run on the first failure so missing selectors
  // (e.g. interactive buttons without data-testids) halt screenshot
  // generation instead of quietly producing broken output.
  maxFailures: 1,
  use: {
    baseURL: BASE_URL,
    // Traces / videos aren't needed — we only save explicit screenshots.
    trace: 'off',
    video: 'off',
    screenshot: 'off',
  },
  webServer: {
    command: 'bun run dev',
    cwd: path.resolve(__dirname, '..'),
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: 120_000,
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
        ...devices['iPhone 13'],
      },
    },
  ],
});
