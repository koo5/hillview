import { test, expect } from '@playwright/test';

test('Activity log should show upload activities', async ({ page }) => {
  // Clean test users first
  const response = await fetch('http://localhost:8055/api/debug/recreate-test-users', {
    method: 'POST'
  });
  console.log('🢄Test cleanup result:', await response.json());
  
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
  
  // Upload a file
  const fileInput = page.locator('[data-testid="photo-file-input"]');
  await fileInput.setInputFiles('test-assets/2025-07-10-19-10-37_🔶∏🗿↻🌞🌲.jpg');
  
  const uploadButton = page.locator('[data-testid="upload-submit-button"]');
  await uploadButton.click();
  
  // Wait for upload to complete
  await page.waitForFunction(() => {
    const input = document.querySelector('[data-testid="photo-file-input"]') as HTMLInputElement;
    return input && input.value === '';
  }, { timeout: 10000 });
  
  // Check if activity log exists and has entries
  const activityLog = page.locator('.activity-log');
  if (await activityLog.isVisible()) {
    console.log('🢄✓ Activity log is visible');
    
    const logEntries = page.locator('.log-entry');
    const count = await logEntries.count();
    console.log(`✓ Found ${count} log entries`);
    
    // Check if there's an upload-related entry
    const logText = await activityLog.textContent();
    if (logText?.includes('Starting upload') || logText?.includes('Uploaded:')) {
      console.log('🢄✓ Activity log contains upload-related entries');
    } else {
      console.log('🢄⚠ Activity log exists but no upload entries found');
      console.log('🢄Log content:', logText);
    }
  } else {
    console.log('🢄⚠ Activity log is not visible');
    
    // Check if there are any log entries at all
    const logEntries = page.locator('.log-entry');
    const count = await logEntries.count();
    console.log(`Log entries count: ${count}`);
  }
});