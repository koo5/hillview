import { test, expect } from '@playwright/test';

test.describe('Enhanced Debug Page', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the main page
    await page.goto('/');
    
    // Wait for the app to load
    await page.waitForLoadState('networkidle');
    
    // Wait for map to be ready
    await page.waitForSelector('.leaflet-container', { timeout: 10000 });
  });

  test('should show enhanced debug information in mode 2', async ({ page }) => {
    // Enable debug mode 2 (press Ctrl+Shift+D twice)
    await page.keyboard.press('Control+Shift+D');
    await page.waitForTimeout(100);
    await page.keyboard.press('Control+Shift+D');
    await page.waitForTimeout(500);

    // Check if debug overlay is visible
    const debugOverlay = page.locator('.debug-overlay');
    await expect(debugOverlay).toBeVisible();

    // Check for photo statistics section
    const photoStatsSection = page.locator('.photo-counts-section');
    await expect(photoStatsSection).toBeVisible();
    
    // Check for specific photo statistics
    const visiblePhotosLabel = page.locator('text=Visible Photos:');
    await expect(visiblePhotosLabel).toBeVisible();
    
    const photosInRangeLabel = page.locator('text=Photos in Range:');
    await expect(photosInRangeLabel).toBeVisible();
    
    const rangeAreaLabel = page.locator('text=Range Area:');
    await expect(rangeAreaLabel).toBeVisible();

    // Check for sources status section
    const sourcesSection = page.locator('.sources-section');
    await expect(sourcesSection).toBeVisible();
    
    const sourcesStatusHeader = page.locator('text=🔄 Sources Status:');
    await expect(sourcesStatusHeader).toBeVisible();

    // Check for Mapillary cache details section
    const mapillaryCacheSection = page.locator('.mapillary-section');
    await expect(mapillaryCacheSection).toBeVisible();
    
    const mapillaryCacheHeader = page.locator('text=🗺️ Mapillary Cache Details:');
    await expect(mapillaryCacheHeader).toBeVisible();

    // Check for cache status grid elements
    const cacheStatusLabel = page.locator('.cache-label', { hasText: 'Status:' });
    await expect(cacheStatusLabel).toBeVisible();
    
    const uncachedRegionsLabel = page.locator('text=Uncached Regions:');
    await expect(uncachedRegionsLabel).toBeVisible();
    
    const livePhotosLabel = page.locator('text=Live Photos:');
    await expect(livePhotosLabel).toBeVisible();
    
    const streamPhaseLabel = page.locator('text=Stream Phase:');
    await expect(streamPhaseLabel).toBeVisible();
  });

  test('should show source loading status indicators', async ({ page }) => {
    // Enable debug mode 2
    await page.keyboard.press('Control+Shift+D');
    await page.waitForTimeout(100);
    await page.keyboard.press('Control+Shift+D');
    await page.waitForTimeout(500);

    // Check for source status indicators
    const sourceStatuses = page.locator('.source-status');
    const sourceCount = await sourceStatuses.count();
    expect(sourceCount).toBeGreaterThanOrEqual(2); // Should have Hillview, Mapillary, and Device sources

    // Check for source names
    const hillviewSource = page.locator('.source-name', { hasText: 'Hillview' });
    await expect(hillviewSource).toBeVisible();
    
    const mapillarySource = page.locator('.source-name', { hasText: 'Mapillary' });
    await expect(mapillarySource).toBeVisible();
    
    const deviceSource = page.locator('.source-name', { hasText: 'My Device' });
    await expect(deviceSource).toBeVisible();

    // Check for enabled/disabled indicators
    const enabledIndicators = page.locator('.source-enabled');
    const indicatorCount = await enabledIndicators.count();
    expect(indicatorCount).toBeGreaterThanOrEqual(3);
  });

  test('should display photo count statistics', async ({ page }) => {
    // Enable debug mode 2
    await page.keyboard.press('Control+Shift+D');
    await page.waitForTimeout(100);
    await page.keyboard.press('Control+Shift+D');
    await page.waitForTimeout(500);

    // Wait a bit for any photos to load
    await page.waitForTimeout(2000);

    // Check that photo statistics are displayed with numeric values
    const statValues = page.locator('.stat-value');
    const valueCount = await statValues.count();
    expect(valueCount).toBeGreaterThanOrEqual(3); // Should have at least 3 stat values

    // Verify the values are numeric (or at least not empty)
    for (let i = 0; i < valueCount; i++) {
      const value = await statValues.nth(i).textContent();
      expect(value).toBeTruthy();
      expect(value?.trim()).not.toBe('');
    }
  });

  test('should handle debug mode cycling correctly', async ({ page }) => {
    // Start with no debug overlay
    let debugOverlay = page.locator('.debug-overlay');
    await expect(debugOverlay).not.toBeVisible();

    // Cycle through debug modes
    await page.keyboard.press('Control+Shift+D'); // Mode 1
    await page.waitForTimeout(200);
    await expect(debugOverlay).toBeVisible();

    await page.keyboard.press('Control+Shift+D'); // Mode 2
    await page.waitForTimeout(200);
    await expect(debugOverlay).toBeVisible();
    
    // Check that we're in mode 2 (should show photo statistics)
    const photoStatsSection = page.locator('.photo-counts-section');
    await expect(photoStatsSection).toBeVisible();

    await page.keyboard.press('Control+Shift+D'); // Mode 3
    await page.waitForTimeout(200);
    await expect(debugOverlay).toBeVisible();
    
    // Mode 3 should not show photo statistics section
    await expect(photoStatsSection).not.toBeVisible();

    await page.keyboard.press('Control+Shift+D'); // Back to Mode 0 (off)
    await page.waitForTimeout(200);
    await expect(debugOverlay).not.toBeVisible();
  });
});