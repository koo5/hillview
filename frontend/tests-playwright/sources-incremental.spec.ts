import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { createMockMapillaryData, setupMockMapillaryData, clearMockMapillaryData } from './helpers/mapillaryMocks';
import { createMockPanoramaxItems, mockPanoramaxSearch } from './helpers/panoramaxMocks';
import { configureSources, ensureHunterMode } from './helpers/sourceHelpers';
import { setMapLocation } from './helpers/mapSetup';
import { setDelay, clearDelays } from './helpers/debugFaults';

/**
 * Sources load independently: each one's markers go on the map as soon as it
 * answers, instead of after the slowest one. The Hillview stream is slowed
 * server-side (debug delay knob); mocked Mapillary answers at once.
 */

const CENTER = { lat: 50.0755, lng: 14.4378 }; // Prague, where the Mapillary mock helper puts its photos

// data-source lives on the inner .marker-container, not on the icon wrapper
const markers = (page: any, source: string) => page.locator(`.optimized-photo-marker:visible:has(.marker-container[data-source="${source}"])`);
const spinner = (page: any, source: string) => page.locator(`[data-testid="source-toggle-${source}"] .source-spinner`);

test.describe.configure({ mode: 'serial' });
test.describe('Sources load independently', () => {
  test.beforeEach(async ({ page }) => {
    await clearDelays();
    await clearMockMapillaryData(page);
  });

  test.afterEach(async ({ page }) => {
    await clearDelays();
    await clearMockMapillaryData(page);
  });

  test('Mapillary markers land while a slow Hillview is still loading, and survive its completion', async ({ page }) => {
    const HILLVIEW_DELAY_S = 8;
    await setupMockMapillaryData(page, createMockMapillaryData(CENTER.lat, CENTER.lng, 15));
    await setDelay('hillview_stream', HILLVIEW_DELAY_S);

    await page.goto('/');
    await page.waitForSelector('.leaflet-container', { timeout: T(10000) });
    await page.waitForSelector('.source-buttons-group', { timeout: T(5000) });
    await setMapLocation(page, CENTER.lat, CENTER.lng, 16);
    await configureSources(page, { hillview: true, mapillary: true, panoramax: false });

    // Mapillary answers immediately — its markers must not wait for Hillview.
    await expect(markers(page, 'mapillary')).toHaveCount(15, { timeout: T(6000) });
    // …and Hillview really is still in flight at that moment.
    await expect(spinner(page, 'hillview')).toBeVisible();

    // Hillview settles later; the Mapillary markers are still there (no blanking, no rebuild flicker).
    await expect(spinner(page, 'hillview')).toBeHidden({ timeout: T((HILLVIEW_DELAY_S + 10) * 1000) });
    await expect(markers(page, 'mapillary')).toHaveCount(15);
  });

  // The two tests that want the source in its shipped state (on) rather than the
  // suite-wide off. See fixtures.ts for why every other test turns it off.
  test.describe('with the source at its real default', () => {
    test.use({ panoramaxDefault: true });

    test('Panoramax markers come from the (mocked) instance', async ({ page, browserName }) => {
      // WebKit fetches this from the photo worker, where Playwright cannot route
      // the request (probed on 1.59.1), so the mock below would be ignored and the
      // assertion would count whatever the public instance happens to hold today.
      test.skip(browserName === 'webkit', 'page.route cannot intercept worker requests in WebKit');
      const items = createMockPanoramaxItems(CENTER.lat, CENTER.lng, 5);
      await mockPanoramaxSearch(page, items);

      await page.goto('/');
      await page.waitForSelector('.leaflet-container', { timeout: T(10000) });
      await page.waitForSelector('.source-buttons-group', { timeout: T(5000) });
      await setMapLocation(page, CENTER.lat, CENTER.lng, 16);
      await configureSources(page, { hillview: false, mapillary: false, panoramax: true });

      await expect(markers(page, 'panoramax')).toHaveCount(5, { timeout: T(20000) });
      await expect(spinner(page, 'panoramax')).toBeHidden();
    });

    test('Panoramax is on by default for a fresh visitor', async ({ page }) => {
      await page.goto('/');
      await page.evaluate(() => localStorage.clear());
      await page.goto('/');
      await page.waitForSelector('.source-buttons-group', { timeout: T(10000) });
      await ensureHunterMode(page, true);

      await expect(page.locator('[data-testid="source-toggle-panoramax"]')).toHaveClass(/active/);
      await expect(page.locator('[data-testid="source-toggle-hillview"]')).toHaveClass(/active/);
      await expect(page.locator('[data-testid="source-toggle-mapillary"]')).not.toHaveClass(/active/);
    });
  });
});
