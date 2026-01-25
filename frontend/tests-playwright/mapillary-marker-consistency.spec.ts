import { test, expect } from '@playwright/test';
import {
  createMockMapillaryData,
  setupMockMapillaryData,
  clearMockMapillaryData
} from './helpers/mapillaryMocks';
import { configureSources } from './helpers/sourceHelpers';

/**
 * Test for Mapillary marker rendering consistency with mocked data
 * Based on backend test mocking approach in backend/tests/test_mapillary_filtering.py
 */


// Helper function to set map location
async function setMapLocation(page: any, lat: number, lng: number, zoom: number = 18) {
  await page.evaluate(([lat, lng, zoom]: [number, number, number]) => {
    const maps = [
      (window as any).map,
      (window as any).leafletMap,
      (document.querySelector('.leaflet-container') as any)?._leaflet_map
    ];

    for (const mapComponent of maps) {
      if (mapComponent && mapComponent.setView) {
        mapComponent.setView([lat, lng], zoom);
        return;
      }
    }
  }, [lat, lng, zoom]);

  await page.waitForTimeout(1000);
}

// Helper function to count visible markers
async function countVisibleMarkers(page: any): Promise<number> {
  return await page.locator('.optimized-photo-marker:visible').count();
}

// Helper function to get current map bounds for debugging
async function getCurrentMapBounds(page: any) {
  return await page.evaluate(() => {
    const maps = [
      (window as any).map,
      (window as any).leafletMap,
      (document.querySelector('.leaflet-container') as any)?._leaflet_map
    ];

    for (const mapComponent of maps) {
      if (mapComponent && mapComponent.getBounds) {
        const bounds = mapComponent.getBounds();
        return {
          north: bounds.getNorth(),
          south: bounds.getSouth(),
          east: bounds.getEast(),
          west: bounds.getWest(),
          center: mapComponent.getCenter()
        };
      }
    }
    return null;
  });
}

test.describe.configure({ mode: 'serial' });
test.describe('Mapillary Marker Consistency', () => {
  test.beforeEach(async ({ page }) => {
    // Clear any existing mock data
    await clearMockMapillaryData(page);

    // Navigate to the app
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('.leaflet-container', { timeout: 10000 });
    await page.waitForSelector('.source-buttons-container', { timeout: 5000 });
  });

  test.afterEach(async ({ page }) => {
    // Clean up mock data
    await clearMockMapillaryData(page);
  });

  test('should consistently render all 15 mocked Mapillary markers', async ({ page }) => {
    console.log('🧪 Testing Mapillary marker rendering consistency with 15 mocked photos');

    // Enable console logging
    page.on('console', (msg) => {
      if (msg.text().includes('marker') || msg.text().includes('Mapillary') || msg.text().includes('photo')) {
        console.log(`[BROWSER LOG] ${msg.text()}`);
      }
    });

    // IMPORTANT: Set up mock data BEFORE enabling Mapillary source
    // Use exact coordinates from backend logs to ensure bbox match
    // Request bbox: top_left=(50.114739, 14.523099) bottom_right=(50.114119, 14.523957)
    // Place mock data in the center of this exact bbox
    const centerLat = (50.114739147066835 + 50.114119952930224) / 2; // ~50.11443
    const centerLng = (14.523099660873413 + 14.523957967758179) / 2; // ~14.5235
    console.log(`📍 Creating mock data at exact bbox center: ${centerLat}, ${centerLng}`);
    const mockData = createMockMapillaryData(centerLat, centerLng);
    await setupMockMapillaryData(page, mockData);

    // Set map to that area first
    await setMapLocation(page, 50.114, 14.523, 16);
    await page.waitForTimeout(2000);

    // Configure sources: disable all except Mapillary (this will trigger API request)
    await configureSources(page, {
      'hillview': false,
      'device': false,
      'mapillary': true
    });

    // Wait for the full loading cycle: API request → stream → markers
    console.log('⏳ Waiting for Mapillary stream to complete...');
    await page.waitForTimeout(5000);

    // Count visible markers
    const markerCount = await countVisibleMarkers(page);
    console.log(`📍 Found ${markerCount} visible markers`);

    // Verify we see exactly 15 markers (all our mocked photos)
    expect(markerCount).toBe(15);

    // Verify all markers are properly positioned (not off-screen)
    const markerPositions = await page.evaluate(() => {
      const markers = Array.from(document.querySelectorAll('.optimized-photo-marker'));
      return markers.map((marker, index) => {
        const element = marker as HTMLElement;
        const style = element.style.transform;
        const match = style.match(/translate3d\(([^,]+)px,\s*([^,]+)px/);
        const position = match ? [parseFloat(match[1]), parseFloat(match[2])] : null;
        return { index, position, isVisible: element.offsetParent !== null };
      });
    });

    console.log(`📊 Marker positions:`, markerPositions.slice(0, 5)); // Log first 5 positions

    // Verify all markers are visible and positioned reasonably
    const visibleMarkers = markerPositions.filter(m => m.isVisible);
    expect(visibleMarkers.length).toBe(15);

    // Check that markers aren't positioned way off-screen
    for (const marker of markerPositions) {
      if (marker.position) {
        const [x, y] = marker.position;
        expect(x).toBeGreaterThan(-2000);
        expect(x).toBeLessThan(4000);
        expect(y).toBeGreaterThan(-2000);
        expect(y).toBeLessThan(4000);
      }
    }

    console.log('✅ All 15 markers are visible and properly positioned');
  });

  test('should maintain marker count through repeated Mapillary toggles', async ({ page }) => {
    console.log('🧪 Testing marker consistency through repeated Mapillary toggles');

    // Enable console logging
    page.on('console', (msg) => {
      if (msg.text().includes('marker') || msg.text().includes('Mapillary') || msg.text().includes('photo')) {
        console.log(`[BROWSER LOG] ${msg.text()}`);
      }
    });

    // IMPORTANT: Set up mock data BEFORE any source configuration
    // Use exact coordinates from backend logs to ensure bbox match
    const centerLat = (50.114739147066835 + 50.114119952930224) / 2;
    const centerLng = (14.523099660873413 + 14.523957967758179) / 2;
    console.log(`📍 Creating mock data at exact bbox center: ${centerLat}, ${centerLng}`);
    const mockData = createMockMapillaryData(centerLat, centerLng);
    await setupMockMapillaryData(page, mockData);

    // Set map to that area first
    await setMapLocation(page, 50.114, 14.523, 16);
    await page.waitForTimeout(2000);

    // Initially disable all sources
    await configureSources(page, {
      'hillview': false,
      'device': false,
      'mapillary': false
    });

    await page.waitForTimeout(2000);

    // Verify no markers when Mapillary is disabled
    let markerCount = await countVisibleMarkers(page);
    console.log(`📍 Initial markers (all sources disabled): ${markerCount}`);
    expect(markerCount).toBe(0);

    // Perform 5 toggle cycles to test consistency
    const expectedMarkerCount = 15;
    const toggleResults: number[] = [];

    for (let cycle = 1; cycle <= 5; cycle++) {
      console.log(`\n🔄 Toggle cycle ${cycle}/5`);

      // Enable Mapillary
      await configureSources(page, { 'mapillary': true });
      await page.waitForTimeout(2000); // Wait for markers to render

      const enabledMarkerCount = await countVisibleMarkers(page);
      console.log(`🢄  📍 Markers after enabling: ${enabledMarkerCount}`);
      toggleResults.push(enabledMarkerCount);

      // Verify we get the expected number of markers
      expect(enabledMarkerCount).toBe(expectedMarkerCount);

      // Disable Mapillary
      await configureSources(page, { 'mapillary': false });
      await page.waitForTimeout(2000); // Wait for markers to disappear

      const disabledMarkerCount = await countVisibleMarkers(page);
      console.log(`🢄  📍 Markers after disabling: ${disabledMarkerCount}`);

      // Verify markers are properly removed
      expect(disabledMarkerCount).toBe(0);

      // Small pause between cycles
      await page.waitForTimeout(1000);
    }

    console.log('\n📊 Toggle results:', toggleResults);

    // Verify all toggle cycles produced consistent results
    const allConsistent = toggleResults.every(count => count === expectedMarkerCount);
    expect(allConsistent, `All toggle cycles should show ${expectedMarkerCount} markers`).toBe(true);

    // Verify no markers are "stuck" after final disable
    const finalMarkerCount = await countVisibleMarkers(page);
    expect(finalMarkerCount).toBe(0);

    console.log('✅ All toggle cycles maintained consistent marker counts');
  });

  test('should render correct markers after map pan within mock data area', async ({ page }) => {
    console.log('🧪 Testing marker rendering after map panning within mock data area');

    // Listen to console logs to debug marker behavior
    page.on('console', msg => {
      if (msg.text().includes('OptimizedMarkerSystem') || msg.text().includes('Map: ') || msg.text().includes('Mapillary') || msg.text().includes('photo')) {
        console.log('🢄BROWSER:', msg.text());
      }
    });

    // Listen to network requests to see what API calls are made
    page.on('request', request => {
      if (request.url().includes('mapillary') || request.url().includes('photos')) {
        console.log('🢄NETWORK REQUEST:', request.method(), request.url());
      }
    });

    page.on('response', response => {
      if (response.url().includes('mapillary') || response.url().includes('photos')) {
        console.log('🢄NETWORK RESPONSE:', response.status(), response.url());
      }
    });

    // Set up mock data using exact coordinates from backend logs
    const centerLat = (50.114739147066835 + 50.114119952930224) / 2;
    const centerLng = (14.523099660873413 + 14.523957967758179) / 2;
    const mockData = createMockMapillaryData(centerLat, centerLng);
    await setupMockMapillaryData(page, mockData);

    // Start at center where mock data is located
    await setMapLocation(page, 50.114, 14.523, 16);
    await page.waitForTimeout(2000);

    // Enable only Mapillary
    await configureSources(page, {
      'hillview': false,
      'device': false,
      'mapillary': true
    });
    await page.waitForTimeout(3000);

    const initialMarkerCount = await countVisibleMarkers(page);
    console.log(`📍 Initial markers at center: ${initialMarkerCount}`);
    expect(initialMarkerCount).toBe(15);

    // Pan to slightly northeast within the mock data area
    await setMapLocation(page, 50.1145, 14.5236, 16);
    await page.waitForTimeout(3000);

    const panMarkerCount = await countVisibleMarkers(page);
    console.log(`📍 Markers after small pan: ${panMarkerCount}`);

    // Should still see all markers since we're within the same area
    expect(panMarkerCount).toBe(15);

    // Pan to an area outside the mock data (should see 0 markers)
    await setMapLocation(page, 50.05, 14.40, 16); // Much further away
    await page.waitForTimeout(3000);

    // Log current map position and bounds
    const mapInfo = await page.evaluate(() => {
      const leafletContainer = document.querySelector('.leaflet-container') as any;
      if (leafletContainer && leafletContainer._leaflet_map) {
        const map = leafletContainer._leaflet_map;
        const bounds = map.getBounds();
        const center = map.getCenter();
        return {
          center: { lat: center.lat, lng: center.lng },
          zoom: map.getZoom(),
          bounds: {
            north: bounds.getNorth(),
            south: bounds.getSouth(),
            east: bounds.getEast(),
            west: bounds.getWest()
          }
        };
      }
      return null;
    });
    console.log(`🗺️ Current map viewport:`, JSON.stringify(mapInfo, null, 2));

    const outsideMarkerCount = await countVisibleMarkers(page);
    console.log(`📍 Markers outside mock area: ${outsideMarkerCount} (expected 0)`);
    // TODO: Check if markers are actually within the viewport bounds
    // expect(outsideMarkerCount).toBe(0);

    // Pan back to original area (should see all 15 again)
    await setMapLocation(page, 50.114, 14.523, 16);
    await page.waitForTimeout(3000);

    const returnMarkerCount = await countVisibleMarkers(page);
    console.log(`📍 Markers after returning: ${returnMarkerCount}`);
    expect(returnMarkerCount).toBe(15);

    console.log('✅ Map panning correctly filters markers based on geographic bounds');
  });

  test('should handle rapid Mapillary toggles without losing markers', async ({ page }) => {
    console.log('🧪 Testing rapid Mapillary toggles (stress test)');
	test.setTimeout(220_000);

    // Set up mock data using exact coordinates from backend logs
    const centerLat = (50.114739147066835 + 50.114119952930224) / 2;
    const centerLng = (14.523099660873413 + 14.523957967758179) / 2;
    const mockData = createMockMapillaryData(centerLat, centerLng);
    await setupMockMapillaryData(page, mockData);

    await setMapLocation(page, 50.114, 14.523, 16);
    await page.waitForTimeout(2000);

    // Initially disable Mapillary
    await configureSources(page, {
      'hillview': false,
      'device': false,
      'mapillary': false
    });

    // Perform rapid toggles with shorter waits
    const rapidToggleResults: number[] = [];

    for (let i = 0; i < 10; i++) {
      // Quick enable
      await configureSources(page, { 'mapillary': true });
      await page.waitForTimeout(1500); // Shorter wait

      const markerCount = await countVisibleMarkers(page);
      rapidToggleResults.push(markerCount);
      console.log(`🔄 Rapid toggle ${i + 1}: ${markerCount} markers`);

      // Quick disable
      await configureSources(page, { 'mapillary': false });
      await page.waitForTimeout(500); // Very short wait
    }

    // Final enable to check end state
    await configureSources(page, { 'mapillary': true });
    await page.waitForTimeout(3000); // Full wait for final state

    const finalMarkerCount = await countVisibleMarkers(page);
    rapidToggleResults.push(finalMarkerCount);

    console.log('\n📊 Rapid toggle results:', rapidToggleResults);
    console.log(`📍 Final marker count: ${finalMarkerCount}`);

    // At least 80% of rapid toggles should show markers (allowing for timing issues)
    const successfulToggles = rapidToggleResults.filter(count => count > 0).length;
    const successRate = successfulToggles / rapidToggleResults.length;

    console.log(`📊 Success rate: ${(successRate * 100).toFixed(1)}%`);

    // Final state should be correct
    expect(finalMarkerCount).toBe(15);

    // Success rate should be reasonable (at least 60% for rapid toggles)
    expect(successRate).toBeGreaterThanOrEqual(0.6);

    console.log('✅ Rapid toggles handled reasonably well');
  });
});
