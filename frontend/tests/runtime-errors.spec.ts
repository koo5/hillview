import { test, expect } from '@playwright/test';

test.describe('Runtime Error Detection', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the main page
    await page.goto('/');
    
    // Wait for the app to load
    await page.waitForLoadState('networkidle');
  });

  test('should not have "pos is not defined" errors', async ({ page }) => {
    const errors: string[] = [];
    const uncaughtExceptions: string[] = [];

    // Listen for console errors
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    // Listen for uncaught exceptions
    page.on('pageerror', (error) => {
      uncaughtExceptions.push(error.message);
    });

    // Wait for initial load and any async operations
    await page.waitForTimeout(2000);

    // Trigger actions that previously caused "pos is not defined" errors
    
    // 1. Try map interaction that previously used get(pos)
    const mapContainer = page.locator('.leaflet-container').first();
    if (await mapContainer.isVisible()) {
      const mapBox = await mapContainer.boundingBox();
      if (mapBox) {
        // Click on map to trigger position updates
        await page.mouse.click(mapBox.x + mapBox.width / 2, mapBox.y + mapBox.height / 2);
        await page.waitForTimeout(200);
        
        // Pan the map to trigger spatial state updates
        await page.mouse.move(mapBox.x + mapBox.width / 2, mapBox.y + mapBox.height / 2);
        await page.mouse.down();
        await page.mouse.move(mapBox.x + mapBox.width / 2 + 50, mapBox.y + mapBox.height / 2 + 50);
        await page.mouse.up();
        await page.waitForTimeout(500);
      }
    }

    // 2. Trigger keyboard navigation that might access pos/bearing stores
    await page.keyboard.press('z'); // rotate left
    await page.waitForTimeout(100);
    await page.keyboard.press('x'); // rotate right
    await page.waitForTimeout(100);
    await page.keyboard.press('c'); // turn to left photo
    await page.waitForTimeout(100);
    await page.keyboard.press('v'); // turn to right photo
    await page.waitForTimeout(100);

    // 3. Toggle debug mode which previously had issues with pos references
    await page.keyboard.press('d');
    await page.waitForTimeout(200);

    // 4. Try URL parameter updates that previously failed
    // This should trigger spatial state subscriptions
    for (let i = 0; i < 3; i++) {
      await page.keyboard.press('z');
      await page.waitForTimeout(100);
    }
    await page.waitForTimeout(1000); // Wait for URL updates

    // Check for specific "pos is not defined" errors
    const hasPosErrors = [
      ...errors.filter(error => error.includes('pos is not defined')),
      ...uncaughtExceptions.filter(error => error.includes('pos is not defined'))
    ];

    // Log all errors for debugging
    if (errors.length > 0) {
      console.log('Console errors found:', errors);
    }
    if (uncaughtExceptions.length > 0) {
      console.log('Uncaught exceptions found:', uncaughtExceptions);
    }

    expect(hasPosErrors.length, `Found "pos is not defined" errors: ${hasPosErrors.join(', ')}`).toBe(0);
  });

  test('should not have legacy store reference errors', async ({ page }) => {
    const errors: string[] = [];
    const uncaughtExceptions: string[] = [];

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    page.on('pageerror', (error) => {
      uncaughtExceptions.push(error.message);
    });

    // Wait for initial load
    await page.waitForTimeout(2000);

    // Perform various actions that might trigger legacy store references
    
    // Camera button interaction
    const cameraButton = page.locator('[data-testid="camera-button"]');
    if (await cameraButton.isVisible()) {
      await cameraButton.click();
      await page.waitForTimeout(500);
      await cameraButton.click(); // Toggle back
      await page.waitForTimeout(500);
    }

    // Menu interactions
    const menuButton = page.locator('.hamburger');
    if (await menuButton.isVisible()) {
      await menuButton.click();
      await page.waitForTimeout(200);
      await page.keyboard.press('Escape'); // Close menu
      await page.waitForTimeout(200);
    }

    // Debug overlay interactions
    const debugToggle = page.locator('.debug-toggle');
    if (await debugToggle.isVisible()) {
      await debugToggle.click();
      await page.waitForTimeout(200);
      await debugToggle.click(); // Toggle back
      await page.waitForTimeout(200);
    }

    // Check for legacy store reference errors
    const legacyStoreErrors = [
      ...errors.filter(error => 
        error.includes('bearing is not defined') ||
        error.includes('pos2 is not defined') ||
        error.includes('photos_in_area is not defined') ||
        error.includes('photos_in_range is not defined')
      ),
      ...uncaughtExceptions.filter(error => 
        error.includes('bearing is not defined') ||
        error.includes('pos2 is not defined') ||
        error.includes('photos_in_area is not defined') ||
        error.includes('photos_in_range is not defined')
      )
    ];

    expect(legacyStoreErrors.length, `Found legacy store errors: ${legacyStoreErrors.join(', ')}`).toBe(0);
  });

  test('should handle map component initialization without errors', async ({ page }) => {
    const errors: string[] = [];
    const uncaughtExceptions: string[] = [];

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    page.on('pageerror', (error) => {
      uncaughtExceptions.push(error.message);
    });

    // Wait for map to fully initialize
    await page.waitForSelector('.leaflet-container', { timeout: 10000 });
    await page.waitForTimeout(2000);

    // Check that the map has loaded without errors
    const mapContainer = page.locator('.leaflet-container');
    await expect(mapContainer).toBeVisible();

    // Verify no initialization errors related to position/bearing
    const initErrors = [
      ...errors.filter(error => 
        error.includes('pos is not defined') ||
        error.includes('spatialState') ||
        error.includes('visualState') ||
        error.includes('mapState')
      ),
      ...uncaughtExceptions.filter(error => 
        error.includes('pos is not defined') ||
        error.includes('spatialState') ||
        error.includes('visualState') ||
        error.includes('mapState')
      )
    ];

    expect(initErrors.length, `Found map initialization errors: ${initErrors.join(', ')}`).toBe(0);
  });

  test('should handle photo gallery operations without legacy errors', async ({ page }) => {
    const errors: string[] = [];
    const uncaughtExceptions: string[] = [];

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    page.on('pageerror', (error) => {
      uncaughtExceptions.push(error.message);
    });

    // Wait for initial load
    await page.waitForTimeout(2000);

    // Try photo navigation operations
    await page.keyboard.press('c'); // Turn to left photo
    await page.waitForTimeout(300);
    await page.keyboard.press('v'); // Turn to right photo  
    await page.waitForTimeout(300);

    // Try multiple rapid navigation
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press('c');
      await page.waitForTimeout(50);
    }

    for (let i = 0; i < 5; i++) {
      await page.keyboard.press('v');
      await page.waitForTimeout(50);
    }

    // Check for photo-related legacy errors
    const photoErrors = [
      ...errors.filter(error => 
        error.includes('turn_to_photo_to') ||
        error.includes('combinedPhotos') ||
        error.includes('photosInArea') ||
        error.includes('photos_in_area is not defined') ||
        error.includes('photos_in_range is not defined')
      ),
      ...uncaughtExceptions.filter(error => 
        error.includes('turn_to_photo_to') ||
        error.includes('combinedPhotos') ||
        error.includes('photosInArea') ||
        error.includes('photos_in_area is not defined') ||
        error.includes('photos_in_range is not defined')
      )
    ];

    expect(photoErrors.length, `Found photo gallery errors: ${photoErrors.join(', ')}`).toBe(0);
  });

  test('should handle display mode toggle without state errors', async ({ page }) => {
    const errors: string[] = [];
    const uncaughtExceptions: string[] = [];

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    page.on('pageerror', (error) => {
      uncaughtExceptions.push(error.message);
    });

    // Wait for initial load
    await page.waitForTimeout(1000);

    // Test display mode toggle
    await page.keyboard.press('m');
    await page.waitForTimeout(500);
    await page.keyboard.press('m'); // Toggle back
    await page.waitForTimeout(500);

    // Test display mode button if visible
    const displayModeButton = page.locator('.display-mode-toggle');
    if (await displayModeButton.isVisible()) {
      await displayModeButton.click();
      await page.waitForTimeout(300);
      await displayModeButton.click(); // Toggle back
      await page.waitForTimeout(300);
    }

    // Check for display mode related errors
    const displayErrors = [
      ...errors.filter(error => 
        error.includes('pos is not defined') ||
        error.includes('displayMode') ||
        error.includes('spatialState') ||
        error.includes('app.update')
      ),
      ...uncaughtExceptions.filter(error => 
        error.includes('pos is not defined') ||
        error.includes('displayMode') ||
        error.includes('spatialState') ||
        error.includes('app.update')
      )
    ];

    expect(displayErrors.length, `Found display mode errors: ${displayErrors.join(', ')}`).toBe(0);
  });
});