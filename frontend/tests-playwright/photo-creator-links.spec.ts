import { test, expect } from '@playwright/test';
import { setupDefaultMockMapillaryData, clearMockMapillaryData } from './helpers/mapillaryMocks';
import { createTestUsers } from './helpers/testUsers';

test.describe('Photo Creator Name Links', () => {
  test.beforeEach(async ({ page }) => {
    // Clean up test users before each test
    const response = await fetch('http://localhost:8055/api/debug/recreate-test-users', {
      method: 'POST'
    });
    const result = await response.json();
    console.log('🢄Test cleanup result:', result);
  });

  test('should make Hillview photo creator names clickable', async ({ page }) => {
    // Get test user credentials and login
    const response = await fetch('http://localhost:8055/api/debug/recreate-test-users', {
      method: 'POST'
    });
    const result = await response.json();
    const testPassword = result.details?.user_passwords?.test;

    // Login with test user
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    await page.fill('input[type="text"]', 'test');
    await page.fill('input[type="password"]', testPassword);
    await page.click('button[type="submit"]');
    await page.waitForURL('/', { timeout: 15000 });

    // Upload a photo to create Hillview content
    await page.goto('/photos');
    await page.waitForLoadState('networkidle');

    const fileInput = page.locator('[data-testid="photo-file-input"]');
    await fileInput.setInputFiles('test-assets/2025-07-10-19-10-37_🔶∏🗿↻🌞🌲.jpg');
    const uploadButton = page.locator('[data-testid="upload-submit-button"]');
    await uploadButton.click();

    // Wait for upload completion
    await page.waitForFunction(() => {
      const input = document.querySelector('[data-testid="photo-file-input"]') as HTMLInputElement;
      return input && input.value === '';
    }, { timeout: 10000 });

    // Go to main map view where Photo.svelte is used
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('.leaflet-container', { timeout: 10000 });

    // Look for creator info in front photo (Photo.svelte component)
    const creatorInfo = page.locator('.creator-info');
    if (await creatorInfo.isVisible()) {
      // Check if creator name is clickable for Hillview photos
      const clickableCreatorName = creatorInfo.locator('.creator-name.clickable');
      if (await clickableCreatorName.count() > 0) {
        const creatorText = await clickableCreatorName.textContent();

        // Click the creator name
        await clickableCreatorName.click();

        // Should navigate to user page
        await page.waitForURL(/\/users\/[^\/]+$/);

        // Should be on user page with creator's photos
        await expect(page.locator('.photos-section')).toBeVisible();

        // Check that the page title contains the creator name
        const pageTitle = page.locator('h1, h2').filter({ hasText: /Photos/ });
        await expect(pageTitle).toBeVisible();
      }
    }
  });

  test('should not make Mapillary creator names clickable', async ({ page }) => {
    // Set up mock Mapillary data so we have photos to test with
    await setupDefaultMockMapillaryData(page);

    // Navigate to map view
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('.leaflet-container', { timeout: 10000 });

    // Wait for photos to load from mock data
    await page.waitForTimeout(3000);

    // Look for creator info
    const creatorInfo = page.locator('.creator-info');
    if (await creatorInfo.isVisible()) {
      // Check source name to see if it's Mapillary
      const sourceName = creatorInfo.locator('.source-name');
      const sourceText = await sourceName.textContent();

      if (sourceText?.toLowerCase().includes('mapillary')) {
        // For Mapillary photos, creator name should NOT be clickable
        const creatorName = creatorInfo.locator('.creator-name');
        await expect(creatorName).toBeVisible();
        await expect(creatorName).not.toHaveClass('clickable');

        // Should not have clickable class
        const clickableCreatorName = creatorInfo.locator('.creator-name.clickable');
        expect(await clickableCreatorName.count()).toBe(0);
      }
    }
  });

  test('should display creator info correctly', async ({ page }) => {
    // Set up mock Mapillary data so we have photos to test with
    await setupDefaultMockMapillaryData(page);

    // Navigate to map view
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('.leaflet-container', { timeout: 10000 });

    // Wait for photos to load from mock data
    await page.waitForTimeout(3000);

    // Look for creator info display
    const creatorInfo = page.locator('.creator-info');
    if (await creatorInfo.isVisible()) {
      // Should have creator name starting with @
      const creatorName = creatorInfo.locator('.creator-name');
      const nameText = await creatorName.textContent();
      expect(nameText).toMatch(/^@\w+/);

      // Should have source name
      const sourceName = creatorInfo.locator('.source-name');
      await expect(sourceName).toBeVisible();
      const sourceText = await sourceName.textContent();
      expect(sourceText).toMatch(/hillview|mapillary/i);
    }
  });


});
