import { test, expect } from '@playwright/test';

test.describe('Map Panning Operations', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    
    // Wait for the map to be loaded and visible
    await page.waitForSelector('.leaflet-container', { timeout: 10000 });
    await page.waitForTimeout(2000); // Allow map to fully initialize
    
    // Ensure we're in the correct view mode
    await expect(page.locator('.leaflet-container')).toBeVisible();
  });

  test('should pan map using mouse drag in all directions', async ({ page }) => {
    const mapContainer = page.locator('.leaflet-container');
    
    // Get the bounding box of the map container
    const mapBounds = await mapContainer.boundingBox();
    expect(mapBounds).not.toBeNull();
    
    if (!mapBounds) return;
    
    const centerX = mapBounds.x + mapBounds.width / 2;
    const centerY = mapBounds.y + mapBounds.height / 2;
    const panDistance = 100;
    
    // Test panning in all four cardinal directions
    const directions = [
      { name: 'right', startX: centerX, startY: centerY, endX: centerX + panDistance, endY: centerY },
      { name: 'left', startX: centerX, startY: centerY, endX: centerX - panDistance, endY: centerY },
      { name: 'down', startX: centerX, startY: centerY, endX: centerX, endY: centerY + panDistance },
      { name: 'up', startX: centerX, startY: centerY, endX: centerX, endY: centerY - panDistance }
    ];
    
    for (const direction of directions) {
      console.log(`Testing pan ${direction.name}...`);
      
      // Perform drag gesture
      await page.mouse.move(direction.startX, direction.startY);
      await page.mouse.down();
      await page.mouse.move(direction.endX, direction.endY, { steps: 10 });
      await page.mouse.up();
      
      // Wait for map to settle
      await page.waitForTimeout(500);
      
      // Verify map is still functional
      await expect(mapContainer).toBeVisible();
    }
  });

  test('should perform diagonal panning movements', async ({ page }) => {
    const mapContainer = page.locator('.leaflet-container');
    const mapBounds = await mapContainer.boundingBox();
    expect(mapBounds).not.toBeNull();
    
    if (!mapBounds) return;
    
    const centerX = mapBounds.x + mapBounds.width / 2;
    const centerY = mapBounds.y + mapBounds.height / 2;
    const panDistance = 80;
    
    // Test diagonal movements
    const diagonalMoves = [
      { name: 'northeast', dx: panDistance, dy: -panDistance },
      { name: 'southeast', dx: panDistance, dy: panDistance },
      { name: 'southwest', dx: -panDistance, dy: panDistance },
      { name: 'northwest', dx: -panDistance, dy: -panDistance }
    ];
    
    for (const move of diagonalMoves) {
      console.log(`Testing diagonal pan ${move.name}...`);
      
      await page.mouse.move(centerX, centerY);
      await page.mouse.down();
      await page.mouse.move(centerX + move.dx, centerY + move.dy, { steps: 8 });
      await page.mouse.up();
      
      await page.waitForTimeout(400);
      await expect(mapContainer).toBeVisible();
    }
  });

  test('should handle rapid successive panning gestures', async ({ page }) => {
    const mapContainer = page.locator('.leaflet-container');
    const mapBounds = await mapContainer.boundingBox();
    expect(mapBounds).not.toBeNull();
    
    if (!mapBounds) return;
    
    const centerX = mapBounds.x + mapBounds.width / 2;
    const centerY = mapBounds.y + mapBounds.height / 2;
    const quickPanDistance = 60;
    
    // Perform 5 rapid pans in different directions
    const rapidPans = [
      { dx: quickPanDistance, dy: 0 },
      { dx: 0, dy: quickPanDistance },
      { dx: -quickPanDistance, dy: 0 },
      { dx: 0, dy: -quickPanDistance },
      { dx: quickPanDistance/2, dy: quickPanDistance/2 }
    ];
    
    for (let i = 0; i < rapidPans.length; i++) {
      const pan = rapidPans[i];
      console.log(`Rapid pan ${i + 1}...`);
      
      await page.mouse.move(centerX, centerY);
      await page.mouse.down();
      await page.mouse.move(centerX + pan.dx, centerY + pan.dy, { steps: 3 });
      await page.mouse.up();
      
      // Very short pause between gestures
      await page.waitForTimeout(100);
    }
    
    // Verify map is still responsive after rapid panning
    await expect(mapContainer).toBeVisible();
  });

  test('should perform smooth continuous panning motion', async ({ page }) => {
    const mapContainer = page.locator('.leaflet-container');
    const mapBounds = await mapContainer.boundingBox();
    expect(mapBounds).not.toBeNull();
    
    if (!mapBounds) return;
    
    const centerX = mapBounds.x + mapBounds.width / 2;
    const centerY = mapBounds.y + mapBounds.height / 2;
    const radius = 80;
    
    // Create a circular panning motion
    const numPoints = 8;
    const points = [];
    for (let i = 0; i < numPoints; i++) {
      const angle = (i * 2 * Math.PI) / numPoints;
      points.push({
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle)
      });
    }
    
    // Start the continuous pan
    await page.mouse.move(points[0].x, points[0].y);
    await page.mouse.down();
    
    // Move through all points
    for (let i = 1; i < points.length; i++) {
      await page.mouse.move(points[i].x, points[i].y, { steps: 5 });
      await page.waitForTimeout(50);
    }
    
    // Complete the circle
    await page.mouse.move(points[0].x, points[0].y, { steps: 5 });
    await page.mouse.up();
    
    await page.waitForTimeout(500);
    await expect(mapContainer).toBeVisible();
  });

  test('should handle touch-based panning on mobile viewport', async ({ browser }) => {
    // Create a new context with touch support enabled
    const context = await browser.newContext({ hasTouch: true });
    const newPage = await context.newPage();
    
    // Set mobile viewport
    await newPage.setViewportSize({ width: 375, height: 667 });
    await newPage.goto('/');
    
    await newPage.waitForSelector('.leaflet-container', { timeout: 10000 });
    await newPage.waitForTimeout(2000);
    
    const mapContainer = newPage.locator('.leaflet-container');
    const mapBounds = await mapContainer.boundingBox();
    expect(mapBounds).not.toBeNull();
    
    if (!mapBounds) return;
    
    const centerX = mapBounds.x + mapBounds.width / 2;
    const centerY = mapBounds.y + mapBounds.height / 2;
    
    // Simulate touch pan gestures
    const touchPans = [
      { name: 'swipe_right', startX: centerX - 50, startY: centerY, endX: centerX + 50, endY: centerY },
      { name: 'swipe_left', startX: centerX + 50, startY: centerY, endX: centerX - 50, endY: centerY },
      { name: 'swipe_up', startX: centerX, startY: centerY + 50, endX: centerX, endY: centerY - 50 },
      { name: 'swipe_down', startX: centerX, startY: centerY - 50, endX: centerX, endY: centerY + 50 }
    ];
    
    for (const pan of touchPans) {
      console.log(`Testing touch ${pan.name}...`);
      
      // Use touch API for more realistic mobile interaction
      await newPage.touchscreen.tap(pan.startX, pan.startY);
      await newPage.waitForTimeout(50);
      
      // Simulate drag
      await newPage.mouse.move(pan.startX, pan.startY);
      await newPage.mouse.down();
      await newPage.mouse.move(pan.endX, pan.endY, { steps: 10 });
      await newPage.mouse.up();
      
      await newPage.waitForTimeout(300);
      await expect(mapContainer).toBeVisible();
    }
    
    // Clean up the context
    await context.close();
  });

  test('should maintain map responsiveness during extended panning session', async ({ page }) => {
    const mapContainer = page.locator('.leaflet-container');
    const mapBounds = await mapContainer.boundingBox();
    expect(mapBounds).not.toBeNull();
    
    if (!mapBounds) return;
    
    const centerX = mapBounds.x + mapBounds.width / 2;
    const centerY = mapBounds.y + mapBounds.height / 2;
    
    // Perform extended panning session (simulating user exploration)
    const extendedPanSequence = [
      { dx: 100, dy: 0 }, { dx: 0, dy: 100 }, { dx: -150, dy: 0 },
      { dx: 0, dy: -120 }, { dx: 80, dy: 80 }, { dx: -60, dy: -60 },
      { dx: 120, dy: -40 }, { dx: -80, dy: 100 }, { dx: 0, dy: -80 }
    ];
    
    for (let i = 0; i < extendedPanSequence.length; i++) {
      const pan = extendedPanSequence[i];
      console.log(`Extended pan sequence ${i + 1}/${extendedPanSequence.length}...`);
      
      await page.mouse.move(centerX, centerY);
      await page.mouse.down();
      await page.mouse.move(centerX + pan.dx, centerY + pan.dy, { steps: 8 });
      await page.mouse.up();
      
      await page.waitForTimeout(200);
      
      // Verify map is still responsive every few moves
      if (i % 3 === 0) {
        await expect(mapContainer).toBeVisible();
        
        // Check that map tiles are still loading/visible
        const mapTiles = page.locator('.leaflet-tile');
        await expect(mapTiles.first()).toBeVisible();
      }
    }
    
    // Final verification
    await expect(mapContainer).toBeVisible();
  });

  test('should handle panning with different mouse speeds', async ({ page }) => {
    const mapContainer = page.locator('.leaflet-container');
    const mapBounds = await mapContainer.boundingBox();
    expect(mapBounds).not.toBeNull();
    
    if (!mapBounds) return;
    
    const centerX = mapBounds.x + mapBounds.width / 2;
    const centerY = mapBounds.y + mapBounds.height / 2;
    const panDistance = 100;
    
    // Test different panning speeds
    const speeds = [
      { name: 'slow', steps: 20, delay: 50 },
      { name: 'medium', steps: 10, delay: 20 },
      { name: 'fast', steps: 3, delay: 0 }
    ];
    
    for (const speed of speeds) {
      console.log(`Testing ${speed.name} panning speed...`);
      
      await page.mouse.move(centerX, centerY);
      await page.mouse.down();
      
      if (speed.delay > 0) {
        await page.mouse.move(centerX + panDistance, centerY, { steps: speed.steps });
        await page.waitForTimeout(speed.delay);
      } else {
        // Fast movement
        await page.mouse.move(centerX + panDistance, centerY, { steps: speed.steps });
      }
      
      await page.mouse.up();
      await page.waitForTimeout(300);
      
      await expect(mapContainer).toBeVisible();
      
      // Reset position for next test
      await page.mouse.move(centerX + panDistance, centerY);
      await page.mouse.down();
      await page.mouse.move(centerX, centerY, { steps: 5 });
      await page.mouse.up();
      await page.waitForTimeout(200);
    }
  });
});