import { test, expect } from '@playwright/test';
import { createTestUsers, loginAsTestUser } from './helpers/testUsers';

test.describe('Settings Visibility', () => {
  let testPasswords: { test: string; admin: string; testuser: string };

  test.beforeEach(async () => {
    // Clean up and recreate test users before each test
    const result = await createTestUsers();
    testPasswords = result.passwords;
  });

  test('Settings button should not be visible in web browser (non-Tauri environment)', async ({ page }) => {
    // Login with test user
    await loginAsTestUser(page, testPasswords.test);

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
});
