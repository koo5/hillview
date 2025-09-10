import { test, expect } from '@playwright/test';

test('debug filenames', async ({ page }) => {
  // Clean up test users first
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
  
  // Login first
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  
  await page.fill('input[type="text"]', 'test');
  await page.fill('input[type="password"]', testPassword);
  await page.click('button[type="submit"]');
  await page.waitForURL('/', { timeout: 15000 });
  
  // Go to photos page
  await page.goto('/photos');
  await page.waitForLoadState('networkidle');
  
  // Wait for photos to load
  await page.waitForTimeout(2000);
  
  // Get all photo cards and their data-filename attributes
  const photoCards = await page.locator('[data-testid="photo-card"]').all();
  console.log(`Found ${photoCards.length} photo cards`);
  
  for (let i = 0; i < photoCards.length; i++) {
    const card = photoCards[i];
    const filename = await card.getAttribute('data-filename');
    const displayFilename = await card.locator('[data-testid="photo-filename"]').textContent();
    console.log(`Photo ${i + 1}:`, {
      dataFilename: filename,
      displayFilename: displayFilename,
    });
  }
  
  // Try to find a specific photo using different approaches
  const targetFilename = '2025-07-10-19-10-37_🔶∏🗿↻🌞🌲.jpg';
  console.log('🢄Looking for filename:', targetFilename);
  
  const byDataFilename = page.locator(`[data-testid="photo-card"][data-filename="${targetFilename}"]`);
  console.log('🢄Found by data-filename:', await byDataFilename.count());
  
  const byText = page.locator('[data-testid="photo-filename"]', { hasText: targetFilename });
  console.log('🢄Found by text content:', await byText.count());
  
  const byContainsText = page.locator('[data-testid="photo-filename"]:has-text("2025-07-10-19-10-37")');
  console.log('🢄Found by partial text:', await byContainsText.count());
});