import { test, expect } from '@playwright/test';

/**
 * Test for Mapillary marker rendering consistency with mocked data
 * Based on backend test mocking approach in backend/tests/test_mapillary_filtering.py
 */

// Mock data similar to backend tests - 15 photos in Prague area
const createMockMapillaryData = (centerLat = 50.0755, centerLng = 14.4378) => {
  const baseLatitude = centerLat;
  const baseLongitude = centerLng;
  const photos = [];
  
  for (let i = 1; i <= 15; i++) {
    // Distribute photos in a small area - use deterministic positions for consistent testing
    const angle = (i * 24) % 360; // Distribute in a circle
    const distance = 0.002 * ((i % 3) + 1); // Three concentric circles
    const latOffset = distance * Math.sin(angle * Math.PI / 180);
    const lngOffset = distance * Math.cos(angle * Math.PI / 180);
    
    photos.push({
      id: `mock_mapillary_${i.toString().padStart(3, '0')}`,
      geometry: {
        type: "Point",
        coordinates: [baseLongitude + lngOffset, baseLatitude + latOffset]
      },
      compass_angle: (i * 24) % 360, // Vary angles
      computed_compass_angle: (i * 24) % 360,
      computed_rotation: 0.0,
      computed_altitude: 200.0 + (i * 10),
      captured_at: `2024-01-15T${String(10 + (i % 12)).padStart(2, '0')}:30:00Z`,
      is_pano: false,
      thumb_1024_url: `https://mock.mapillary.com/thumb${i.toString().padStart(3, '0')}.jpg`,
      creator: {
        username: `mock_creator_${((i - 1) % 3) + 1}`,
        id: `mock_creator_${((i - 1) % 3) + 1}`
      }
    });
  }
  
  return { data: photos };
};

// Helper function to set mock data via backend debug endpoint
async function setMockMapillaryData(page: any, mockData: any) {
  const response = await page.request.post('http://localhost:8055/api/debug/mock-mapillary', {
    data: mockData
  });
  
  if (response.status() !== 200) {
    throw new Error(`Failed to set mock data: ${response.status()}`);
  }
  
  const result = await response.json();
  console.log(`✓ Set mock Mapillary data: ${result.details.photos_count} photos`);
  return result;
}

// Helper function to clear mock data and cache
async function clearMockMapillaryData(page: any) {
  try {
    // Clear mock data
    const mockResponse = await page.request.delete('http://localhost:8055/api/debug/mock-mapillary');
    if (mockResponse.status() === 200) {
      console.log('✓ Cleared mock Mapillary data');
    }
    
    // Clear database/cache to force fresh requests
    const cacheResponse = await page.request.post('http://localhost:8055/api/debug/clear-database');
    if (cacheResponse.status() === 200) {
      console.log('✓ Cleared database/cache');
    }
  } catch (e) {
    console.log('⚠ Could not clear data:', (e as Error).message);
  }
}

// Helper function to configure sources
async function configureSources(page: any, config: { [sourceName: string]: boolean }) {
  console.log('🔧 Configuring sources:', config);
  
  await page.waitForTimeout(1000);
  
  const sourceButtonsContainer = page.locator('.source-buttons-container');
  await sourceButtonsContainer.waitFor({ state: 'visible', timeout: 5000 });
  
  // Expand source buttons if in compact mode
  try {
    const compactToggle = sourceButtonsContainer.locator('button.toggle-compact');
    await compactToggle.waitFor({ state: 'visible', timeout: 2000 });
    
    const isCompact = await compactToggle.evaluate((el: HTMLElement) => el.classList.contains('active'));
    if (isCompact) {
      await compactToggle.click();
      await page.waitForTimeout(500);
    }
  } catch (e) {
    // Try hover method if compact toggle not found
    try {
      await sourceButtonsContainer.hover();
      await page.waitForTimeout(500);
    } catch (e2) {
      // Continue if neither method works
    }
  }
  
  // Configure each source
  for (const [sourceName, shouldBeEnabled] of Object.entries(config)) {
    try {
      const sourceButton = sourceButtonsContainer
        .locator('button')
        .filter({ hasText: new RegExp(sourceName, 'i') })
        .or(sourceButtonsContainer.locator(`button[title*="${sourceName}"]`));
      
      const isCurrentlyActive = await sourceButton.evaluate(el => el.classList.contains('active'));
      
      if (isCurrentlyActive !== shouldBeEnabled) {
        await sourceButton.click();
        const action = shouldBeEnabled ? 'Enabled' : 'Disabled';
        console.log(`${action === 'Enabled' ? '🌍' : '🔘'} ${action} ${sourceName} source`);
        await page.waitForTimeout(500);
      }
    } catch (e) {
      console.log(`⚠️ Could not configure ${sourceName} source: ${(e as Error).message}`);
    }
  }
  
  await page.waitForTimeout(2000); // Wait for source changes to propagate
}

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
  return await page.locator('.optimized-photo-marker').count();
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
    // Based on observed backend logs: lat ~50.114, lng ~14.523
    const mockData = createMockMapillaryData(50.114, 14.523);
    await setMockMapillaryData(page, mockData);
    
    // Set map to that area first
    await setMapLocation(page, 50.114, 14.523, 16);
    await page.waitForTimeout(2000);
    
    // Configure sources: disable all except Mapillary (this will trigger API request)
    await configureSources(page, {
      'Hillview': false,
      'My Device': false,
      'Mapillary': true
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
    
    // Set up mock data
    const mockData = createMockMapillaryData();
    await setMockMapillaryData(page, mockData);
    
    // Set map location
    await setMapLocation(page, 50.0755, 14.4378, 16);
    
    // Initially disable all sources
    await configureSources(page, {
      'Hillview': false,
      'My Device': false,
      'Mapillary': false
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
      await configureSources(page, { 'Mapillary': true });
      await page.waitForTimeout(3000); // Wait for markers to render
      
      const enabledMarkerCount = await countVisibleMarkers(page);
      console.log(`  📍 Markers after enabling: ${enabledMarkerCount}`);
      toggleResults.push(enabledMarkerCount);
      
      // Verify we get the expected number of markers
      expect(enabledMarkerCount).toBe(expectedMarkerCount);
      
      // Disable Mapillary
      await configureSources(page, { 'Mapillary': false });
      await page.waitForTimeout(2000); // Wait for markers to disappear
      
      const disabledMarkerCount = await countVisibleMarkers(page);
      console.log(`  📍 Markers after disabling: ${disabledMarkerCount}`);
      
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
    
    // Set up mock data
    const mockData = createMockMapillaryData();
    await setMockMapillaryData(page, mockData);
    
    // Enable only Mapillary
    await configureSources(page, {
      'Hillview': false,
      'My Device': false,
      'Mapillary': true
    });
    
    // Start at center of Prague (should see all 15 markers)
    await setMapLocation(page, 50.0755, 14.4378, 16);
    await page.waitForTimeout(3000);
    
    const initialMarkerCount = await countVisibleMarkers(page);
    console.log(`📍 Initial markers at center: ${initialMarkerCount}`);
    expect(initialMarkerCount).toBe(15);
    
    // Pan to slightly northeast within the mock data area
    await setMapLocation(page, 50.0760, 14.4383, 16);
    await page.waitForTimeout(3000);
    
    const panMarkerCount = await countVisibleMarkers(page);
    console.log(`📍 Markers after small pan: ${panMarkerCount}`);
    
    // Should still see all markers since we're within the same area
    expect(panMarkerCount).toBe(15);
    
    // Pan to an area outside the mock data (should see 0 markers)
    await setMapLocation(page, 50.1, 14.5, 16); // Further away
    await page.waitForTimeout(3000);
    
    const outsideMarkerCount = await countVisibleMarkers(page);
    console.log(`📍 Markers outside mock area: ${outsideMarkerCount}`);
    expect(outsideMarkerCount).toBe(0);
    
    // Pan back to original area (should see all 15 again)
    await setMapLocation(page, 50.0755, 14.4378, 16);
    await page.waitForTimeout(3000);
    
    const returnMarkerCount = await countVisibleMarkers(page);
    console.log(`📍 Markers after returning: ${returnMarkerCount}`);
    expect(returnMarkerCount).toBe(15);
    
    console.log('✅ Map panning correctly filters markers based on geographic bounds');
  });

  test('should handle rapid Mapillary toggles without losing markers', async ({ page }) => {
    console.log('🧪 Testing rapid Mapillary toggles (stress test)');
    
    // Set up mock data
    const mockData = createMockMapillaryData();
    await setMockMapillaryData(page, mockData);
    
    await setMapLocation(page, 50.0755, 14.4378, 16);
    
    // Initially disable Mapillary
    await configureSources(page, {
      'Hillview': false,
      'My Device': false,
      'Mapillary': false
    });
    
    // Perform rapid toggles with shorter waits
    const rapidToggleResults: number[] = [];
    
    for (let i = 0; i < 10; i++) {
      // Quick enable
      await configureSources(page, { 'Mapillary': true });
      await page.waitForTimeout(1500); // Shorter wait
      
      const markerCount = await countVisibleMarkers(page);
      rapidToggleResults.push(markerCount);
      console.log(`🔄 Rapid toggle ${i + 1}: ${markerCount} markers`);
      
      // Quick disable
      await configureSources(page, { 'Mapillary': false });
      await page.waitForTimeout(500); // Very short wait
    }
    
    // Final enable to check end state
    await configureSources(page, { 'Mapillary': true });
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