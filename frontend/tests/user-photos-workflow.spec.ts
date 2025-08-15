import { test, expect } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

test.describe('User Photos Workflow', () => {
  // Test assets and expected filenames
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = path.dirname(__filename);
  const testAssetsDir = path.join(__dirname, '..', 'test-assets');
  const testPhotos = [
    '2025-07-10-19-10-37_🔶∏🗿↻🌞🌲.jpg',
    '2025-07-10-19-10-39_👁️💫🔷⤵️🌪️☀️.jpg',
    '2025-07-10-19-10-41_⤴️🦢𝄞🔹🪐♪.jpg',
    '2025-07-10-19-10-45_Φ✨⤴️↗️⟸🌪️.jpg'
  ];

  test.beforeEach(async ({ page }) => {
    // Login with test user before each test
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    
    await page.fill('input[type="text"]', 'test');
    await page.fill('input[type="password"]', 'test123');
    await page.click('button[type="submit"]');
    
    // Wait for login success and redirect
    await expect(page).toHaveURL('/');
    await page.waitForLoadState('networkidle');
  });

  test('should upload photos and verify exact filenames in My Photos page', async ({ page }) => {
    // Navigate to My Photos page
    await page.goto('/photos');
    await page.waitForLoadState('networkidle');
    
    // Verify we're on the photos page
    await expect(page.locator('h1')).toContainText('My Photos');
    await expect(page.locator('[data-testid="photos-grid"]')).toBeVisible();

    // Get initial photo count
    const photosListLocator = page.locator('[data-testid="photos-list"]');
    const initialPhotoCards = page.locator('[data-testid="photo-card"]');
    const initialCount = await initialPhotoCards.count();

    // Upload each test photo
    for (let i = 0; i < testPhotos.length; i++) {
      const photoName = testPhotos[i];
      const photoPath = path.join(testAssetsDir, photoName);
      
      console.log(`Uploading photo ${i + 1}/${testPhotos.length}: ${photoName}`);
      
      // Select file
      await page.locator('[data-testid="photo-file-input"]').setInputFiles(photoPath);
      
      // Wait for upload button to be enabled (file selected)
      await page.waitForFunction(() => {
        const uploadButton = document.querySelector('[data-testid="upload-submit-button"]') as HTMLButtonElement;
        return uploadButton && !uploadButton.disabled;
      }, { timeout: 5000 });
      
      // Click upload button
      await page.locator('[data-testid="upload-submit-button"]').click();
      
      // Wait for upload to complete - button should show "Upload Photo" not "Uploading..."
      await page.waitForFunction(() => {
        const uploadButton = document.querySelector('[data-testid="upload-submit-button"]') as HTMLButtonElement;
        return uploadButton && uploadButton.textContent?.includes('Upload Photo');
      }, { timeout: 15000 });
      
      // Wait for file input to be cleared (indicating upload completed)
      await page.waitForFunction(() => {
        const input = document.querySelector('[data-testid="photo-file-input"]') as HTMLInputElement;
        return input && input.value === '';
      }, { timeout: 5000 });
      
      // Wait for photo count to increase (new photo added to list)
      const expectedPhotoCount = initialCount + i + 1;
      await page.waitForFunction((expectedCount) => {
        const photoCards = document.querySelectorAll('[data-testid="photo-card"]');
        return photoCards.length >= expectedCount;
      }, expectedPhotoCount, { timeout: 10000 });
    }

    // Verify all photos are uploaded and visible in the My Photos page
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Check that we have more photos than initially
    const finalPhotoCards = page.locator('[data-testid="photo-card"]');
    const finalCount = await finalPhotoCards.count();
    
    expect(finalCount).toBeGreaterThan(initialCount);
    console.log(`Photo count increased from ${initialCount} to ${finalCount}`);

    // Verify each uploaded photo appears with exact filename
    for (const photoName of testPhotos) {
      console.log(`Checking for photo: ${photoName}`);
      
      // Look for photo card with this exact filename
      const photoCard = page.locator(`[data-testid="photo-card"][data-filename="${photoName}"]`);
      await expect(photoCard).toBeVisible({ timeout: 5000 });
      
      // Verify the filename is displayed in the UI
      const filenameElement = photoCard.locator('[data-testid="photo-filename"]');
      await expect(filenameElement).toContainText(photoName);
      
      // Verify thumbnail is present
      const thumbnail = photoCard.locator('[data-testid="photo-thumbnail"]');
      await expect(thumbnail).toBeVisible();
      
      console.log(`✓ Found photo: ${photoName}`);
    }

    console.log('All test photos verified successfully!');
  });

  test('should delete uploaded photos by exact filename', async ({ page }) => {
    // First, ensure we have some photos to delete
    await page.goto('/photos');
    await page.waitForLoadState('networkidle');

    // Get current photo cards
    const photoCards = page.locator('[data-testid="photo-card"]');
    const initialCount = await photoCards.count();

    if (initialCount === 0) {
      // Upload one photo first if none exist
      const photoPath = path.join(testAssetsDir, testPhotos[0]);
      await page.locator('[data-testid="photo-file-input"]').setInputFiles(photoPath);
      await page.waitForTimeout(500);
      await page.locator('[data-testid="upload-submit-button"]').click();
      await page.waitForTimeout(3000);
      await page.reload();
      await page.waitForLoadState('networkidle');
    }

    // Find and delete photos with our test filenames
    for (const photoName of testPhotos) {
      const photoCard = page.locator(`[data-testid="photo-card"][data-filename="${photoName}"]`);
      
      if (await photoCard.isVisible()) {
        console.log(`Deleting photo: ${photoName}`);
        
        // Click delete button for this specific photo
        const deleteButton = photoCard.locator('[data-testid="delete-photo-button"]');
        await deleteButton.click();
        
        // Handle confirmation dialog
        page.once('dialog', dialog => {
          expect(dialog.message()).toContain('Are you sure you want to delete this photo?');
          dialog.accept();
        });
        
        // Wait for deletion to complete
        await page.waitForTimeout(1000);
        
        // Verify photo is no longer visible
        await expect(photoCard).not.toBeVisible({ timeout: 5000 });
        
        console.log(`✓ Deleted photo: ${photoName}`);
      } else {
        console.log(`Photo not found for deletion: ${photoName}`);
      }
    }
  });

  test('should handle upload validation correctly', async ({ page }) => {
    await page.goto('/photos');
    await page.waitForLoadState('networkidle');

    // Try to upload without selecting a file
    const uploadButton = page.locator('[data-testid="upload-submit-button"]');
    await expect(uploadButton).toBeDisabled();

    // Select a valid file
    const photoPath = path.join(testAssetsDir, testPhotos[0]);
    await page.locator('[data-testid="photo-file-input"]').setInputFiles(photoPath);
    
    // Upload button should now be enabled
    await expect(uploadButton).toBeEnabled();
  });

  test.afterEach(async ({ page }) => {
    // Logout after each test
    try {
      await page.goto('/');
      await page.waitForTimeout(1000);
      
      await page.click('.hamburger');
      await page.waitForTimeout(500);
      
      const logoutButton = page.locator('button:has-text("Logout")');
      if (await logoutButton.isVisible()) {
        await logoutButton.click();
        await page.waitForTimeout(1000);
      }
    } catch (error) {
      console.log('Logout failed in afterEach:', error);
    }
  });
});