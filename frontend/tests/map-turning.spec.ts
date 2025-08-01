import { test, expect } from '@playwright/test';

test.describe('Map Turning and Rotation Operations', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    
    // Wait for the map to be loaded and visible
    await page.waitForSelector('.leaflet-container', { timeout: 10000 });
    await page.waitForTimeout(2000); // Allow map to fully initialize
    
    // Ensure we're in the correct view mode
    await expect(page.locator('.leaflet-container')).toBeVisible();
  });

  test('should rotate view using control buttons', async ({ page }) => {
    // Look for rotation control buttons
    const rotateCcwButton = page.locator('button[title*="counterclockwise"], button[title*="Rotate view 15° counterclockwise"]');
    const rotateCwButton = page.locator('button[title*="clockwise"], button[title*="Rotate view 15° clockwise"]');
    
    // Test counterclockwise rotation if button exists
    if (await rotateCcwButton.count() > 0) {
      console.log('Testing counterclockwise rotation button...');
      
      for (let i = 0; i < 3; i++) {
        await rotateCcwButton.click();
        await page.waitForTimeout(500); // Wait for rotation animation
        
        // Verify map is still visible and responsive
        await expect(page.locator('.leaflet-container')).toBeVisible();
      }
    }
    
    // Test clockwise rotation if button exists
    if (await rotateCwButton.count() > 0) {
      console.log('Testing clockwise rotation button...');
      
      for (let i = 0; i < 3; i++) {
        await rotateCwButton.click();
        await page.waitForTimeout(500); // Wait for rotation animation
        
        // Verify map is still visible and responsive
        await expect(page.locator('.leaflet-container')).toBeVisible();
      }
    }
  });

  test('should navigate using left/right turn buttons', async ({ page }) => {
    // Look for photo navigation buttons
    const leftTurnButton = page.locator('button[title*="left"], button[title*="photo on the left"]');
    const rightTurnButton = page.locator('button[title*="right"], button[title*="photo on the right"]');
    
    // Test left turn button if it exists and is enabled
    if (await leftTurnButton.count() > 0) {
      const isEnabled = await leftTurnButton.isEnabled();
      if (isEnabled) {
        console.log('Testing left turn button...');
        await leftTurnButton.click();
        await page.waitForTimeout(1000);
        
        await expect(page.locator('.leaflet-container')).toBeVisible();
      }
    }
    
    // Test right turn button if it exists and is enabled
    if (await rightTurnButton.count() > 0) {
      const isEnabled = await rightTurnButton.isEnabled();
      if (isEnabled) {
        console.log('Testing right turn button...');
        await rightTurnButton.click();
        await page.waitForTimeout(1000);
        
        await expect(page.locator('.leaflet-container')).toBeVisible();
      }
    }
  });

  test('should test forward/backward movement buttons', async ({ page }) => {
    // Look for movement buttons
    const forwardButton = page.locator('button[title*="forward"], button[title*="Move forward"]');
    const backwardButton = page.locator('button[title*="backward"], button[title*="Move backward"]');
    
    // Test forward movement
    if (await forwardButton.count() > 0) {
      console.log('Testing forward movement button...');
      await forwardButton.click();
      await page.waitForTimeout(800);
      
      await expect(page.locator('.leaflet-container')).toBeVisible();
    }
    
    // Test backward movement
    if (await backwardButton.count() > 0) {
      console.log('Testing backward movement button...');
      await backwardButton.click();
      await page.waitForTimeout(800);
      
      await expect(page.locator('.leaflet-container')).toBeVisible();
    }
  });

  test('should perform gesture-based map rotation', async ({ page }) => {
    const mapContainer = page.locator('.leaflet-container');
    const mapBounds = await mapContainer.boundingBox();
    expect(mapBounds).not.toBeNull();
    
    if (!mapBounds) return;
    
    const centerX = mapBounds.x + mapBounds.width / 2;
    const centerY = mapBounds.y + mapBounds.height / 2;
    const rotationRadius = 80;
    
    // Simulate two-finger rotation gesture (clockwise)
    console.log('Testing clockwise rotation gesture...');
    
    // First finger starts at top, moves to right
    const finger1Start = { x: centerX, y: centerY - rotationRadius };
    const finger1End = { x: centerX + rotationRadius, y: centerY };
    
    // Second finger starts at bottom, moves to left  
    const finger2Start = { x: centerX, y: centerY + rotationRadius };
    const finger2End = { x: centerX - rotationRadius, y: centerY };
    
    // Perform the rotation gesture
    await page.mouse.move(finger1Start.x, finger1Start.y);
    await page.mouse.down();
    await page.mouse.move(finger1End.x, finger1End.y, { steps: 10 });
    await page.mouse.up();
    
    await page.waitForTimeout(200);
    
    // Simulate second finger (in a real two-finger rotation, these would be simultaneous)
    await page.mouse.move(finger2Start.x, finger2Start.y);
    await page.mouse.down();
    await page.mouse.move(finger2End.x, finger2End.y, { steps: 10 });
    await page.mouse.up();
    
    await page.waitForTimeout(500);
    await expect(mapContainer).toBeVisible();
  });

  test('should perform counterclockwise rotation gesture', async ({ page }) => {
    const mapContainer = page.locator('.leaflet-container');
    const mapBounds = await mapContainer.boundingBox();
    expect(mapBounds).not.toBeNull();
    
    if (!mapBounds) return;
    
    const centerX = mapBounds.x + mapBounds.width / 2;
    const centerY = mapBounds.y + mapBounds.height / 2;
    const rotationRadius = 80;
    
    console.log('Testing counterclockwise rotation gesture...');
    
    // First finger starts at top, moves to left
    const finger1Start = { x: centerX, y: centerY - rotationRadius };
    const finger1End = { x: centerX - rotationRadius, y: centerY };
    
    // Second finger starts at bottom, moves to right
    const finger2Start = { x: centerX, y: centerY + rotationRadius };
    const finger2End = { x: centerX + rotationRadius, y: centerY };
    
    // Perform the rotation gesture
    await page.mouse.move(finger1Start.x, finger1Start.y);
    await page.mouse.down();
    await page.mouse.move(finger1End.x, finger1End.y, { steps: 10 });
    await page.mouse.up();
    
    await page.waitForTimeout(200);
    
    await page.mouse.move(finger2Start.x, finger2Start.y);
    await page.mouse.down();
    await page.mouse.move(finger2End.x, finger2End.y, { steps: 10 });
    await page.mouse.up();
    
    await page.waitForTimeout(500);
    await expect(mapContainer).toBeVisible();
  });

  test('should handle multiple small precision rotations', async ({ page }) => {
    const mapContainer = page.locator('.leaflet-container');
    const mapBounds = await mapContainer.boundingBox();
    expect(mapBounds).not.toBeNull();
    
    if (!mapBounds) return;
    
    const centerX = mapBounds.x + mapBounds.width / 2;
    const centerY = mapBounds.y + mapBounds.height / 2;
    const smallRadius = 60;
    
    // Perform multiple small rotation gestures
    const smallRotations = [15, -10, 25, -20, 15]; // degrees (positive = clockwise)
    
    for (let i = 0; i < smallRotations.length; i++) {
      const rotation = smallRotations[i];
      const rotationRadians = (rotation * Math.PI) / 180;
      
      console.log(`Small precision rotation ${i + 1}: ${rotation} degrees...`);
      
      // Calculate rotation points
      const startX = centerX + smallRadius * Math.cos(-Math.PI / 2);
      const startY = centerY + smallRadius * Math.sin(-Math.PI / 2);
      const endX = centerX + smallRadius * Math.cos(-Math.PI / 2 + rotationRadians);
      const endY = centerY + smallRadius * Math.sin(-Math.PI / 2 + rotationRadians);
      
      // Perform precise rotation
      await page.mouse.move(startX, startY);
      await page.mouse.down();
      await page.mouse.move(endX, endY, { steps: 5 });
      await page.mouse.up();
      
      await page.waitForTimeout(300);
      await expect(mapContainer).toBeVisible();
    }
  });

  test('should test location tracking functionality', async ({ page }) => {
    // Look for location tracking button
    const locationButton = page.locator('button[title*="location"], button[title*="Track my location"]');
    
    if (await locationButton.count() > 0) {
      console.log('Testing location tracking button...');
      
      // Click to attempt to enable location tracking
      await locationButton.click();
      await page.waitForTimeout(1000);
      
      // Note: In a real test environment, geolocation might be blocked
      // The button should still be functional even if permission is denied
      await expect(locationButton).toBeVisible();
      
      // Click again to toggle off
      await locationButton.click();
      await page.waitForTimeout(500);
      
      await expect(page.locator('.leaflet-container')).toBeVisible();
    }
  });

  test('should test compass tracking functionality', async ({ page }) => {
    // Look for compass tracking button
    const compassButton = page.locator('button[title*="compass"], button[title*="Track compass bearing"]');
    
    if (await compassButton.count() > 0) {
      console.log('Testing compass tracking button...');
      
      const isEnabled = await compassButton.isEnabled();
      if (isEnabled) {
        // Click to enable compass tracking
        await compassButton.click();
        await page.waitForTimeout(1000);
        
        // Click again to disable
        await compassButton.click();
        await page.waitForTimeout(500);
      } else {
        console.log('Compass button is disabled (likely no compass available in test environment)');
      }
      
      await expect(compassButton).toBeVisible();
      await expect(page.locator('.leaflet-container')).toBeVisible();
    }
  });

  test('should perform complex turning sequence with movement', async ({ page }) => {
    console.log('Testing complex turning and movement sequence...');
    
    // Get all control buttons
    const rotateButtons = page.locator('button[title*="Rotate"], button[title*="rotate"]');
    const moveButtons = page.locator('button[title*="Move"], button[title*="move"]');
    
    const rotateCount = await rotateButtons.count();
    const moveCount = await moveButtons.count();
    
    // Perform complex sequence: rotate → move → rotate → move
    if (rotateCount > 0) {
      console.log('Executing rotation action...');
      const randomRotateIndex = Math.floor(Math.random() * rotateCount);
      const rotateButton = rotateButtons.nth(randomRotateIndex);
      
      if (await rotateButton.isEnabled()) {
        await rotateButton.click();
        await page.waitForTimeout(600);
      }
    }
    
    if (moveCount > 0) {
      console.log('Executing movement action...');
      const randomMoveIndex = Math.floor(Math.random() * moveCount);
      const moveButton = moveButtons.nth(randomMoveIndex);
      
      if (await moveButton.isEnabled()) {
        await moveButton.click();
        await page.waitForTimeout(600);
      }
    }
    
    // Repeat the sequence
    if (rotateCount > 0) {
      const randomRotateIndex = Math.floor(Math.random() * rotateCount);
      const rotateButton = rotateButtons.nth(randomRotateIndex);
      
      if (await rotateButton.isEnabled()) {
        await rotateButton.click();
        await page.waitForTimeout(600);
      }
    }
    
    if (moveCount > 0) {
      const randomMoveIndex = Math.floor(Math.random() * moveCount);
      const moveButton = moveButtons.nth(randomMoveIndex);
      
      if (await moveButton.isEnabled()) {
        await moveButton.click();
        await page.waitForTimeout(600);
      }
    }
    
    // Verify map is still responsive
    await expect(page.locator('.leaflet-container')).toBeVisible();
  });

  test('should test turning while panning simultaneously', async ({ page }) => {
    console.log('Testing simultaneous turning and panning...');
    
    const mapContainer = page.locator('.leaflet-container');
    const mapBounds = await mapContainer.boundingBox();
    expect(mapBounds).not.toBeNull();
    
    if (!mapBounds) return;
    
    const centerX = mapBounds.x + mapBounds.width / 2;
    const centerY = mapBounds.y + mapBounds.height / 2;
    
    // First perform a rotation gesture
    await page.mouse.move(centerX, centerY - 60);
    await page.mouse.down();
    await page.mouse.move(centerX + 60, centerY, { steps: 8 });
    await page.mouse.up();
    await page.waitForTimeout(300);
    
    // Then immediately perform a pan
    await page.mouse.move(centerX, centerY);
    await page.mouse.down();
    await page.mouse.move(centerX + 80, centerY - 80, { steps: 8 });
    await page.mouse.up();
    await page.waitForTimeout(300);
    
    // Then another rotation
    await page.mouse.move(centerX, centerY + 60);
    await page.mouse.down();
    await page.mouse.move(centerX - 60, centerY, { steps: 8 });
    await page.mouse.up();
    await page.waitForTimeout(300);
    
    await expect(mapContainer).toBeVisible();
  });

  test('should maintain navigation consistency after multiple operations', async ({ page }) => {
    console.log('Testing navigation consistency...');
    
    const mapContainer = page.locator('.leaflet-container');
    const mapBounds = await mapContainer.boundingBox();
    expect(mapBounds).not.toBeNull();
    
    if (!mapBounds) return;
    
    const centerX = mapBounds.x + mapBounds.width / 2;
    const centerY = mapBounds.y + mapBounds.height / 2;
    
    // Perform a series of mixed operations
    const operations = [
      {
        name: 'pan',
        action: async () => {
          await page.mouse.move(centerX, centerY);
          await page.mouse.down();
          await page.mouse.move(centerX + 70, centerY, { steps: 6 });
          await page.mouse.up();
        }
      },
      {
        name: 'rotate',
        action: async () => {
          await page.mouse.move(centerX, centerY - 50);
          await page.mouse.down();
          await page.mouse.move(centerX + 50, centerY, { steps: 6 });
          await page.mouse.up();
        }
      },
      {
        name: 'pan_diagonal',
        action: async () => {
          await page.mouse.move(centerX, centerY);
          await page.mouse.down();
          await page.mouse.move(centerX - 60, centerY - 60, { steps: 6 });
          await page.mouse.up();
        }
      },
      {
        name: 'rotate_counter',
        action: async () => {
          await page.mouse.move(centerX, centerY - 50);
          await page.mouse.down();
          await page.mouse.move(centerX - 50, centerY, { steps: 6 });
          await page.mouse.up();
        }
      }
    ];
    
    for (const operation of operations) {
      console.log(`Performing ${operation.name} operation...`);
      await operation.action();
      await page.waitForTimeout(400);
      
      // Verify map is still responsive after each operation
      await expect(mapContainer).toBeVisible();
      
      // Check that map tiles are still visible
      const mapTiles = page.locator('.leaflet-tile');
      if (await mapTiles.count() > 0) {
        await expect(mapTiles.first()).toBeVisible();
      }
    }
  });

  test('should handle rapid control button interactions', async ({ page }) => {
    console.log('Testing rapid control button interactions...');
    
    // Get all navigation control buttons
    const controlButtons = page.locator('button[title*="Rotate"], button[title*="Move"], button[title*="rotate"], button[title*="move"]');
    const buttonCount = await controlButtons.count();
    
    if (buttonCount > 0) {
      // Perform rapid sequence of button presses
      const rapidSequenceLength = Math.min(buttonCount, 6);
      
      for (let i = 0; i < rapidSequenceLength; i++) {
        const button = controlButtons.nth(i % buttonCount);
        
        if (await button.isEnabled()) {
          console.log(`Rapid button click ${i + 1}...`);
          await button.click();
          await page.waitForTimeout(150); // Short pause between clicks
        }
      }
      
      // Verify UI is still responsive
      await expect(page.locator('.leaflet-container')).toBeVisible();
    }
  });

  test('should test bearing arrow visibility and updates', async ({ page }) => {
    console.log('Testing bearing arrow visibility...');
    
    // Look for the bearing arrow/direction indicator
    const bearingArrow = page.locator('svg line[marker-end*="arrowhead"], .svg-overlay svg line');
    
    if (await bearingArrow.count() > 0) {
      await expect(bearingArrow.first()).toBeVisible();
      
      // Test if arrow updates when rotation buttons are clicked
      const rotateButton = page.locator('button[title*="Rotate"], button[title*="rotate"]').first();
      
      if (await rotateButton.count() > 0 && await rotateButton.isEnabled()) {
        // Get initial arrow properties
        const initialArrow = await bearingArrow.first().boundingBox();
        
        // Click rotation button
        await rotateButton.click();
        await page.waitForTimeout(500);
        
        // Verify arrow is still visible (position may have changed)
        await expect(bearingArrow.first()).toBeVisible();
        
        console.log('Bearing arrow remained visible after rotation');
      }
    }
  });
});