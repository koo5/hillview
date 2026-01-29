import { test, expect } from '@playwright/test';
import { uploadTestPhotosWithLocation } from './helpers/photoUpload';
import { createTestUsers, loginAsTestUser } from './helpers/testUsers';

test.describe('Users Pages and Navigation', () => {
  let testPasswords: { test: string; admin: string; testuser: string };

  test.beforeEach(async () => {
    // Clean up and recreate test users before each test
    const result = await createTestUsers();
    testPasswords = result.passwords;
  });

  test('should load users list page and display user cards', async ({ page }) => {
    await page.goto('/users');
    await page.waitForLoadState('networkidle');

    // Check for users grid
    await expect(page.locator('.users-grid')).toBeVisible();

    // Check for user cards
    const userCards = page.locator('[data-testid^="user-card-"]');
    expect(await userCards.count()).toBeGreaterThan(0);

    // Check first user card structure
    const firstCard = userCards.first();
    await expect(firstCard.locator('.user-photo')).toBeVisible();
    await expect(firstCard.locator('.username')).toBeVisible();
    await expect(firstCard.locator('.photo-count')).toBeVisible();
  });

  test('should navigate from users list to individual user page', async ({ page }) => {
    await page.goto('/users');
    await page.waitForLoadState('networkidle');

    const userCards = page.locator('[data-testid^="user-card-"]');
    await expect(userCards.first()).toBeVisible();

    // Click first user card
    await userCards.first().click();

    // Should navigate to user page
    await page.waitForURL(/\/users\/[^\/]+$/);

    // Wait for the loading to complete and content to be rendered
    await page.waitForLoadState('networkidle');

    // Wait for loading container to disappear (if it exists)
    try {
      await page.waitForSelector('.loading-container', { state: 'hidden', timeout: 5000 });
    } catch {
      // Loading container might not appear if page loads quickly
    }

    // Check that either photos section or empty state is visible
    const hasPhotos = await page.locator('.photos-section').isVisible();
    const isEmpty = await page.locator('.empty-state').isVisible();
    expect(hasPhotos || isEmpty).toBe(true);

    // Back button should be visible in photos section, but not in empty state
    if (hasPhotos) {
      await expect(page.locator('.back-button')).toBeVisible();
    }
  });

  test('should navigate from activity page usernames to user pages', async ({ page }) => {
    // Login first
    await loginAsTestUser(page, testPasswords.test);

    // Navigate to activity page
    await page.goto('/activity');
    await page.waitForLoadState('networkidle');

    // Look for username links in activity
    const usernameLinks = page.locator('.username-link');
    if (await usernameLinks.count() > 0) {
      await usernameLinks.first().click();
      await page.waitForURL(/\/users\/[^\/]+$/);
      await expect(page.locator('.photos-section')).toBeVisible();
    }
  });

  test('should make photos clickable to navigate to map', async ({ page }) => {
    // Login and ensure we have some photos
    await loginAsTestUser(page, testPasswords.test);

    // Upload some test photos with location data for the test user
    await uploadTestPhotosWithLocation(page, 2);

    // Go to users page and click on test user
    await page.goto('/users');
    await page.waitForLoadState('networkidle');

    const testUserCard = page.locator('[data-testid="user-card-test"]');
    if (await testUserCard.count() > 0) {
      await testUserCard.click();
      await page.waitForURL(/\/users\/[^\/]+$/);

      // Look for clickable photos with location data
      const clickablePhotos = page.locator('.photo-card.clickable');
      if (await clickablePhotos.count() > 0) {
        await clickablePhotos.first().click();
        // Should navigate to map with coordinates
        await page.waitForURL(/\/\?.*lat=.*&lon=/);
        await expect(page.locator('.leaflet-container')).toBeVisible();
      }
    }
  });

  test('should handle user page pagination', async ({ page }) => {
    await page.goto('/users');
    await page.waitForLoadState('networkidle');

    const userCards = page.locator('[data-testid^="user-card-"]');
    if (await userCards.count() > 0) {
      await userCards.first().click();
      await page.waitForURL(/\/users\/[^\/]+$/);

      // Check if load more button exists (indicates pagination)
      const loadMoreButton = page.locator('.load-more-button');
      if (await loadMoreButton.isVisible()) {
        await loadMoreButton.click();
        // Should load more photos without errors
        await page.waitForTimeout(2000);
        await expect(page.locator('.photos-grid')).toBeVisible();
      }
    }
  });

  test('should display user statistics correctly', async ({ page }) => {
    await page.goto('/users');
    await page.waitForLoadState('networkidle');

    // Check header shows user count
    const header = page.locator('.users-grid h2');
    const headerText = await header.textContent();
    expect(headerText).toMatch(/All Users \(\d+\)/);

    // Check user cards show photo counts
    const userCards = page.locator('[data-testid^="user-card-"]');
    if (await userCards.count() > 0) {
      const photoCount = userCards.first().locator('.photo-count');
      const photoCountText = await photoCount.textContent();
      expect(photoCountText).toMatch(/\d+ photos?/);
    }
  });

  test('should handle pages without runtime errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !msg.text().includes('favicon.ico')) {
        errors.push(msg.text());
      }
    });

    await page.goto('/users');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    expect(errors.length, `Found errors: ${errors.join(', ')}`).toBe(0);
  });
});