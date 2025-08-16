import { test, expect } from '@playwright/test';

test.describe('Map Navigation and Photo Turning', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the main page
    await page.goto('/');
    
    // Wait for the app to load
    await page.waitForLoadState('networkidle');
    
    // Wait for map to be ready
    await page.waitForSelector('.leaflet-container', { timeout: 10000 });
  });

  test('should load main page without runtime errors', async ({ page }) => {
    // Listen for console errors
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    // Check for uncaught exceptions
    const uncaughtExceptions: string[] = [];
    page.on('pageerror', (error) => {
      uncaughtExceptions.push(error.message);
    });

    // Wait a bit for any async operations
    await page.waitForTimeout(2000);

    // Check for specific runtime errors that were problematic
    const hasPositionError = errors.some(error => error.includes('pos is not defined'));
    const hasBearingError = errors.some(error => error.includes('bearing is not defined'));
    const hasUncaughtError = uncaughtExceptions.some(error => 
      error.includes('pos is not defined') || 
      error.includes('bearing is not defined')
    );

    // Assertions
    expect(hasPositionError, `Found 'pos is not defined' error: ${errors.join(', ')}`).toBe(false);
    expect(hasBearingError, `Found 'bearing is not defined' error: ${errors.join(', ')}`).toBe(false);
    expect(hasUncaughtError, `Found uncaught runtime error: ${uncaughtExceptions.join(', ')}`).toBe(false);
  });

  test('should handle keyboard turning (z/x keys) without errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    // Wait for page to be fully loaded
    await page.waitForTimeout(1000);

    // Test z key (rotate left)
    await page.keyboard.press('z');
    await page.waitForTimeout(100);

    // Test x key (rotate right)  
    await page.keyboard.press('x');
    await page.waitForTimeout(100);

    // Test multiple rapid key presses
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press('z');
      await page.waitForTimeout(50);
    }

    for (let i = 0; i < 5; i++) {
      await page.keyboard.press('x');
      await page.waitForTimeout(50);
    }

    // Check for runtime errors during rotation
    const hasRotationErrors = errors.some(error => 
      error.includes('pos is not defined') || 
      error.includes('bearing is not defined') ||
      error.includes('updateBearing') ||
      error.includes('spatialState') ||
      error.includes('visualState')
    );

    expect(hasRotationErrors, `Found rotation errors: ${errors.join(', ')}`).toBe(false);
  });

  test('should handle photo navigation (c/v keys) without errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    // Wait for page to be fully loaded
    await page.waitForTimeout(1000);

    // Test c key (turn to left photo)
    await page.keyboard.press('c');
    await page.waitForTimeout(200);

    // Test v key (turn to right photo)
    await page.keyboard.press('v');
    await page.waitForTimeout(200);

    // Test multiple navigation attempts
    for (let i = 0; i < 3; i++) {
      await page.keyboard.press('c');
      await page.waitForTimeout(100);
      await page.keyboard.press('v');
      await page.waitForTimeout(100);
    }

    // Check for runtime errors during photo navigation
    const hasNavigationErrors = errors.some(error => 
      error.includes('pos is not defined') || 
      error.includes('bearing is not defined') ||
      error.includes('turn_to_photo_to') ||
      error.includes('photosInArea') ||
      error.includes('spatialState') ||
      error.includes('visualState')
    );

    expect(hasNavigationErrors, `Found navigation errors: ${errors.join(', ')}`).toBe(false);
  });

  test('should handle map panning without runtime errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    // Wait for map to be ready
    await page.waitForTimeout(1000);

    // Get the map container
    const mapContainer = page.locator('.leaflet-container').first();
    await expect(mapContainer).toBeVisible();

    // Get the map's bounding box
    const mapBox = await mapContainer.boundingBox();
    expect(mapBox).not.toBeNull();

    if (mapBox) {
      // Simulate map panning by dragging from center to different positions
      const centerX = mapBox.x + mapBox.width / 2;
      const centerY = mapBox.y + mapBox.height / 2;

      // Pan in different directions
      const panTests = [
        { name: 'pan north', deltaX: 0, deltaY: -100 },
        { name: 'pan south', deltaX: 0, deltaY: 100 },
        { name: 'pan east', deltaX: 100, deltaY: 0 },
        { name: 'pan west', deltaX: -100, deltaY: 0 },
        { name: 'pan northeast', deltaX: 50, deltaY: -50 },
        { name: 'pan southwest', deltaX: -50, deltaY: 50 },
      ];

      for (const panTest of panTests) {
        await page.mouse.move(centerX, centerY);
        await page.mouse.down();
        await page.mouse.move(centerX + panTest.deltaX, centerY + panTest.deltaY, { steps: 5 });
        await page.mouse.up();
        await page.waitForTimeout(100);
      }
    }

    // Check for runtime errors during panning
    const hasPanningErrors = errors.some(error => 
      error.includes('pos is not defined') || 
      error.includes('bearing is not defined') ||
      error.includes('spatialState') ||
      error.includes('updateSpatialState') ||
      error.includes('center') ||
      error.includes('zoom')
    );

    expect(hasPanningErrors, `Found panning errors: ${errors.join(', ')}`).toBe(false);
  });

  test('should update URL parameters during navigation without errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    // Wait for initial load
    await page.waitForTimeout(1000);

    // Check initial URL
    const initialUrl = page.url();
    
    // Perform some navigation actions
    await page.keyboard.press('z'); // rotate
    await page.waitForTimeout(200);
    
    await page.keyboard.press('x'); // rotate back
    await page.waitForTimeout(200);

    // Pan the map
    const mapContainer = page.locator('.leaflet-container').first();
    const mapBox = await mapContainer.boundingBox();
    if (mapBox) {
      const centerX = mapBox.x + mapBox.width / 2;
      const centerY = mapBox.y + mapBox.height / 2;
      
      await page.mouse.move(centerX, centerY);
      await page.mouse.down();
      await page.mouse.move(centerX + 100, centerY + 100, { steps: 5 });
      await page.mouse.up();
      await page.waitForTimeout(500);
    }

    // Check for URL update errors
    const hasUrlErrors = errors.some(error => 
      error.includes('Failed to update URL') ||
      error.includes('replaceState') ||
      error.includes('pos is not defined') ||
      error.includes('bearing is not defined')
    );

    expect(hasUrlErrors, `Found URL update errors: ${errors.join(', ')}`).toBe(false);
  });

  test('should handle debug overlay toggle without errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    // Wait for page load
    await page.waitForTimeout(1000);

    // Test debug button
    const debugButton = page.locator('button.debug-toggle');
    await expect(debugButton).toBeVisible();
    await debugButton.click();
    await page.waitForTimeout(200);
    
    // Test clicking again to cycle debug modes
    await debugButton.click();
    await page.waitForTimeout(200);

    // Check for debug-related errors
    const hasDebugErrors = errors.some(error => 
      error.includes('pos is not defined') ||
      error.includes('bearing is not defined') ||
      error.includes('debugOverlay') ||
      error.includes('spatialState') ||
      error.includes('visualState')
    );

    expect(hasDebugErrors, `Found debug-related errors: ${errors.join(', ')}`).toBe(false);
  });
});