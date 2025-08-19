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

  test('should load photos from data sources', async ({ page }) => {
    const consoleMessages: string[] = [];
    
    page.on('console', (msg) => {
      consoleMessages.push(`[${msg.type()}] ${msg.text()}`);
    });

    // Wait for photo loading
    await page.waitForTimeout(5000);

    // Check console messages for photo loading indicators (now from worker)
    const photoLoadMessages = consoleMessages.filter(msg => 
      msg.includes('Worker: Loaded') && msg.includes('photos from') || 
      msg.includes('Worker: Total loaded') ||
      msg.includes('Updated') && msg.includes('markers')
    );

    console.log('📸 Photo loading messages:');
    photoLoadMessages.forEach(msg => console.log(`  ${msg}`));

    // Check if photos were actually loaded by worker
    const workerLoadedMessage = consoleMessages.find(msg => 
      msg.includes('Worker: Loaded') && msg.includes('photos from')
    );
    
    if (workerLoadedMessage) {
      const photosCount = parseInt(workerLoadedMessage.match(/(\d+) photos from/)?.[1] || '0');
      console.log(`📊 Worker loaded: ${photosCount} photos`);
      
      expect(photosCount, 'Expected photos to be loaded by worker from data sources').toBeGreaterThan(0);
    } else {
      console.log('❌ No worker photo loading message found');
      expect(false, 'No worker photo loading message found in console').toBe(true);
    }

    // Check marker updates
    const markerMessages = consoleMessages.filter(msg => 
      msg.includes('Updated') && msg.includes('markers')
    );
    
    console.log('🎯 Marker update messages:');
    markerMessages.forEach(msg => console.log(`  ${msg}`));

    // At least one marker update should show > 0 markers
    const hasVisibleMarkers = markerMessages.some(msg => {
      const match = msg.match(/Updated (\d+).*markers/);
      return match && parseInt(match[1]) > 0;
    });

    expect(hasVisibleMarkers, 'Expected at least some photo markers to be visible on map').toBe(true);
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
          console.log(`  Image ${i}: src="${src}", alt="${alt}"`);
        }
      }

      // This test should fail if no photos are found
      expect(photoCount, 'No photos found in gallery - this indicates a photo loading issue').toBeGreaterThan(0);
    }
  });

  test('should have working photo data sources', async ({ page }) => {
    const consoleMessages: string[] = [];
    const networkRequests: string[] = [];
    
    page.on('console', (msg) => {
      consoleMessages.push(msg.text());
    });

    page.on('request', (request) => {
      const url = request.url();
      if (url.includes('.json') || url.includes('files') || url.includes('photo')) {
        networkRequests.push(`${request.method()} ${url}`);
      }
    });

    page.on('response', (response) => {
      const url = response.url();
      if (url.includes('.json') || url.includes('files') || url.includes('photo')) {
        networkRequests.push(`RESPONSE ${response.status()} ${url}`);
      }
    });

    // Wait for photo loading
    await page.waitForTimeout(5000);

    console.log('🌐 Network requests for photo data:');
    networkRequests.forEach(req => console.log(`  ${req}`));

    console.log('📋 Relevant console messages:');
    const relevantMessages = consoleMessages.filter(msg => 
      msg.includes('source') || 
      msg.includes('photo') || 
      msg.includes('fetch') ||
      msg.includes('enabled') ||
      msg.includes('hillview') ||
      msg.includes('device') ||
      msg.includes('mapillary')
    );
    relevantMessages.forEach(msg => console.log(`  ${msg}`));

    // Check if sources are enabled
    const sourcesMessages = consoleMessages.filter(msg => 
      msg.includes('sources changed') || msg.includes('source')
    );

    expect(sourcesMessages.length, 'Expected photo sources to be configured').toBeGreaterThan(0);

    // Log sources state for debugging
    const sourceInfo = await page.evaluate(() => {
      // Access sources if available in global scope
      return (window as any).debugSources || 'Sources not available in global scope';
    });
    
    console.log('📊 Sources debug info:', sourceInfo);
  });

  test('should show photo count information', async ({ page }) => {
    // Wait for loading
    await page.waitForTimeout(5000);

    // Look for any text that shows photo counts
    const photoCountElements = page.locator('text=/\\d+\\s*(photo|image)/i');
    const countElementsFound = await photoCountElements.count();

    if (countElementsFound > 0) {
      for (let i = 0; i < countElementsFound; i++) {
        const element = photoCountElements.nth(i);
        const text = await element.textContent();
        console.log(`📊 Found photo count display: "${text}"`);
      }
    } else {
      console.log('📊 No photo count displays found on page');
    }

    // Look for debug overlay or status information
    const debugToggle = page.locator('.debug-toggle, [data-testid="debug-toggle"]');
    if (await debugToggle.isVisible()) {
      await debugToggle.click();
      await page.waitForTimeout(1000);
      
      // Look for debug information
      const debugText = await page.locator('.debug-overlay, .debug-info').textContent();
      if (debugText) {
        console.log('🔍 Debug overlay content:', debugText);
      }
    }
  });
});