import { test, expect } from '@playwright/test';

test.describe('Photo Loading and Display', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the main page
    await page.goto('/');

    // Wait for the app to load
    await page.waitForLoadState('networkidle');

    // Wait for initial setup
    await page.waitForTimeout(3000);
  });

  test('should display photo markers on the map', async ({ page }) => {
    // Wait for map and photos to load
    await page.waitForTimeout(5000);

    // Look for Leaflet markers on the map
    const leafletMarkers = page.locator('.leaflet-marker-pane .leaflet-marker-icon');

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
    // Wait for photos to load
    await page.waitForTimeout(5000);

    // Look for photo elements in the gallery
    const photoElements = page.locator('.photo-item, .gallery-photo, [data-testid*="photo"], img[src*="jpg"], img[src*="jpeg"], img[src*="png"]');

    const photoCount = await photoElements.count();
    console.log(`🖼️ Found ${photoCount} photos in gallery`);

    if (photoCount > 0) {
      expect(photoCount, 'Expected photos to be displayed in gallery').toBeGreaterThan(0);

      // Check if first photo is visible
      const firstPhoto = photoElements.first();
      await expect(firstPhoto).toBeVisible();
    } else {
      // If no photos found, log what elements we do have
      const allImages = page.locator('img');
      const imageCount = await allImages.count();
      console.log(`📷 Found ${imageCount} total images on page`);

      if (imageCount > 0) {
        for (let i = 0; i < Math.min(5, imageCount); i++) {
          const img = allImages.nth(i);
          const src = await img.getAttribute('src');
          const alt = await img.getAttribute('alt');
          console.log(`🢄  Image ${i}: src="${src}", alt="${alt}"`);
        }
      }

      // This test should fail if no photos are found
      expect(photoCount, 'No photos found in gallery - this indicates a photo loading issue').toBeGreaterThan(0);
    }
  });
});
