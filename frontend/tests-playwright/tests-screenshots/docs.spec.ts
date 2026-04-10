import { test, type Page } from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { ensureHunterMode } from '../helpers/sourceHelpers';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Docs screenshots.
 *
 * Produces imagery for:
 *   - docs/USER_GUIDE.md
 *   - marketing / landing pages
 *   - play store listing (web equivalents; real android shots still come from emulator)
 *
 * Each test runs once per viewport project defined in
 * playwright.screenshots.config.ts. Files land in:
 *   docs/screenshots/<project>/<name>.png
 *
 * The HERO shots focus on the annotated panorama — that is the primary
 * value proposition of Hillview. Technical shots support the detailed
 * sections of the guide.
 */

// The flagship annotated panorama (Vyhlídka Prosecké skály - východ).
// This URL is the one we hand out to new visitors.
const HERO_PANORAMA_URL =
  '/?lat=50.11691142317276&lon=14.488375782966616&zoom=20&bearing=139.06&photo=hillview-333e8851-c59b-4133-bce5-2d1ddc2ce335';

const OUT_ROOT = process.env.SCREENSHOT_OUT_DIR
  ? path.resolve(process.env.SCREENSHOT_OUT_DIR)
  : path.resolve(__dirname, '../../../docs/screenshots');

function outPath(project: string, name: string): string {
  const dir = path.join(OUT_ROOT, project);
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, `${name}.png`);
}

async function shot(page: Page, project: string, name: string, fullPage = false) {
  await page.screenshot({
    path: outPath(project, name),
    fullPage,
    animations: 'disabled',
  });
}

/** Wait for the map + photo split view to be visually settled. */
async function waitForMapView(page: Page) {
  await page.waitForLoadState('networkidle').catch(() => { /* best effort */ });
  await page.waitForSelector('.leaflet-container', { timeout: 15_000 });
  // Let tiles, photo, and any annotorious overlays render.
  await page.waitForTimeout(2500);
}

/** Wait for a plain content page (no map). */
async function waitForContent(page: Page) {
  await page.waitForLoadState('networkidle').catch(() => { /* best effort */ });
  await page.waitForTimeout(800);
}

// ---------------------------------------------------------------------------
// HERO SHOTS — annotated panorama
// ---------------------------------------------------------------------------

test.describe('hero', () => {
  test('annotated panorama — first-visit view', async ({ page }, testInfo) => {
    const project = testInfo.project.name;
    await page.goto(HERO_PANORAMA_URL);
    await waitForMapView(page);
    await shot(page, project, 'hero-panorama');
  });

  test('annotated panorama — zoom view', async ({ page }, testInfo) => {
    const project = testInfo.project.name;
    await page.goto(HERO_PANORAMA_URL);
    await waitForMapView(page);
    // Tap the photo to open the OSD zoom view.
    await page.locator('[data-testid="main-photo"].front').click();
    await page.locator('[data-testid="osd-viewer-overlay"]').waitFor({ state: 'visible', timeout: 10_000 });
    // Let OSD fully render tiles + annotations.
    await page.waitForTimeout(2000);
    // Zoom in a bit via scroll wheel in the centre of the viewer.
    // Zoom in — use OSD's built-in keyboard zoom (+ key).
    // Works on both desktop and mobile emulation.
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press('+');
      await page.waitForTimeout(200);
    }
    await page.waitForTimeout(1500);
    await shot(page, project, 'hero-panorama-full');
  });
});

// ---------------------------------------------------------------------------
// TECHNICAL SHOTS — for the detailed guide sections
// ---------------------------------------------------------------------------

test.describe('guide', () => {
  test('login page', async ({ page }, testInfo) => {
    const project = testInfo.project.name;
    await page.goto('/login');
    await waitForContent(page);
    await shot(page, project, '03-login-page');
  });

  test('activity feed', async ({ page }, testInfo) => {
    const project = testInfo.project.name;
    await page.goto('/activity');
    await waitForContent(page);
    await shot(page, project, '06-activity-feed');
  });

  test('best of', async ({ page }, testInfo) => {
    const project = testInfo.project.name;
    await page.goto('/bestof');
    await waitForContent(page);
    await shot(page, project, '07-best-of');
  });

  test('settings', async ({ page }, testInfo) => {
    const project = testInfo.project.name;
    await page.goto('/settings');
    await waitForContent(page);
    await shot(page, project, '08-settings');
  });

  test('about', async ({ page }, testInfo) => {
    const project = testInfo.project.name;
    await page.goto('/about');
    await waitForContent(page);
    await shot(page, project, '09-about-page');
  });
});

// ---------------------------------------------------------------------------
// CAPTURE SHOTS — camera and external camera workflow
// ---------------------------------------------------------------------------

test.describe('capture', () => {
  test('camera capture view', async ({ page }, testInfo) => {
    const project = testInfo.project.name;
    // Enable fake camera via localStorage before navigating.
    await page.goto('/');
    await page.evaluate(() => localStorage.setItem('fakeCamera', 'true'));
    await page.goto('/');
    await waitForMapView(page);
    await page.locator('[data-testid="camera-button"]').click();
    // Wait for the capture UI to render with the fake canvas.
    await page.waitForTimeout(1500);
    await shot(page, project, '10-camera-capture');
  });

  test('qr timestamp page', async ({ page }, testInfo) => {
    const project = testInfo.project.name;
    await page.goto('/settings/advanced/qr-timestamp');
    await page.locator('[data-testid="qr-timestamp-page"]').waitFor({ state: 'visible', timeout: 10_000 });
    await page.waitForTimeout(1000);
    await shot(page, project, '11-qr-timestamp');
  });
});

// ---------------------------------------------------------------------------
// INTERACTIVE STATES — menus / modals opened
// ---------------------------------------------------------------------------

test.describe('interactive', () => {
  test('navigation menu opened', async ({ page }, testInfo) => {
    const project = testInfo.project.name;
    await page.goto('/');
    await waitForMapView(page);
    // Fails the spec (and therefore the run) if the selector doesn't resolve.
    await page.locator('[data-testid="hamburger-menu"]').click();
    await page.waitForTimeout(500);
    await shot(page, project, '02-navigation-menu');
  });

  test('filters modal opened', async ({ page }, testInfo) => {
    const project = testInfo.project.name;
    await page.goto('/');
    await waitForMapView(page);
    await ensureHunterMode(page, true);
    await page.locator('[data-testid="filters-button"]').click();
    await page.waitForTimeout(500);
    await shot(page, project, '05-filters-modal');
  });
});
