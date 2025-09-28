import { test, expect } from '@playwright/test';
import { MAX_DEBUG_MODES } from '../src/lib/constants';


  test('should cycle debug modes including new capture mode', async ({ page }) => {
    await page.goto('/');

    // Wait for page to load
    await page.waitForSelector('body', { timeout: 5000 });

    // Find debug button
    const debugButton = page.locator('button.debug-toggle');

    // Click through debug modes
    await debugButton.click(); // Mode 1
    await page.waitForSelector('.debug-overlay', { timeout: 5000 });
    await page.waitForTimeout(500);

    await debugButton.click(); // Mode 2
    await page.waitForTimeout(500);

    await debugButton.click(); // Mode 3
    await page.waitForTimeout(500);

    await debugButton.click(); // Mode 4 (capture system)
    await page.waitForTimeout(500);

    // Check that we're in mode 4 and capture system section is visible
    const captureSystemSection = page.locator('.capture-system-section');
    await expect(captureSystemSection).toBeVisible();

    await debugButton.click(); // Mode 5 (front photo debug)
    await page.waitForTimeout(500);

    // Check that we're in mode 5 and photo management section is visible
    const photoManagementSection = page.locator('.photo-management-section');
    await expect(photoManagementSection).toBeVisible();

    await debugButton.click(); // Mode 0 (off)
    await page.waitForTimeout(500);

    // Debug overlay should be hidden
    const debugOverlay = page.locator('.debug-overlay');
    await expect(debugOverlay).not.toBeVisible();
  });

  test('should show front photo debug information in mode 5', async ({ page }) => {
    // Go to page with debug mode 5 directly via URL
    await page.goto('/?debug=5');

    // Wait for debug overlay to appear
    await page.waitForSelector('.debug-overlay', { timeout: 5000 });

    // Check that debug overlay is visible
    const debugOverlay = page.locator('.debug-overlay');
    await expect(debugOverlay).toBeVisible();

    // Check for photo management section (which contains front photo debug)
    const photoManagementSection = page.locator('.photo-management-section');
    await expect(photoManagementSection).toBeVisible();

    // Check for the front photo debug text
    const frontPhotoHeader = page.locator('text=📂 Front Photo Debug.');
    await expect(frontPhotoHeader).toBeVisible();

    // Check for the debug note showing correct mode count
    const debugNote = page.locator('.debug-note');
    await expect(debugNote).toContainText(`State 5/${MAX_DEBUG_MODES}`);
  });
});
