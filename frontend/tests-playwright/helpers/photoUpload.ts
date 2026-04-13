/**
 * Photo upload utilities for Playwright tests
 */

import path from 'path';
import fs from 'fs';
import os from 'os';
import { fileURLToPath } from 'url';
import { Page } from '@playwright/test';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const testAssetsDir = path.join(__dirname, '..', '..', 'test-assets');

/**
 * Playwright 1.59+ silently fails setInputFiles when the file path contains
 * non-ASCII characters (emojis, etc.). Work around by copying the file to a
 * temp path whose name encodes non-ASCII chars as _uXXXX_ escape sequences.
 *
 * The resulting filename is deterministic and reversible — when this Playwright
 * bug is fixed, just remove the workaround and setInputFiles directly.
 */
function hasNonAscii(s: string): boolean {
  return /[^\x00-\x7F]/.test(s);
}

/** Replace each non-ASCII char with _uXXXX_ (or _uXXXXX_ for astral chars). */
function escapeNonAscii(name: string): string {
  return name.replace(/[^\x00-\x7F]/gu, ch => {
    const code = ch.codePointAt(0)!;
    return `_u${code.toString(16).toUpperCase()}_`;
  });
}

let tempDir: string | null = null;
function getTempDir(): string {
  if (!tempDir) {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'pw-upload-'));
  }
  return tempDir;
}

function toAsciiTempPath(originalPath: string): string {
  const dir = path.dirname(originalPath);
  const basename = path.basename(originalPath);
  const safeName = escapeNonAscii(basename);
  const dest = path.join(getTempDir(), safeName);
  fs.copyFileSync(originalPath, dest);
  return dest;
}

/**
 * Wait for a specific photo to finish async worker processing by polling the
 * /photos page UI. Repeatedly clicks the refresh button until the photo item
 * no longer shows a "processing" badge (i.e. processing_status === 'completed').
 *
 * Expects the page to already be on /photos with the user logged in.
 */
export async function waitForPhotoProcessing(
  page: Page,
  photoId: string,
  timeoutMs: number = 30000,
): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    // Click refresh to reload the photo list
    const refreshBtn = page.locator('[data-testid="refresh-photos-button"]');
    if (await refreshBtn.isVisible()) {
      await refreshBtn.click();
      await page.waitForTimeout(1000);
    }

    // Look for the photo by its ID (action buttons carry data-photo-id)
    const photoItem = page.locator(`[data-testid="photo-item"]:has([data-photo-id="${photoId}"])`);
    if (await photoItem.count() > 0) {
      // Check if the processing badge is gone (status === 'completed')
      const badge = photoItem.locator('.processing-badge');
      if (await badge.count() === 0) return;

      // Check for error status
      const badgeText = await badge.textContent();
      if (badgeText?.trim() === 'error') {
        throw new Error(`Photo ${photoId} processing failed`);
      }
    }

    await page.waitForTimeout(500);
  }
  throw new Error(`Timed out waiting for photo ${photoId} to finish processing after ${timeoutMs}ms`);
}

export const testPhotos = [
  '2025-07-10-19-10-37_🔶∏🗿↻🌞🌲.jpg',
  '2025-07-10-19-10-39_👁️💫🔷⤵️🌪️☀️.jpg',
  '2025-07-10-19-10-41_⤴️🦢𝄞🔹🪐♪.jpg',
  '2025-07-10-19-10-45_Φ✨⤴️↗️⟸🌪️.jpg'
];

/**
 * Set files on an input element, working around Playwright 1.59+ Unicode path bug.
 */
export async function safeSetInputFiles(fileInput: ReturnType<Page['locator']>, filePath: string | string[]): Promise<void> {
  const paths = Array.isArray(filePath) ? filePath : [filePath];
  const safePaths = paths.map(p => hasNonAscii(p) ? toAsciiTempPath(p) : p);
  await fileInput.setInputFiles(safePaths.length === 1 ? safePaths[0] : safePaths);
}

/**
 * Upload a single photo file. Returns the photo ID assigned by the server.
 */
export async function uploadPhoto(page: Page, photoFilename: string): Promise<string> {
  const photoPath = path.join(testAssetsDir, photoFilename);

  // Go to photos page
  await page.goto('/photos');
  await page.waitForLoadState('networkidle');

  // Check the license checkbox first (file input is disabled until license is set)
  const licenseCheckbox = page.locator('[data-testid="license-checkbox"]');
  await licenseCheckbox.waitFor({ state: 'visible', timeout: 10000 });
  const isChecked = await licenseCheckbox.isChecked();
  if (!isChecked) {
    await licenseCheckbox.check();
  }

  // Wait for the file input to be enabled (user auth + license must be set)
  const fileInput = page.locator('[data-testid="photo-file-input"]');
  await page.waitForFunction(() => {
    const input = document.querySelector('[data-testid="photo-file-input"]') as HTMLInputElement;
    return input && !input.disabled;
  }, { timeout: 10000 });

  // Select file (uses ASCII temp copy if filename has non-ASCII chars)
  await safeSetInputFiles(fileInput, photoPath);

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

  // Extract photo ID from the success log entry
  const photoId = await page.evaluate(() => {
    const entry = document.querySelector('[data-testid="log-entry"][data-operation="upload"][data-outcome="success"]');
    return entry?.getAttribute('data-photo-id') || '';
  });

  // Wait for file input to be cleared
  await page.waitForFunction(() => {
    const input = document.querySelector('[data-testid="photo-file-input"]') as HTMLInputElement;
    return input && input.value === '';
  }, { timeout: 5000 });

  // Wait for async worker processing to complete (EXIF extraction, GPS indexing)
  if (photoId) {
    await waitForPhotoProcessing(page, photoId);
  }

  return photoId;
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
