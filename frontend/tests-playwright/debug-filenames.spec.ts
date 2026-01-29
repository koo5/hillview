import { test, expect } from '@playwright/test';
import { createTestUsers, loginAsTestUser } from './helpers/testUsers';

test.describe('Debug Filenames', () => {
  let testPasswords: { test: string; admin: string; testuser: string };

  test.beforeEach(async () => {
    // Clean up and recreate test users before each test
    const result = await createTestUsers();
    testPasswords = result.passwords;
  });

  test('debug filenames', async ({ page }) => {
    // Login first
    await loginAsTestUser(page, testPasswords.test);

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
});
