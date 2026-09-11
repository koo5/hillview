import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { recreateTestUsers, loginAsTestUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { ensureSourceEnabled } from './helpers/sourceHelpers';

/**
 * Zoom view print view: a chrome-less rendering of the current view with the
 * share-link QR in the middle, handed to the printer via the browser's own
 * Ctrl+P. The viewer FREEZES (no OSD refits, no overlay-canvas resizes) and
 * the print layout scales it uniformly into an aspect-locked box — see the
 * "print view" block in OpenSeadragonViewer.svelte for the why.
 */

type Page = import('@playwright/test').Page;

// Test-asset location (testPhotos[0] sits near here — see bearing-url-param.spec).
const AT_PHOTO = '/?lat=50.1153&lon=14.4938&zoom=18';
const OVERLAY = '[data-testid="osd-viewer-overlay"]';

async function openViewer(page: Page) {
  const mainPhoto = page.locator('[data-testid="main-photo"]').first();
  await mainPhoto.waitFor({ state: 'visible', timeout: T(30000) });
  await mainPhoto.click();
  await page.locator(OVERLAY).waitFor({ state: 'visible', timeout: T(15000) });
  await page.locator('.openseadragon-canvas').waitFor({ state: 'visible', timeout: T(15000) });
  await page.waitForTimeout(500);
}

async function enterPrintView(page: Page) {
  await page.click('[data-testid="osd-display-menu-toggle"]', { timeout: T(10000) });
  // explicit timeouts: the suite leaves actionTimeout at 0, and a missing
  // element would otherwise sleep out the whole per-test budget
  await page.click('[data-testid="osd-print-view"]', { timeout: T(10000) });
  await expect(page.locator('[data-testid="osd-print-hint"]')).toBeVisible({ timeout: T(5000) });
}

test.describe('Zoom view print view', () => {
  test.beforeEach(async ({ page, testUsers }) => {
    // uploads dedupe per user by MD5 and every test uploads testPhotos[0]:
    // fresh users per test, as in zoom-view-url-params.spec
    await recreateTestUsers();
    await loginAsTestUser(page, testUsers.passwords.test);
    await uploadPhoto(page, testPhotos[0]);
    await page.goto(AT_PHOTO);
    await ensureSourceEnabled(page, 'hillview', true);
    await openViewer(page);
  });

  test('hides the chrome, shows the share-link QR, Escape leaves it', async ({ page }) => {
    const closeBtn = page.locator('[data-testid="osd-viewer-close"]');
    await expect(closeBtn).toBeVisible();

    await enterPrintView(page);

    // top chrome gone, the view itself still there
    await expect(closeBtn).not.toBeVisible();
    await expect(page.locator('[data-testid="osd-annotations-toggle"]')).not.toBeVisible();
    await expect(page.locator(OVERLAY)).toBeVisible();

    // the QR carries the share link (short /shared/ slug when the backend
    // mints one, else the long ?photo= form); only the host is spelled out
    const qr = page.locator('[data-testid="osd-print-qr"]');
    await expect(qr).toBeVisible();
    await expect(qr).toHaveAttribute('data-url', /^https?:\/\/.+(\/shared\/|photo=)/, { timeout: T(10000) });
    const host = page.locator('[data-testid="osd-print-qr-host"]');
    await expect(host).toHaveText(/^[\w.-]+(:\d+)?$/);
    // the screen-only hint strip spells out what the code encodes
    await expect(page.locator('[data-testid="osd-print-link"]')).toHaveText(/QR → \S+\/shared\/\d+$|short link unavailable/);
    // "Save as PDF" is named after the document title, which is the photo's
    // while the zoom view is open
    await expect(page).toHaveTitle(/ – Hillview$/);
    const qrPx = await page.locator('[data-testid="osd-print-qr-canvas"]').evaluate(
      (c: HTMLCanvasElement) => [c.width, c.clientWidth],
    );
    expect(qrPx[0]).toBeGreaterThan(0);
    expect(qrPx[1]).toBeGreaterThanOrEqual(128);

    // page orientation rule is injected only while the print view is on
    await expect(page.locator('[data-testid="osd-print-page-style"]')).toHaveCount(1);

    // Escape leaves the print view — it does NOT close the viewer
    await page.keyboard.press('Escape');
    await expect(page.locator('[data-testid="osd-print-hint"]')).not.toBeVisible();
    await expect(closeBtn).toBeVisible();
    await expect(page.locator(OVERLAY)).toBeVisible();
    await expect(page.locator('[data-testid="osd-print-page-style"]')).toHaveCount(0);

    // the mode's own label scale (1.4×) is gone with it: the slider is
    // back at the visitor's value
    await page.click('[data-testid="osd-display-menu-toggle"]', { timeout: T(10000) });
    await expect(page.locator('[data-testid="osd-annotation-scale-slider"]')).toHaveValue('1');
    // close it the way a visitor does, on the backdrop — the toggle is under
    // that backdrop while the menu is open, and Escape on an open menu falls
    // through to closing the viewer (the dropdown eats the key first)
    await page.click('[data-testid="dropdown-backdrop"]', { position: { x: 5, y: 5 }, timeout: T(10000) });
    await expect(page.locator('[data-testid="osd-annotation-scale-slider"]')).not.toBeVisible();

    // the Exit button does the same
    await enterPrintView(page);
    await page.click('[data-testid="osd-print-exit"]', { timeout: T(10000) });
    await expect(page.locator('[data-testid="osd-print-hint"]')).not.toBeVisible();
    await expect(closeBtn).toBeVisible();
  });

  test('print layout is an aspect-locked box with the overlay canvases scaled onto it', async ({ page }) => {
    const container = page.locator('.osd-container');
    const screenBox = (await container.boundingBox())!;
    const screenAr = screenBox.width / screenBox.height;

    await enterPrintView(page);

    // a square "page": the box must keep the screen aspect, not fill it
    await page.setViewportSize({ width: 900, height: 900 });
    await page.emulateMedia({ media: 'print' });
    await page.waitForTimeout(500);

    const box = (await container.boundingBox())!;
    expect(Math.abs(box.width / box.height - screenAr)).toBeLessThan(0.02);
    expect(box.width).toBeLessThanOrEqual(900);
    expect(box.height).toBeLessThan(900);

    // the overlay canvases follow the container (they are replaced elements:
    // without an explicit width/height they would stay at bitmap size and
    // drift off the photo — the original print-offset bug)
    for (const testid of ['osd-terrain-canvas', 'osd-label-canvas']) {
      const c = (await page.locator(`[data-testid="${testid}"]`).boundingBox())!;
      expect(Math.abs(c.width - box.width)).toBeLessThan(1.5);
      expect(Math.abs(c.height - box.height)).toBeLessThan(1.5);
    }
    // ...at their frozen backing size
    const backing = await page.locator('[data-testid="osd-label-canvas"]').evaluate(
      (c: HTMLCanvasElement) => [c.width, c.height],
    );
    expect(backing[0]).toBe(Math.round(screenBox.width));
    expect(backing[1]).toBe(Math.round(screenBox.height));

    await page.emulateMedia({ media: 'screen' });
  });

  test('prints as a single page', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'page.pdf() is Chromium-only');
    await enterPrintView(page);
    await expect(page.locator('[data-testid="osd-print-qr"]')).toHaveAttribute('data-url', /^https?:\/\//, { timeout: T(10000) });

    const pdf = await page.pdf({ format: 'A4', landscape: true, printBackground: true });
    const pages = pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g)?.length ?? 0;
    expect(pages).toBe(1);

    // and the viewer is intact afterwards (afterprint unfreezes nothing
    // here — the print view is still on)
    await expect(page.locator('[data-testid="osd-print-hint"]')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('[data-testid="osd-viewer-close"]')).toBeVisible();
  });
});
