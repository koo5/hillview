import { test, expect } from '@playwright/test';

test('debug login', async ({ page }) => {
  // Navigate to login page
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  
  console.log('Current URL:', await page.url());
  console.log('Page title:', await page.title());
  
  // Check if form elements exist
  const usernameInput = page.locator('input[type="text"]');
  const passwordInput = page.locator('input[type="password"]');
  const submitButton = page.locator('button[type="submit"]');
  
  console.log('Username input found:', await usernameInput.count() > 0);
  console.log('Password input found:', await passwordInput.count() > 0);
  console.log('Submit button found:', await submitButton.count() > 0);
  
  // Fill form
  await usernameInput.fill('test');
  await passwordInput.fill('test123');
  
  console.log('Username value:', await usernameInput.inputValue());
  console.log('Password value:', await passwordInput.inputValue());
  console.log('Submit button text:', await submitButton.textContent());
  
  // Check for any error messages before submitting
  const errorMessage = page.locator('.error-message');
  console.log('Error message count before submit:', await errorMessage.count());
  
  // Submit form
  await submitButton.click();
  
  // Wait a bit and check for errors
  await page.waitForTimeout(2000);
  
  console.log('URL after submit:', await page.url());
  console.log('Error message count after submit:', await errorMessage.count());
  if (await errorMessage.count() > 0) {
    console.log('Error message text:', await errorMessage.textContent());
  }
  
  // Listen to console and network events
  page.on('console', msg => console.log('BROWSER CONSOLE:', msg.text()));
  page.on('response', response => {
    if (response.url().includes('/auth/token')) {
      console.log('AUTH REQUEST:', response.status(), response.url());
    }
  });
  
  // Check if backend is responding
  try {
    const response = await page.evaluate(async () => {
      const res = await fetch('http://localhost:8055/api/debug');
      return { status: res.status, text: await res.text() };
    });
    console.log('Backend debug response:', response);
  } catch (error) {
    console.log('Backend debug error:', error);
  }
});