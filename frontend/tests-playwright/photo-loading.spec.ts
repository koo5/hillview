import { test, expect } from './fixtures';
import { configureSources } from './helpers/sourceHelpers';
import { setupDefaultMockMapillaryData, clearMockMapillaryData } from './helpers/mapillaryMocks';
import { setMapLocation } from './helpers/mapSetup';

test.describe('Photo Loading and Display', () => {
  test.beforeEach(async ({ page }) => {
    // Clear any existing mock data first
    await clearMockMapillaryData(page);

    // Navigate to the main page
    await page.goto('/');

    // Wait for initial setup
    await page.waitForTimeout(3000);
  });

  test('should display photo markers on the map', async ({ page }) => {
    // Wait for initial map load
    await page.waitForSelector('.leaflet-container', { timeout: 11*10000 });
    await page.waitForSelector('.source-buttons-group', { timeout: 11*5000 });

    // Set up mock Mapillary data (default location is Prague: 50.0755, 14.4378)
    await setupDefaultMockMapillaryData(page);

    // Navigate map to where mock data is located
    await setMapLocation(page, 50.0755, 14.4378, 16);

    // Enable Mapillary source to load the mock data
    await configureSources(page, {
      'mapillary': true
    });

    // Wait for sources to load and photos to appear (poll instead of fixed timeout)
    await page.locator('.optimized-photo-marker:visible').first().waitFor({ state: 'visible', timeout: 11*20000 });

    // Look for photo markers on the map
    const leafletMarkers = page.locator('.optimized-photo-marker:visible');

    // Count the markers
    const markerCount = await leafletMarkers.count();
    console.log(`🗺️ Found ${markerCount} photo markers on map`);

    expect(markerCount, 'Expected photo markers to be visible on the map').toBeGreaterThan(0);

    // Check if markers are actually visible
    if (markerCount > 0) {
      const firstMarker = leafletMarkers.first();
      await expect(firstMarker).toBeVisible();

      // Check marker positioning
      const boundingBox = await firstMarker.boundingBox();
      expect(boundingBox, 'Marker should have valid positioning').not.toBeNull();
    }
  });

  test('should show photos in the gallery', async ({ page }) => {
    // Load deterministic mock photos before asserting anything. Without setup the
    // page has no photos at the default view, and the previous selector matched
    // `img[src*="png"]` — which also matches leaflet map tiles — so `.first()`
    // could resolve to a hidden tile and flake. Mirror the marker test's setup so
    // there is a real photo to display.
    await page.waitForSelector('.leaflet-container', { timeout: 11*10000 });
    await page.waitForSelector('.source-buttons-group', { timeout: 11*5000 });

    await setupDefaultMockMapillaryData(page);
    await setMapLocation(page, 50.0755, 14.4378, 16);
    await configureSources(page, { 'mapillary': true });

    // Photos render on the map as markers; assert at least one is actually visible
    // (scoped to the photo-marker class, never map tiles).
    const photoMarkers = page.locator('.optimized-photo-marker:visible');
    await photoMarkers.first().waitFor({ state: 'visible', timeout: 11*20000 });

    const markerCount = await photoMarkers.count();
    console.log(`🖼️ Found ${markerCount} photos shown on the map`);
    expect(markerCount, 'Expected photos to be displayed').toBeGreaterThan(0);
    await expect(photoMarkers.first()).toBeVisible();
  });
});
