import { test, expect } from '@playwright/test';

test.describe('Capture Button Gestures', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    
    // Open camera view
    await page.locator('[data-testid="camera-button"]').click();
    
    // Wait for camera interface to load
    await page.waitForSelector('[data-testid="single-capture-button"]', { timeout: 10000 });
  });

  test('shows only single button by default', async ({ page }) => {
    // Single button should be visible
    await expect(page.locator('[data-testid="single-capture-button"]')).toBeVisible();
    
    // Slow and fast buttons should not be visible initially
    await expect(page.locator('[data-testid="slow-capture-button"]')).not.toBeVisible();
    await expect(page.locator('[data-testid="fast-capture-button"]')).not.toBeVisible();
  });

  test('shows all buttons on long press', async ({ page }) => {
    const singleButton = page.locator('[data-testid="single-capture-button"]');
    
    // Use mouse down and hold instead of dispatchEvent
    await singleButton.hover();
    await page.mouse.down();
    
    // Wait for long press timeout (500ms + buffer)
    await page.waitForTimeout(700);
    
    // All buttons should now be visible
    await expect(page.locator('[data-testid="slow-capture-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="fast-capture-button"]')).toBeVisible();
    await expect(singleButton).toBeVisible();
    
    // Release the long press
    await page.mouse.up();
  });

  test('handles short press for single capture', async ({ page }) => {
    const singleButton = page.locator('[data-testid="single-capture-button"]');
    
    // Quick tap (should trigger single capture, not long press)
    await singleButton.dispatchEvent('pointerdown', { 
      clientX: 100, 
      clientY: 100,
      button: 0
    });
    
    // Release quickly (before long press timeout)
    await page.waitForTimeout(100);
    await singleButton.dispatchEvent('pointerup');
    
    // Should not show additional buttons
    await expect(page.locator('[data-testid="slow-capture-button"]')).not.toBeVisible();
    await expect(page.locator('[data-testid="fast-capture-button"]')).not.toBeVisible();
  });

  test('auto-hides buttons after timeout', async ({ page }) => {
    const singleButton = page.locator('[data-testid="single-capture-button"]');
    
    // Trigger long press to show buttons
    await singleButton.dispatchEvent('pointerdown', { 
      clientX: 100, 
      clientY: 100,
      button: 0
    });
    await page.waitForTimeout(600);
    await singleButton.dispatchEvent('pointerup');
    
    // Buttons should be visible
    await expect(page.locator('[data-testid="slow-capture-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="fast-capture-button"]')).toBeVisible();
    
    // Wait for auto-hide timeout (3 seconds)
    await page.waitForTimeout(3200);
    
    // Buttons should be hidden again
    await expect(page.locator('[data-testid="slow-capture-button"]')).not.toBeVisible();
    await expect(page.locator('[data-testid="fast-capture-button"]')).not.toBeVisible();
  });
});