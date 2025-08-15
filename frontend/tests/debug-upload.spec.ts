import { test, expect } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

test('debug upload', async ({ page }) => {
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = path.dirname(__filename);
  const testAssetsDir = path.join(__dirname, '..', 'test-assets');
  const testPhoto = '2025-07-10-19-10-37_🔶∏🗿↻🌞🌲.jpg';
  const photoPath = path.join(testAssetsDir, testPhoto);

  // Login first
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  
  await page.fill('input[type="text"]', 'test');
  await page.fill('input[type="password"]', 'test123');
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL('/');
  
  // Go to photos page
  await page.goto('/photos');
  await page.waitForLoadState('networkidle');
  
  console.log('Current URL:', await page.url());
  
  // Check if upload section exists
  const uploadSection = page.locator('[data-testid="upload-section"]');
  console.log('Upload section visible:', await uploadSection.isVisible());
  
  const fileInput = page.locator('[data-testid="photo-file-input"]');
  const uploadButton = page.locator('[data-testid="upload-submit-button"]');
  
  console.log('File input visible:', await fileInput.isVisible());
  console.log('Upload button visible:', await uploadButton.isVisible());
  console.log('Upload button text before:', await uploadButton.textContent());
  console.log('Upload button disabled before:', await uploadButton.isDisabled());
  
  // Listen to network requests
  page.on('response', response => {
    if (response.url().includes('/photos/upload')) {
      console.log('Upload request:', response.status(), response.url());
    }
  });
  
  // Listen to console logs
  page.on('console', msg => {
    if (msg.text().includes('Error') || msg.text().includes('Upload')) {
      console.log('BROWSER CONSOLE:', msg.text());
    }
  });
  
  // Select file
  console.log('Setting file:', photoPath);
  await fileInput.setInputFiles(photoPath);
  
  await page.waitForTimeout(1000);
  
  console.log('Upload button text after file select:', await uploadButton.textContent());
  console.log('Upload button disabled after file select:', await uploadButton.isDisabled());
  
  // Click upload
  console.log('Clicking upload button...');
  await uploadButton.click();
  
  await page.waitForTimeout(2000);
  
  console.log('Upload button text after click:', await uploadButton.textContent());
  console.log('Upload button disabled after click:', await uploadButton.isDisabled());
  
  // Wait and check again
  await page.waitForTimeout(5000);
  
  console.log('Upload button text after wait:', await uploadButton.textContent());
  console.log('Upload button disabled after wait:', await uploadButton.isDisabled());
  
  // Check for any error messages
  const errorMessage = page.locator('.error-message');
  if (await errorMessage.count() > 0) {
    console.log('Error message:', await errorMessage.textContent());
  }
});