import { test, expect } from '@playwright/test';

test('Settings button should not be visible in web browser (non-Tauri environment)', async ({ page }) => {
  // Clean up test users
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
  
  // Navigate to photos page
  await page.goto('/photos');
  await page.waitForLoadState('networkidle');
  
  // Verify settings button is NOT visible (since we're in browser, not Tauri)
  const settingsButton = page.locator('button:has-text("Settings")');
  await expect(settingsButton).not.toBeVisible();
  console.log('🢄✓ Settings button correctly hidden in web browser');
  
  // Verify upload section is still visible
  const uploadSection = page.locator('[data-testid="upload-section"]');
  await expect(uploadSection).toBeVisible();
  console.log('🢄✓ Upload section is visible');
});