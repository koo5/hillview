import { test, expect } from '@playwright/test';

test.describe('Debug Capture Mode', () => {
  test('should show capture system debug information in mode 4', async ({ page }) => {
    // Go to page with debug mode 4 directly via URL
    await page.goto('/?debug=4');
    
    // Wait for debug overlay to appear
    await page.waitForSelector('.debug-overlay', { timeout: 5000 });
    
    // Check that debug overlay is visible
    const debugOverlay = page.locator('.debug-overlay');
    await expect(debugOverlay).toBeVisible();
    
    // Check for capture system section
    const captureSystemSection = page.locator('.capture-system-section');
    await expect(captureSystemSection).toBeVisible();
    
    // Check for queue status subsection
    const queueStatus = page.locator('.subsection-header', { hasText: 'Queue Status:' });
    await expect(queueStatus).toBeVisible();
    
    // Check for capture statistics
    const queueSizeLabel = page.locator('.capture-label', { hasText: 'Queue Size:' });
    await expect(queueSizeLabel).toBeVisible();
    
    const processingLabel = page.locator('.capture-label', { hasText: 'Processing:' });
    await expect(processingLabel).toBeVisible();
    
    const totalCapturedLabel = page.locator('.capture-label', { hasText: 'Total Captured:' });
    await expect(totalCapturedLabel).toBeVisible();
    
    // Check for settings subsection
    const settingsHeader = page.locator('.subsection-header', { hasText: 'Settings:' });
    await expect(settingsHeader).toBeVisible();
    
    // Check for camera status subsection
    const cameraStatusHeader = page.locator('.subsection-header', { hasText: 'Camera Status:' });
    await expect(cameraStatusHeader).toBeVisible();
    
    // Check for last captured photo section (should show "No photos captured yet" initially)
    const lastPhotoHeader = page.locator('.subsection-header', { hasText: 'Last Captured Photo:' });
    await expect(lastPhotoHeader).toBeVisible();
    
    const noPhotosMessage = page.locator('.no-photos-captured');
    await expect(noPhotosMessage).toBeVisible();
    await expect(noPhotosMessage).toHaveText('No photos captured yet');
  });
  
  test('should cycle debug modes including new capture mode', async ({ page }) => {
    await page.goto('/');
    
    // Wait for page to load
    await page.waitForSelector('body', { timeout: 5000 });
    
    // Find debug button
    const debugButton = page.locator('button.debug-toggle');
    
    // Click through debug modes
    await debugButton.click(); // Mode 1
    await page.waitForTimeout(200);
    
    await debugButton.click(); // Mode 2
    await page.waitForTimeout(200);
    
    await debugButton.click(); // Mode 3
    await page.waitForTimeout(200);
    
    await debugButton.click(); // Mode 4 (capture system)
    await page.waitForTimeout(200);
    
    // Check that we're in mode 4 and capture system section is visible
    const captureSystemSection = page.locator('.capture-system-section');
    await expect(captureSystemSection).toBeVisible();
    
    await debugButton.click(); // Mode 0 (off)
    await page.waitForTimeout(200);
    
    // Debug overlay should be hidden
    const debugOverlay = page.locator('.debug-overlay');
    await expect(debugOverlay).not.toBeVisible();
  });
});