import { test, expect } from './fixtures';
import { recreateTestUsers, loginAsTestUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { ensureSourceEnabled } from './helpers/sourceHelpers';
import { collectErrors } from './helpers/consoleLogging';

type Page = import('@playwright/test').Page;

/** Open the OSD viewer by clicking the main photo. */
async function openViewer(page: Page) {
  const mainPhoto = page.locator('[data-testid="main-photo"]');
  await mainPhoto.waitFor({ state: 'visible', timeout: 30000 });
  await mainPhoto.click();
  await page.locator('[data-testid="osd-viewer-overlay"]').waitFor({ state: 'visible', timeout: 15000 });
  await page.locator('.openseadragon-canvas').waitFor({ state: 'visible', timeout: 15000 });
  await page.waitForTimeout(500);
}

/** Close the OSD viewer via the close button. */
async function closeViewer(page: Page) {
  await page.click('[data-testid="osd-viewer-close"]');
  await expect(page.locator('[data-testid="osd-viewer-overlay"]')).not.toBeVisible({ timeout: 5000 });
  await page.waitForTimeout(500);
}

/** Extract current URL search params as an object. */
function getUrlParams(url: string): URLSearchParams {
  return new URL(url).searchParams;
}

test.describe('Zoom View URL Parameters', () => {

  test.describe('URL params appear when zoom view opens', () => {

    test.beforeEach(async ({ testUsers }) => {
      await recreateTestUsers();
    });

    test('should add x1/y1/x2/y2 URL params when zoom view opens', async ({ page, testUsers }) => {
      // Upload a photo and navigate to its location
      await loginAsTestUser(page, testUsers.passwords.test);
      await uploadPhoto(page, testPhotos[0]);

      await page.goto('/?lat=50.1153&lon=14.4938&zoom=18');
      await page.waitForLoadState('networkidle');
      await ensureSourceEnabled(page, 'hillview', true);

      // Wait for photo to appear in gallery
      const mainPhoto = page.locator('[data-testid="main-photo"]');
      await mainPhoto.waitFor({ state: 'visible', timeout: 30000 });

      // URL should NOT have zoom params before opening viewer
      const urlBefore = getUrlParams(page.url());
      expect(urlBefore.get('x1')).toBeNull();
      expect(urlBefore.get('y1')).toBeNull();
      expect(urlBefore.get('x2')).toBeNull();
      expect(urlBefore.get('y2')).toBeNull();

      // Open zoom view
      await openViewer(page);

      // Wait for viewport bounds to be emitted (debounced at 500ms)
      await page.waitForTimeout(1500);

      // URL should now contain x1/y1/x2/y2 params
      const urlAfter = getUrlParams(page.url());
      expect(urlAfter.get('x1')).not.toBeNull();
      expect(urlAfter.get('y1')).not.toBeNull();
      expect(urlAfter.get('x2')).not.toBeNull();
      expect(urlAfter.get('y2')).not.toBeNull();

      // Params should be valid numbers
      const x1 = parseFloat(urlAfter.get('x1')!);
      const y1 = parseFloat(urlAfter.get('y1')!);
      const x2 = parseFloat(urlAfter.get('x2')!);
      const y2 = parseFloat(urlAfter.get('y2')!);
      expect(Number.isFinite(x1)).toBe(true);
      expect(Number.isFinite(y1)).toBe(true);
      expect(Number.isFinite(x2)).toBe(true);
      expect(Number.isFinite(y2)).toBe(true);

      // x2 > x1 and y2 > y1 (bounds are left-to-right, top-to-bottom)
      expect(x2).toBeGreaterThan(x1);
      expect(y2).toBeGreaterThan(y1);
    });

    test('should update x1/y1/x2/y2 URL params when panning in zoom view', async ({ page, testUsers }) => {
      await loginAsTestUser(page, testUsers.passwords.test);
      await uploadPhoto(page, testPhotos[0]);

      await page.goto('/?lat=50.1153&lon=14.4938&zoom=18');
      await page.waitForLoadState('networkidle');
      await ensureSourceEnabled(page, 'hillview', true);

      const mainPhoto = page.locator('[data-testid="main-photo"]');
      await mainPhoto.waitFor({ state: 'visible', timeout: 30000 });
      await openViewer(page);

      // Wait for initial viewport bounds
      await page.waitForTimeout(1500);
      const urlBefore = getUrlParams(page.url());
      const x1Before = parseFloat(urlBefore.get('x1')!);
      const y1Before = parseFloat(urlBefore.get('y1')!);

      // Zoom in by double-clicking to change viewport bounds
      const canvas = page.locator('.openseadragon-canvas');
      const canvasBox = await canvas.boundingBox();
      expect(canvasBox).toBeTruthy();

      // Double-click to zoom in (changes viewport bounds)
      await page.mouse.dblclick(
        canvasBox!.x + canvasBox!.width / 2,
        canvasBox!.y + canvasBox!.height / 2
      );

      // Wait for zoom animation (300ms) + debounce (500ms) + margin
      await page.waitForTimeout(1500);

      // URL params should have changed after zoom
      const urlAfter = getUrlParams(page.url());
      const x1After = parseFloat(urlAfter.get('x1')!);
      const x2After = parseFloat(urlAfter.get('x2')!);

      // After zooming in, the viewport rect should be smaller (x2-x1 should decrease)
      const widthBefore = parseFloat(urlBefore.get('x2')!) - x1Before;
      const widthAfter = x2After - x1After;
      expect(widthAfter).toBeLessThan(widthBefore);
    });

    test('should clear x1/y1/x2/y2 URL params when zoom view closes', async ({ page, testUsers }) => {
      await loginAsTestUser(page, testUsers.passwords.test);
      await uploadPhoto(page, testPhotos[0]);

      await page.goto('/?lat=50.1153&lon=14.4938&zoom=18');
      await page.waitForLoadState('networkidle');
      await ensureSourceEnabled(page, 'hillview', true);

      const mainPhoto = page.locator('[data-testid="main-photo"]');
      await mainPhoto.waitFor({ state: 'visible', timeout: 30000 });
      await openViewer(page);

      // Wait for params to appear
      await page.waitForTimeout(1500);
      const urlWithZoom = getUrlParams(page.url());
      expect(urlWithZoom.get('x1')).not.toBeNull();

      // Close the viewer
      await closeViewer(page);

      // Wait for URL update
      await page.waitForTimeout(1000);

      // Zoom params should be gone
      const urlAfterClose = getUrlParams(page.url());
      expect(urlAfterClose.get('x1')).toBeNull();
      expect(urlAfterClose.get('y1')).toBeNull();
      expect(urlAfterClose.get('x2')).toBeNull();
      expect(urlAfterClose.get('y2')).toBeNull();

      // Other params (lat, lon, etc.) should still be present
      expect(urlAfterClose.get('lat')).not.toBeNull();
      expect(urlAfterClose.get('lon')).not.toBeNull();
    });
  });

  test.describe('Loading from URL with zoom params', () => {

    test.beforeEach(async ({ testUsers }) => {
      await recreateTestUsers();
    });

    test('should show pending spinner when loading with zoom params', async ({ page, testUsers }) => {
      await loginAsTestUser(page, testUsers.passwords.test);
      const photoId = await uploadPhoto(page, testPhotos[0]);

      // Navigate with zoom view params
      await page.goto(`/?lat=50.1153&lon=14.4938&zoom=18&photo=hillview-${photoId}&x1=0.1&y1=0.1&x2=0.9&y2=0.9`);

      // Pending overlay should appear while waiting for photo data
      const pendingOverlay = page.locator('[data-testid="zoom-view-pending"]');
      // It may be very brief if data loads fast, so check with a short timeout
      // or check that eventually either the pending overlay or the viewer is visible
      const eitherVisible = await Promise.race([
        pendingOverlay.waitFor({ state: 'visible', timeout: 5000 }).then(() => 'pending'),
        page.locator('[data-testid="osd-viewer-overlay"]').waitFor({ state: 'visible', timeout: 15000 }).then(() => 'viewer'),
      ]);

      expect(['pending', 'viewer']).toContain(eitherVisible);
    });

    test('should open zoom view at specified bounds when loading from URL', async ({ page, testUsers }) => {
      await loginAsTestUser(page, testUsers.passwords.test);
      const photoId = await uploadPhoto(page, testPhotos[0]);

      // Navigate with zoom params that represent a zoomed-in view
      const targetX1 = 0.2;
      const targetY1 = 0.2;
      const targetX2 = 0.6;
      const targetY2 = 0.6;

      await page.goto(`/?lat=50.1153&lon=14.4938&zoom=18&photo=hillview-${photoId}&x1=${targetX1}&y1=${targetY1}&x2=${targetX2}&y2=${targetY2}`);
      await page.waitForLoadState('networkidle');

      // Enable hillview source and wait for viewer to open
      await ensureSourceEnabled(page, 'hillview', true);

      // Wait for the OSD viewer to open (either from pending or directly)
      await page.locator('[data-testid="osd-viewer-overlay"]').waitFor({ state: 'visible', timeout: 30000 });
      await page.locator('.openseadragon-canvas').waitFor({ state: 'visible', timeout: 15000 });

      // Wait for viewport bounds to settle and URL to update
      await page.waitForTimeout(2000);

      // The URL should now reflect the viewport (should be close to what we requested)
      const params = getUrlParams(page.url());
      const x1 = parseFloat(params.get('x1')!);
      const y1 = parseFloat(params.get('y1')!);
      const x2 = parseFloat(params.get('x2')!);
      const y2 = parseFloat(params.get('y2')!);

      // The viewport should contain the requested region
      // (fitBounds ensures the region fits within viewport, possibly with padding)
      expect(x1).toBeLessThanOrEqual(targetX1 + 0.05);
      expect(y1).toBeLessThanOrEqual(targetY1 + 0.05);
      expect(x2).toBeGreaterThanOrEqual(targetX2 - 0.05);
      expect(y2).toBeGreaterThanOrEqual(targetY2 - 0.05);

      // The viewport should NOT be the full image (we zoomed in)
      const viewportWidth = x2 - x1;
      expect(viewportWidth).toBeLessThan(1.0);
    });

    test('should close pending overlay when close button is clicked', async ({ page, testUsers }) => {
      // Navigate with zoom params for a non-existent photo so pending stays visible
      await page.goto('/?lat=50.0755&lon=14.4378&zoom=18&photo=hillview-nonexistent-999&x1=0.1&y1=0.1&x2=0.9&y2=0.9');
      await page.waitForLoadState('networkidle');

      const pendingOverlay = page.locator('[data-testid="zoom-view-pending"]');
      // The pending overlay should appear (photo won't load)
      await pendingOverlay.waitFor({ state: 'visible', timeout: 10000 });

      // Click close button
      await page.click('[data-testid="zoom-view-pending-close"]');

      // Pending overlay should disappear
      await expect(pendingOverlay).not.toBeVisible({ timeout: 5000 });

      // Zoom params should be cleared from URL
      await page.waitForTimeout(1000);
      const params = getUrlParams(page.url());
      expect(params.get('x1')).toBeNull();
      expect(params.get('y1')).toBeNull();
      expect(params.get('x2')).toBeNull();
      expect(params.get('y2')).toBeNull();
    });
  });

  test.describe('URL params coexistence', () => {

    test('should not add zoom params when page loads without them', async ({ page }) => {
      await page.goto('/?lat=50.0755&lon=14.4378&zoom=18');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      const params = getUrlParams(page.url());
      expect(params.get('x1')).toBeNull();
      expect(params.get('y1')).toBeNull();
      expect(params.get('x2')).toBeNull();
      expect(params.get('y2')).toBeNull();

      // Other params should still work
      expect(params.get('lat')).not.toBeNull();
      expect(params.get('lon')).not.toBeNull();
    });

    test('should not set pending zoom when zoom params present without photo param', async ({ page }) => {
      // x1/y1/x2/y2 without photo= should NOT activate pending zoom
      await page.goto('/?lat=50.0755&lon=14.4378&zoom=18&x1=0.1&y1=0.1&x2=0.9&y2=0.9');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      // Neither pending overlay nor OSD viewer should appear
      const pendingOverlay = page.locator('[data-testid="zoom-view-pending"]');
      const osdOverlay = page.locator('[data-testid="osd-viewer-overlay"]');
      await expect(pendingOverlay).not.toBeVisible();
      await expect(osdOverlay).not.toBeVisible();
    });

    test('should preserve photo and bearing params alongside zoom params', async ({ page, testUsers }) => {
      await recreateTestUsers();
      await loginAsTestUser(page, testUsers.passwords.test);
      await uploadPhoto(page, testPhotos[0]);

      await page.goto('/?lat=50.1153&lon=14.4938&zoom=18');
      await page.waitForLoadState('networkidle');
      await ensureSourceEnabled(page, 'hillview', true);

      const mainPhoto = page.locator('[data-testid="main-photo"]');
      await mainPhoto.waitFor({ state: 'visible', timeout: 30000 });
      await openViewer(page);

      // Wait for all URL params to settle
      await page.waitForTimeout(2000);

      const params = getUrlParams(page.url());

      // Zoom params should be present
      expect(params.get('x1')).not.toBeNull();
      expect(params.get('y1')).not.toBeNull();
      expect(params.get('x2')).not.toBeNull();
      expect(params.get('y2')).not.toBeNull();

      // Other params should still be present
      expect(params.get('lat')).not.toBeNull();
      expect(params.get('lon')).not.toBeNull();
      expect(params.get('photo')).not.toBeNull();
    });
  });

  test.describe('Share includes viewport bounds', () => {

    test.beforeEach(async ({ testUsers }) => {
      await recreateTestUsers();
    });

    /** Intercept clipboard.writeText so we can read what was shared across all browsers. */
    async function installClipboardInterceptor(page: Page) {
      await page.evaluate(() => {
        (window as any).__lastClipboardText = '';
        const orig = navigator.clipboard.writeText.bind(navigator.clipboard);
        navigator.clipboard.writeText = async (text: string) => {
          (window as any).__lastClipboardText = text;
          return orig(text).catch(() => {}); // swallow permission errors
        };
      });
    }

    async function getLastClipboardText(page: Page): Promise<string> {
      return page.evaluate(() => (window as any).__lastClipboardText as string);
    }

    test('share URL from zoom view should include x1/y1/x2/y2 params', async ({ page, testUsers }) => {
      await loginAsTestUser(page, testUsers.passwords.test);
      await uploadPhoto(page, testPhotos[0]);

      await page.goto('/?lat=50.1153&lon=14.4938&zoom=18');
      await page.waitForLoadState('networkidle');
      await ensureSourceEnabled(page, 'hillview', true);

      await openViewer(page);
      await installClipboardInterceptor(page);
      // Wait for viewport bounds to settle (debounced at 500ms)
      await page.waitForTimeout(1500);

      // Click Share button
      await page.click('[data-testid="osd-share"]');
      await page.waitForTimeout(500);

      // Read share URL from intercepted clipboard
      const clipboardText = await getLastClipboardText(page);
      const urlMatch = clipboardText.match(/https?:\/\/\S+/);
      expect(urlMatch, 'Share clipboard should contain a URL').toBeTruthy();

      const shareUrl = new URL(urlMatch![0]);
      const x1 = shareUrl.searchParams.get('x1');
      const y1 = shareUrl.searchParams.get('y1');
      const x2 = shareUrl.searchParams.get('x2');
      const y2 = shareUrl.searchParams.get('y2');

      expect(x1, 'Share URL should contain x1').not.toBeNull();
      expect(y1, 'Share URL should contain y1').not.toBeNull();
      expect(x2, 'Share URL should contain x2').not.toBeNull();
      expect(y2, 'Share URL should contain y2').not.toBeNull();

      // Bounds should be valid numbers with x2 > x1, y2 > y1
      expect(parseFloat(x2!) - parseFloat(x1!)).toBeGreaterThan(0);
      expect(parseFloat(y2!) - parseFloat(y1!)).toBeGreaterThan(0);

      // Should also have photo param
      expect(shareUrl.searchParams.get('photo')).toMatch(/^hillview-/);
    });

    test('share URL viewport bounds should reflect zoomed-in state', async ({ page, testUsers }) => {
      await loginAsTestUser(page, testUsers.passwords.test);
      await uploadPhoto(page, testPhotos[0]);

      await page.goto('/?lat=50.1153&lon=14.4938&zoom=18');
      await page.waitForLoadState('networkidle');
      await ensureSourceEnabled(page, 'hillview', true);

      await openViewer(page);
      await installClipboardInterceptor(page);
      await page.waitForTimeout(1500);

      // Share at default zoom
      await page.click('[data-testid="osd-share"]');
      await page.waitForTimeout(500);
      const defaultClip = await getLastClipboardText(page);
      const defaultUrl = new URL(defaultClip.match(/https?:\/\/\S+/)![0]);
      const defaultWidth = parseFloat(defaultUrl.searchParams.get('x2')!) - parseFloat(defaultUrl.searchParams.get('x1')!);

      // Zoom in by double-clicking
      const canvas = page.locator('.openseadragon-canvas');
      const canvasBox = await canvas.boundingBox();
      await page.mouse.dblclick(
        canvasBox!.x + canvasBox!.width / 2,
        canvasBox!.y + canvasBox!.height / 2
      );
      // Wait for zoom animation + debounce
      await page.waitForTimeout(1500);

      // Share at zoomed-in state
      await page.click('[data-testid="osd-share"]');
      await page.waitForTimeout(500);
      const zoomedClip = await getLastClipboardText(page);
      const zoomedUrl = new URL(zoomedClip.match(/https?:\/\/\S+/)![0]);
      const zoomedWidth = parseFloat(zoomedUrl.searchParams.get('x2')!) - parseFloat(zoomedUrl.searchParams.get('x1')!);

      // After zooming in, viewport width should be smaller
      expect(zoomedWidth).toBeLessThan(defaultWidth);
    });
  });

  test.describe('Error handling', () => {

    test('should handle malformed zoom params gracefully', async ({ page }) => {
      const { errors } = collectErrors(page);

      // Navigate with invalid (non-numeric) zoom params
      await page.goto('/?lat=50.0755&lon=14.4378&zoom=18&photo=hillview-123&x1=abc&y1=def&x2=ghi&y2=jkl');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      // App should not crash
      await expect(page.locator('.leaflet-container')).toBeVisible();

      expect(errors.length, `Found unexpected errors: ${errors.join(', ')}`).toBe(0);
    });

    test('should handle partial zoom params gracefully (only x1 and y1)', async ({ page }) => {
      const { errors } = collectErrors(page);

      // Only 2 of 4 params — should not activate zoom view
      await page.goto('/?lat=50.0755&lon=14.4378&zoom=18&photo=hillview-123&x1=0.1&y1=0.1');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      // Neither pending nor OSD should appear (incomplete params)
      const pendingOverlay = page.locator('[data-testid="zoom-view-pending"]');
      const osdOverlay = page.locator('[data-testid="osd-viewer-overlay"]');
      await expect(pendingOverlay).not.toBeVisible();
      await expect(osdOverlay).not.toBeVisible();

      // App should not crash
      await expect(page.locator('.leaflet-container')).toBeVisible();
      expect(errors.length, `Found unexpected errors: ${errors.join(', ')}`).toBe(0);
    });
  });
});
