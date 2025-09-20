import { test, expect } from '@playwright/test';
import { createTestUsers, loginAsTestUser } from './helpers/testUsers';

test.describe('Authentication Integration', () => {
  test.beforeEach(async ({ page }) => {
    // Clean up test users before each test
    const response = await fetch('http://localhost:8055/api/debug/recreate-test-users', {
      method: 'POST'
    });
    const result = await response.json();
    console.log('🢄Test cleanup result:', result);
  });

  test('should login successfully with valid credentials', async ({ page }) => {
    // Create test users for this test
    const result = await createTestUsers();
    const testPassword = result.passwords.test;

    await loginAsTestUser(page, testPassword);
    await expect(page).toHaveURL('/');
  });

  test('should show error for invalid username', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    
    await page.fill('input[type="text"]', 'invaliduser');
    await page.fill('input[type="password"]', 'anypassword');
    await page.click('button[type="submit"]');
    
    // Should stay on login page and show error
    await page.waitForTimeout(2000);
    await expect(page).toHaveURL('/login');
    
    // Check for error message (adjust selector based on your UI)
    const errorMessage = page.locator('.error-message, .alert-error, [data-testid="error-message"]');
    await expect(errorMessage).toBeVisible();
  });

  test('should show error for invalid password', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    
    await page.fill('input[type="text"]', 'test');
    await page.fill('input[type="password"]', 'wrongpassword');
    await page.click('button[type="submit"]');
    
    // Should stay on login page and show error
    await page.waitForTimeout(2000);
    await expect(page).toHaveURL('/login');
    
    // Check for error message
    const errorMessage = page.locator('.error-message, .alert-error, [data-testid="error-message"]');
    await expect(errorMessage).toBeVisible();
  });

  test('should show validation popup for empty credentials', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    
    // Check that form has required attributes that will trigger browser validation
    const usernameInput = page.locator('input[type="text"]');
    const passwordInput = page.locator('input[type="password"]');
    
    // Verify inputs have required attributes
    await expect(usernameInput).toHaveAttribute('required', '');
    await expect(passwordInput).toHaveAttribute('required', '');
    
    // Try to submit with empty fields - browser will show validation popup
    await page.click('button[type="submit"]');
    
    // Should stay on login page due to validation
    await page.waitForTimeout(1000);
    await expect(page).toHaveURL('/login');
    
    // Verify that the form is still empty (validation prevented submission)
    await expect(usernameInput).toHaveValue('');
    await expect(passwordInput).toHaveValue('');
  });
});