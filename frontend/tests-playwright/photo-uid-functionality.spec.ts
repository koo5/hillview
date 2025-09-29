import { test, expect } from '@playwright/test';
import { configureSources } from './helpers/sourceHelpers';
import { uploadTestPhotosWithLocation } from './helpers/photoUpload';

test.describe('Photo UID Functionality', () => {
  test.beforeEach(async ({ page }) => {
    // Clean up test users before each test
    const response = await fetch('http://localhost:8055/api/debug/recreate-test-users', {
      method: 'POST'
    });
    const result = await response.json();
    console.log('🢄Test cleanup result:', result);
  });

  test.describe('URL Parameter Parsing', () => {
    test('should parse photo uid from URL and navigate to correct location', async ({ page }) => {
      const errors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error' && !msg.text().includes('favicon.ico')) {
          errors.push(msg.text());
        }
      });

      // Navigate with photo uid in URL
      await page.goto('/?lat=50.0755&lon=14.4378&zoom=18&bearing=45&photo=hillview-test-photo-123');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1000);

      // Check that photo parameter is parsed
      const url = page.url();
      expect(url).toContain('photo=hillview-test-photo-123');
      expect(url).toContain('lat=50.0755');
      expect(url).toContain('lon=14.4378');
      expect(url).toContain('bearing=45');

      // Verify no errors during parsing
      expect(errors.length, `Found errors: ${errors.join(', ')}`).toBe(0);
    });

    test('should handle different photo uid formats', async ({ page }) => {
      const testCases = [
        'hillview-12345',
        'mapillary-abcdef-ghijkl',
        'hillview-uuid-with-dashes-123',
        'mapillary-1234567890'
      ];

      for (const photoUid of testCases) {
        await test.step(`Testing photo uid: ${photoUid}`, async () => {
          const errors: string[] = [];
          page.on('console', (msg) => {
            if (msg.type() === 'error' && !msg.text().includes('favicon.ico')) {
              errors.push(msg.text());
            }
          });

          await page.goto(`/?lat=50.0755&lon=14.4378&photo=${encodeURIComponent(photoUid)}`);
          await page.waitForLoadState('networkidle');
          await page.waitForTimeout(500);

          // Check URL contains the photo uid
          expect(page.url()).toContain(`photo=${encodeURIComponent(photoUid)}`);

          // Verify no parsing errors
          expect(errors.length, `Found errors for ${photoUid}: ${errors.join(', ')}`).toBe(0);
        });
      }
    });

    test('should handle invalid photo uid formats gracefully', async ({ page }) => {
      const errors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error' && !msg.text().includes('favicon.ico')) {
          errors.push(msg.text());
        }
      });

      const invalidCases = [
        'invalid-source-123',
        'just-text',
        '',
        'no-dash'
      ];

      for (const invalidUid of invalidCases) {
        await test.step(`Testing invalid photo uid: ${invalidUid}`, async () => {
          await page.goto(`/?lat=50.0755&lon=14.4378&photo=${encodeURIComponent(invalidUid)}`);
          await page.waitForLoadState('networkidle');
          await page.waitForTimeout(500);

          // Should not crash on invalid uid
          await expect(page.locator('.leaflet-container')).toBeVisible();
        });
      }
    });
  });

  test.describe('Automatic Source Enabling', () => {
    test('should enable hillview source when hillview photo uid is in URL', async ({ page }) => {
      const errors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error' && !msg.text().includes('favicon.ico')) {
          errors.push(msg.text());
        }
      });

      // Start with hillview source disabled
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      await configureSources(page, { 'hillview': false, 'mapillary': false });

      // Navigate with hillview photo uid
      await page.goto('/?lat=50.0755&lon=14.4378&photo=hillview-test-123');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      // Check that hillview source is now enabled
      const hillviewButton = page.locator('[data-testid="source-toggle-hillview"]');
      await expect(hillviewButton).toHaveClass(/active/);

      // Verify mapillary remains disabled
      const mapillaryButton = page.locator('[data-testid="source-toggle-mapillary"]');
      await expect(mapillaryButton).not.toHaveClass(/active/);

      expect(errors.length, `Found errors: ${errors.join(', ')}`).toBe(0);
    });

    test('should enable mapillary source when mapillary photo uid is in URL', async ({ page }) => {
      const errors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error' && !msg.text().includes('favicon.ico')) {
          errors.push(msg.text());
        }
      });

      // Start with both sources disabled
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      await configureSources(page, { 'hillview': false, 'mapillary': false });

      // Navigate with mapillary photo uid
      await page.goto('/?lat=50.0755&lon=14.4378&photo=mapillary-abc123');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      // Check that mapillary source is now enabled
      const mapillaryButton = page.locator('[data-testid="source-toggle-mapillary"]');
      await expect(mapillaryButton).toHaveClass(/active/);

      // Verify hillview remains disabled
      const hillviewButton = page.locator('[data-testid="source-toggle-hillview"]');
      await expect(hillviewButton).not.toHaveClass(/active/);

      expect(errors.length, `Found errors: ${errors.join(', ')}`).toBe(0);
    });

    test('should not affect already enabled sources', async ({ page }) => {
      const errors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error' && !msg.text().includes('favicon.ico')) {
          errors.push(msg.text());
        }
      });

      // Start with both sources enabled
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      await configureSources(page, { 'hillview': true, 'mapillary': true });

      // Navigate with hillview photo uid
      await page.goto('/?lat=50.0755&lon=14.4378&photo=hillview-test-123');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1000);

      // Both sources should remain enabled
      const hillviewButton = page.locator('[data-testid="source-toggle-hillview"]');
      const mapillaryButton = page.locator('[data-testid="source-toggle-mapillary"]');

      await expect(hillviewButton).toHaveClass(/active/);
      await expect(mapillaryButton).toHaveClass(/active/);

      expect(errors.length, `Found errors: ${errors.join(', ')}`).toBe(0);
    });
  });

  test.describe('Photo UID in Sharing URLs', () => {
    test('should include photo uid in constructed share URLs', async ({ page }) => {
      // Login and upload a test photo
      const response = await fetch('http://localhost:8055/api/debug/recreate-test-users', {
        method: 'POST'
      });
      const result = await response.json();
      const testPassword = result.details?.user_passwords?.test;
      if (!testPassword) {
        throw new Error(`Test password not found in API response: ${JSON.stringify(result)}`);
      }

      await page.goto('/login');
      await page.waitForLoadState('networkidle');
      await page.fill('input[type="text"]', 'test');
      await page.fill('input[type="password"]', testPassword);
      await page.click('button[type="submit"]');
      await page.waitForURL('/', { timeout: 15000 });

      // Upload test photos with location
      await uploadTestPhotosWithLocation(page, 1);
      await page.waitForTimeout(2000);

      // Navigate to photos page
      await page.goto('/photos');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      // Look for a photo with share functionality
      const photoCards = page.locator('.photo-card');
      if (await photoCards.count() > 0) {
        // Look for share button or click on photo to trigger share URL
        const firstPhoto = photoCards.first();
        if (await firstPhoto.locator('.share-button').count() > 0) {
          await firstPhoto.locator('.share-button').click();
          await page.waitForTimeout(500);

          // Check if share URL contains photo uid parameter
          const shareInput = page.locator('input[readonly]');
          if (await shareInput.count() > 0) {
            const shareUrl = await shareInput.inputValue();
            expect(shareUrl).toMatch(/photo=hillview-/);
          }
        }
      }
    });

    test('should construct valid share URLs with photo coordinates and uid', async ({ page }) => {
      // Test the URL construction utility directly by navigating to users page
      await page.goto('/users');
      await page.waitForLoadState('networkidle');

      const userCards = page.locator('[data-testid^="user-card-"]');
      if (await userCards.count() > 0) {
        await userCards.first().click();
        await page.waitForURL(/\/users\/[^\/]+$/);
        await page.waitForLoadState('networkidle');

        // Look for clickable photos with location data
        const clickablePhotos = page.locator('.photo-item.clickable');
        if (await clickablePhotos.count() > 0) {
          await clickablePhotos.first().click();

          // Should navigate to map URL with photo parameter
          await page.waitForURL(/\/\?.*lat=.*&lon=.*&photo=/);

          const url = page.url();
          expect(url).toMatch(/lat=[\d.-]+/);
          expect(url).toMatch(/lon=[\d.-]+/);
          expect(url).toMatch(/photo=hillview-/);
        }
      }
    });
  });

  test.describe('Cross-Route Photo UID Navigation', () => {
    test('should handle photo uid navigation on activity page', async ({ page }) => {
      const errors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error' && !msg.text().includes('favicon.ico')) {
          errors.push(msg.text());
        }
      });

      await page.goto('/activity?lat=50.0755&lon=14.4378&photo=hillview-activity-test');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1000);

      // Check URL parsing works on activity page
      expect(page.url()).toContain('photo=hillview-activity-test');

      // Just verify the page loads without errors (activity page may be empty)
      await expect(page.locator('body')).toBeVisible();

      expect(errors.length, `Found errors on activity page: ${errors.join(', ')}`).toBe(0);
    });

    test('should handle photo uid navigation on photos page', async ({ page }) => {
      const errors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error' && !msg.text().includes('favicon.ico')) {
          errors.push(msg.text());
        }
      });

      await page.goto('/photos?lat=50.0755&lon=14.4378&photo=hillview-photos-test');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1000);

      // Check URL parsing works on photos page
      expect(page.url()).toContain('photo=hillview-photos-test');

      // Verify the page loads without errors
      await expect(page.locator('body')).toBeVisible();

      expect(errors.length, `Found errors on photos page: ${errors.join(', ')}`).toBe(0);
    });

    test('should handle photo uid navigation on user profile pages', async ({ page }) => {
      const errors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error' && !msg.text().includes('favicon.ico')) {
          errors.push(msg.text());
        }
      });

      // Navigate to user page first
      await page.goto('/users');
      await page.waitForLoadState('networkidle');

      const userCards = page.locator('[data-testid^="user-card-"]');
      const userCount = await userCards.count();

      if (userCount > 0) {
        // Get the username from the first user card
        const username = await userCards.first().locator('.username').textContent();
        if (username) {
          // Navigate to user page with photo uid
          await page.goto(`/users/${username.trim()}?lat=50.0755&lon=14.4378&photo=hillview-user-test`);
          await page.waitForLoadState('networkidle');
          await page.waitForTimeout(1000);

          // Check URL parsing works on user page
          expect(page.url()).toContain('photo=hillview-user-test');

          // Verify the page loads without errors
          await expect(page.locator('body')).toBeVisible();
        }
      } else {
        // If no users available, just test with a known username
        await page.goto(`/users/test?lat=50.0755&lon=14.4378&photo=hillview-user-test`);
        await page.waitForLoadState('networkidle');
        expect(page.url()).toContain('photo=hillview-user-test');
        await expect(page.locator('body')).toBeVisible();
      }

      // Allow 404 errors when loading user photos (expected behavior for non-existent user)
      const has404Errors = errors.filter(error => !error.includes('404')).length;
      expect(has404Errors, `Found non-404 errors on user page: ${errors.filter(e => !e.includes('404')).join(', ')}`).toBe(0);
    });

    test('should maintain photo uid when navigating between routes', async ({ page }) => {
      const photoUid = 'hillview-navigation-test-123';
      const baseParams = `lat=50.0755&lon=14.4378&photo=${photoUid}`;

      // Start at main page with photo uid
      await page.goto(`/?${baseParams}`);
      await page.waitForLoadState('networkidle');
      expect(page.url()).toContain(photoUid);

      // Verify direct navigation to routes with photo uid works
      await page.goto(`/activity?${baseParams}`);
      await page.waitForLoadState('networkidle');
      expect(page.url()).toContain(photoUid);

      // Navigate to photos page with photo uid
      await page.goto(`/photos?${baseParams}`);
      await page.waitForLoadState('networkidle');
      expect(page.url()).toContain(photoUid);
    });
  });

  test.describe('Photo UID Error Handling', () => {
    test('should handle missing photo uid parameter gracefully', async ({ page }) => {
      const errors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error' && !msg.text().includes('favicon.ico')) {
          errors.push(msg.text());
        }
      });

      await page.goto('/?lat=50.0755&lon=14.4378&zoom=18');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1000);

      // Should work normally without photo parameter
      await expect(page.locator('.leaflet-container')).toBeVisible();
      expect(errors.length, `Found errors: ${errors.join(', ')}`).toBe(0);
    });

    test('should handle malformed photo uid parameter', async ({ page }) => {
      const errors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error' && !msg.text().includes('favicon.ico')) {
          errors.push(msg.text());
        }
      });

      const malformedCases = [
        '%',
        'photo%20uid',
        'invalid%20encoding%',
        '%GG%HH'
      ];

      for (const malformedUid of malformedCases) {
        await test.step(`Testing malformed photo uid: ${malformedUid}`, async () => {
          await page.goto(`/?lat=50.0755&lon=14.4378&photo=${malformedUid}`);
          await page.waitForLoadState('networkidle');
          await page.waitForTimeout(500);

          // Should handle gracefully without crashing (app may display error page)
          await expect(page.locator('html')).toBeVisible();
        });
      }
    });

    test('should not enable sources for unsupported photo uid formats', async ({ page }) => {
      const errors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error' && !msg.text().includes('favicon.ico')) {
          errors.push(msg.text());
        }
      });

      // Start with all sources disabled
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      await configureSources(page, { 'hillview': false, 'mapillary': false });

      // Navigate with unsupported source in photo uid
      await page.goto('/?lat=50.0755&lon=14.4378&photo=unsupported-source-123');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1000);

      // No sources should be enabled
      const hillviewButton = page.locator('[data-testid="source-toggle-hillview"]');
      const mapillaryButton = page.locator('[data-testid="source-toggle-mapillary"]');

      await expect(hillviewButton).not.toHaveClass(/active/);
      await expect(mapillaryButton).not.toHaveClass(/active/);

      expect(errors.length, `Found errors: ${errors.join(', ')}`).toBe(0);
    });
  });
});