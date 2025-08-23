import { test, expect } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

test.describe('Photo Upload Tests', () => {
  test.describe.configure({ mode: 'serial' });
  
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
    // Clean up test users and photos before each test
    const response = await fetch('http://localhost:8055/api/debug/recreate-test-users', {
      method: 'POST'
    });
    const result = await response.json();
    console.log('🢄Test cleanup result:', result);
    
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

  test('debug upload - single file upload with detailed logging', async ({ page }) => {
    const testPhoto = testPhotos[0];
    const photoPath = path.join(testAssetsDir, testPhoto);

    // Go to photos page
    await page.goto('/photos');
    await page.waitForLoadState('networkidle');
    
    console.log('🢄Current URL:', await page.url());
    
    // Check if upload section exists
    const uploadSection = page.locator('[data-testid="upload-section"]');
    console.log('🢄Upload section visible:', await uploadSection.isVisible());
    
    const fileInput = page.locator('[data-testid="photo-file-input"]');
    const uploadButton = page.locator('[data-testid="upload-submit-button"]');
    
    console.log('🢄File input visible:', await fileInput.isVisible());
    console.log('🢄Upload button visible:', await uploadButton.isVisible());
    console.log('🢄Upload button text before:', await uploadButton.textContent());
    console.log('🢄Upload button disabled before:', await uploadButton.isDisabled());
    
    // Listen to network requests
    page.on('response', response => {
      if (response.url().includes('/photos/upload')) {
        console.log('🢄Upload request:', response.status(), response.url());
      }
    });
    
    // Listen to console logs
    page.on('console', msg => {
      if (msg.text().includes('Error') || msg.text().includes('Upload')) {
        console.log('🢄BROWSER CONSOLE:', msg.text());
      }
    });
    
    // Select file
    console.log('🢄Setting file:', photoPath);
    await fileInput.setInputFiles(photoPath);
    
    await page.waitForTimeout(1000);
    
    console.log('🢄Upload button text after file select:', await uploadButton.textContent());
    console.log('🢄Upload button disabled after file select:', await uploadButton.isDisabled());
    
    // Click upload
    console.log('🢄Clicking upload button...');
    await uploadButton.click();
    
    await page.waitForTimeout(2000);
    
    console.log('🢄Upload button text after click:', await uploadButton.textContent());
    console.log('🢄Upload button disabled after click:', await uploadButton.isDisabled());
    
    // Wait and check again
    await page.waitForTimeout(5000);
    
    console.log('🢄Upload button text after wait:', await uploadButton.textContent());
    console.log('🢄Upload button disabled after wait:', await uploadButton.isDisabled());
    
    // Check for any error messages
    const errorMessage = page.locator('.error-message');
    if (await errorMessage.count() > 0) {
      console.log('🢄Error message:', await errorMessage.textContent());
    }
  });

  test('multi-file upload should work correctly', async ({ page }) => {
    // Navigate to photos page
    await page.goto('/photos');
    await page.waitForLoadState('networkidle');
    
    // Select multiple files
    const fileInput = page.locator('[data-testid="photo-file-input"]');
    await fileInput.setInputFiles([
      path.join(testAssetsDir, testPhotos[0]),
      path.join(testAssetsDir, testPhotos[1])
    ]);
    
    // Check selected files display
    const selectedFiles = page.locator('.selected-files');
    await expect(selectedFiles).toBeVisible();
    await expect(selectedFiles).toContainText('Selected files: 2');
    
    // Check upload button text
    const uploadButton = page.locator('[data-testid="upload-submit-button"]');
    await expect(uploadButton).toContainText('Upload 2 Photos');
    await expect(uploadButton).not.toBeDisabled();
    
    console.log('🢄✓ Multi-file selection UI working');
    
    // Start upload
    await uploadButton.click();
    
    // Wait for upload to complete
    await page.waitForFunction(() => {
      const input = document.querySelector('[data-testid="photo-file-input"]') as HTMLInputElement;
      return input && input.value === '';
    }, { timeout: 15000 });
    
    // Check activity log for batch upload messages
    const activityLog = page.locator('.activity-log');
    await expect(activityLog).toBeVisible();
    
    const logText = await activityLog.textContent();
    
    // Should contain batch upload messages
    expect(logText).toContain('Starting batch upload: 2 files');
    expect(logText).toContain('Batch complete:');
    
    console.log('🢄✓ Batch upload completed successfully');
    
    // Verify photos appeared in the grid
    await page.waitForTimeout(2000); // Wait for photos to load
    const photoCards = page.locator('[data-testid="photo-card"]');
    const photoCount = await photoCards.count();
    
    expect(photoCount).toBeGreaterThanOrEqual(2);
    console.log(`✓ Found ${photoCount} photos in grid`);
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

    console.log('🢄All test photos verified successfully!');
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
        
        // Set up dialog handler before clicking
        page.once('dialog', dialog => {
          console.log(`Dialog message: ${dialog.message()}`);
          expect(dialog.message()).toContain('Are you sure you want to delete this photo?');
          dialog.accept();
        });
        
        // Click delete button for this specific photo
        const deleteButton = photoCard.locator('[data-testid="delete-photo-button"]');
        await deleteButton.click();
        
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
      console.log('🢄Logout failed in afterEach:', error);
    }
  });
});