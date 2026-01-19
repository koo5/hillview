/**
 * Photo upload utilities for Playwright tests
 */

import path from 'path';
import { fileURLToPath } from 'url';
import { Page } from '@playwright/test';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const testAssetsDir = path.join(__dirname, '..', '..', 'test-assets');

export const testPhotos = [
  '2025-07-10-19-10-37_🔶∏🗿↻🌞🌲.jpg',
  '2025-07-10-19-10-39_👁️💫🔷⤵️🌪️☀️.jpg',
  '2025-07-10-19-10-41_⤴️🦢𝄞🔹🪐♪.jpg',
  '2025-07-10-19-10-45_Φ✨⤴️↗️⟸🌪️.jpg'
];

/**
 * Upload a single photo file
 */
export async function uploadPhoto(page: Page, photoFilename: string): Promise<void> {
  const photoPath = path.join(testAssetsDir, photoFilename);

  // Go to photos page
  await page.goto('/photos');
  await page.waitForLoadState('networkidle');

  // Select file
  const fileInput = page.locator('[data-testid="photo-file-input"]');
  await fileInput.setInputFiles(photoPath);

  // Check the license checkbox if not already checked
  const licenseCheckbox = page.locator('[data-testid="license-checkbox"]');
  await licenseCheckbox.waitFor({ state: 'visible', timeout: 10000 });
  const isChecked = await licenseCheckbox.isChecked();
  if (!isChecked) {
    await licenseCheckbox.check();
  }

  // Wait for upload button to be enabled
  const uploadButton = page.locator('[data-testid="upload-submit-button"]');
  await page.waitForFunction(() => {
    const button = document.querySelector('[data-testid="upload-submit-button"]') as HTMLButtonElement;
    return button && !button.disabled;
  }, { timeout: 5000 });

  // Click upload
  await uploadButton.click();

  // Wait for upload to complete
  await page.waitForFunction(() => {
    const uploadSuccessEntry = document.querySelector('[data-testid="log-entry"][data-operation="upload"][data-outcome="success"]');
    const batchCompleteEntry = document.querySelector('[data-testid="log-entry"][data-operation="batch_complete"]');
    return uploadSuccessEntry || batchCompleteEntry;
  }, { timeout: 30000 });

  // Wait for file input to be cleared
  await page.waitForFunction(() => {
    const input = document.querySelector('[data-testid="photo-file-input"]') as HTMLInputElement;
    return input && input.value === '';
  }, { timeout: 5000 });
}

/**
 * Upload multiple photos sequentially
 */
export async function uploadPhotos(page: Page, photoFilenames: string[]): Promise<void> {
  for (const filename of photoFilenames) {
    await uploadPhoto(page, filename);
    // Small delay between uploads
    await page.waitForTimeout(500);
  }
}

/**
 * Upload some test photos with location data for testing clickable functionality
 */
export async function uploadTestPhotosWithLocation(page: Page, count: number = 2): Promise<void> {
  const photosToUpload = testPhotos.slice(0, count);
  await uploadPhotos(page, photosToUpload);
}

/**
 * Get test photo path for direct use
 */
export function getTestPhotoPath(photoFilename: string): string {
  return path.join(testAssetsDir, photoFilename);
}