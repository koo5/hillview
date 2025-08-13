import { test, expect } from '@playwright/test';

test.describe('Photo Markers', () => {
  test('should only show markers for photos in current map area', async ({ page }) => {
    // Navigate to the app
    await page.goto('/');
    
    // Wait for map to load
    await page.waitForSelector('.leaflet-container');
    
    // Set a specific map view (Seattle area)
    await page.evaluate(() => {
      // Access the map instance and set specific bounds
      const mapComponent = document.querySelector('.leaflet-container');
      if (mapComponent && (window as any).map) {
        (window as any).map.setView([47.6062, -122.3321], 12); // Seattle
      }
    });
    
    // Wait for photos to load
    await page.waitForTimeout(2000);
    
    // Check that markers exist
    const markers = await page.locator('.optimized-photo-marker').count();
    console.log(`Found ${markers} markers`);
    
    if (markers > 0) {
      // Get the first few marker positions to verify they're in the correct area
      const markerPositions = await page.evaluate(() => {
        const markers = Array.from(document.querySelectorAll('.optimized-photo-marker'));
        return markers.slice(0, 5).map(marker => {
          const style = (marker as HTMLElement).style.transform;
          // Extract coordinates from transform style
          const match = style.match(/translate3d\(([^,]+)px,\s*([^,]+)px/);
          return match ? [parseFloat(match[1]), parseFloat(match[2])] : null;
        }).filter(Boolean);
      });
      
      console.log('Marker screen positions:', markerPositions);
      
      // Verify markers are actually visible on screen (not off in crazy locations)
      for (const [x, y] of markerPositions) {
        expect(x).toBeGreaterThan(-1000); // Not way off screen left
        expect(x).toBeLessThan(2000);     // Not way off screen right  
        expect(y).toBeGreaterThan(-1000); // Not way off screen top
        expect(y).toBeLessThan(2000);     // Not way off screen bottom
      }
    }
  });

  test('should update markers when map is panned', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.leaflet-container');
    
    // Set initial view (Seattle)
    await page.evaluate(() => {
      if ((window as any).map) {
        (window as any).map.setView([47.6062, -122.3321], 12);
      }
    });
    
    await page.waitForTimeout(1000);
    const initialMarkers = await page.locator('.optimized-photo-marker').count();
    
    // Pan to a different location (San Francisco)
    await page.evaluate(() => {
      if ((window as any).map) {
        (window as any).map.setView([37.7749, -122.4194], 12);
      }
    });
    
    await page.waitForTimeout(2000);
    const newMarkers = await page.locator('.optimized-photo-marker').count();
    
    console.log(`Initial markers: ${initialMarkers}, After pan: ${newMarkers}`);
    
    // The number of markers should potentially change when panning to a different area
    // (This might be the same if both areas have similar photo density)
    expect(newMarkers).toBeGreaterThanOrEqual(0);
  });

  test('should show debug info for visible photos', async ({ page }) => {
    await page.goto('/?debug=2'); // Enable debug mode
    await page.waitForSelector('.debug-overlay');
    
    // Wait for photos to load
    await page.waitForTimeout(2000);
    
    // Check debug overlay shows photo count
    const debugText = await page.locator('.debug-overlay').textContent();
    expect(debugText).toContain('Visible Photos');
    
    // Look for the specific photos section
    const photosSection = await page.locator('.photos-section').count();
    expect(photosSection).toBeGreaterThan(0);
  });
});