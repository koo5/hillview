import { test, expect } from '@playwright/test';

test('Multi-file upload should work correctly', async ({ page }) => {
  // Clean test users first
  const response = await fetch('http://localhost:8055/api/debug/recreate-test-users', {
    method: 'POST'
  });
  console.log('Test cleanup result:', await response.json());
  
  // Login with test user
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  
  await page.fill('input[type="text"]', 'test');
  await page.fill('input[type="password"]', 'test123');
  await page.click('button[type="submit"]');
  
  // Wait for login success and redirect
  await expect(page).toHaveURL('/');
  await page.waitForLoadState('networkidle');
  
  // Navigate to photos page
  await page.goto('/photos');
  await page.waitForLoadState('networkidle');
  
  // Select multiple files
  const fileInput = page.locator('[data-testid="photo-file-input"]');
  await fileInput.setInputFiles([
    'test-assets/2025-07-10-19-10-37_🔶∏🗿↻🌞🌲.jpg',
    'test-assets/2025-07-10-19-10-39_👁️💫🔷⤵️🌪️☀️.jpg'
  ]);
  
  // Check selected files display
  const selectedFiles = page.locator('.selected-files');
  await expect(selectedFiles).toBeVisible();
  await expect(selectedFiles).toContainText('Selected files: 2');
  
  // Check upload button text
  const uploadButton = page.locator('[data-testid="upload-submit-button"]');
  await expect(uploadButton).toContainText('Upload 2 Photos');
  await expect(uploadButton).not.toBeDisabled();
  
  console.log('✓ Multi-file selection UI working');
  
  // Start upload
  await uploadButton.click();
  
  // Wait for upload to complete
  await page.waitForFunction(() => {
    const input = document.querySelector('[data-testid="photo-file-input"]') as HTMLInputElement;
    return input && input.value === '';
  }, { timeout: 15000 });
  
  // Check activity log for batch upload messages
  const activityLog = page.locator('.activity-log');
  await expect(activityLog).toBeVisible();
  
  const logText = await activityLog.textContent();
  
  // Should contain batch upload messages
  expect(logText).toContain('Starting batch upload: 2 files');
  expect(logText).toContain('Batch complete:');
  
  console.log('✓ Batch upload completed successfully');
  
  // Verify photos appeared in the grid
  await page.waitForTimeout(2000); // Wait for photos to load
  const photoCards = page.locator('[data-testid="photo-card"]');
  const photoCount = await photoCards.count();
  
  expect(photoCount).toBeGreaterThanOrEqual(2);
  console.log(`✓ Found ${photoCount} photos in grid`);
});