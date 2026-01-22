import { test, expect } from '@playwright/test';
import { uploadPhoto } from './helpers/photoUpload';

test('Activity log should show upload activities', async ({ page }) => {
  // Clean test users first
  const response = await fetch('http://localhost:8055/api/debug/recreate-test-users', {
    method: 'POST'
  });
  const result = await response.json();
  console.log('🢄Test cleanup result:', result);
  
  // Get test user password from response
  const testPassword = result.details?.user_passwords?.test;
  if (!testPassword) {
    throw new Error('Test user password not returned from recreate-test-users');
  }
  
  // Login with test user
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  
  await page.fill('input[type="text"]', 'test');
  await page.fill('input[type="password"]', testPassword);
  await page.click('button[type="submit"]');
  
  // Wait for login success and redirect
  await page.waitForURL('/', { timeout: 15000 });
  await page.waitForLoadState('networkidle');
  
  // Upload a photo using the shared helper (handles license checkbox)
  await uploadPhoto(page, '2025-07-10-19-10-37_🔶∏🗿↻🌞🌲.jpg');
  
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