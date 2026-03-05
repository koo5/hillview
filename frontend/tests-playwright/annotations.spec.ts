import { test, expect } from '@playwright/test';
import { setupConsoleLogging } from './helpers/consoleLogging';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { ensureSourceEnabled } from './helpers/sourceHelpers';

const BACKEND_URL = 'http://localhost:8055';

/**
 * Helper: draw a rectangle on the OSD canvas and fill the label via the edit panel.
 * Returns the canvas bounding box for subsequent interactions.
 */
async function drawAnnotation(page: import('@playwright/test').Page, label: string) {
  const canvas = page.locator('.openseadragon-canvas');
  await canvas.waitFor({ state: 'visible' });
  const box = await canvas.boundingBox();
  expect(box).toBeTruthy();

  const startX = box!.x + box!.width * 0.3;
  const startY = box!.y + box!.height * 0.3;
  const endX = box!.x + box!.width * 0.6;
  const endY = box!.y + box!.height * 0.6;

  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(endX, endY, { steps: 10 });
  await page.mouse.up();

  // The edit panel opens automatically after drawing
  const editPanel = page.locator('[data-testid="osd-edit-body-panel"]');
  await editPanel.waitFor({ state: 'visible', timeout: 10000 });

  // Fill label and save
  const input = page.locator('[data-testid="osd-edit-body-input"]');
  await input.fill(label);
  await page.click('[data-testid="osd-edit-body-save"]');
  await expect(editPanel).not.toBeVisible({ timeout: 5000 });

  // Wait for server persist
  await page.waitForTimeout(1000);

  return box!;
}

/**
 * Annotation tests — serial because they share a single uploaded photo
 * and build on each other (create → edit → delete).
 */
test.describe('Annotation Tests', () => {
  test.describe.configure({ mode: 'serial' });

  let testPassword: string;
  /** The photo_id extracted from the uploaded photo's data attribute */
  let photoId: string;

  test.beforeEach(async ({ page }) => {
    setupConsoleLogging(page);

    // Recreate test users (also cleans photos)
    const res = await fetch(`${BACKEND_URL}/api/debug/recreate-test-users`, { method: 'POST' });
    const result = await res.json();
    testPassword = result.details?.user_passwords?.test;
    if (!testPassword) throw new Error('Test user password not returned');

    // Login
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    await page.fill('input[type="text"]', 'test');
    await page.fill('input[type="password"]', testPassword);
    await page.click('button[type="submit"]');
    await page.waitForURL('/', { timeout: 15000 });
    await page.waitForLoadState('networkidle');

    // Upload a geotagged test photo (coords ~50.1153, 14.4938)
    await uploadPhoto(page, testPhotos[0]);

    // Navigate to the map centred on the test photo's GPS coords
    await page.goto('/?lat=50.1153&lon=14.4938&zoom=18');
    await page.waitForLoadState('networkidle');

    // Enable Hillview source
    await ensureSourceEnabled(page, 'Hillview', true);

    // Wait for the gallery photo to appear, then click to open zoom view
    const mainPhoto = page.locator('[data-testid="main-photo"]');
    await mainPhoto.waitFor({ state: 'visible', timeout: 30000 });

    // Extract the photo_id from the data-photo attribute
    photoId = await mainPhoto.evaluate((el) => {
      const data = JSON.parse(el.getAttribute('data-photo') || '{}');
      return data.id;
    });
    expect(photoId).toBeTruthy();

    // Click to open the OSD zoom view
    await mainPhoto.click();
    await page.locator('[data-testid="osd-viewer-overlay"]').waitFor({ state: 'visible', timeout: 15000 });
  });

  test('should create an annotation on a photo', async ({ page }) => {
    // Enter draw mode
    await page.click('[data-testid="osd-annotate-draw"]');

    // Draw annotation and label it via edit panel
    await drawAnnotation(page, 'test-label');

    // Verify via API
    const res = await fetch(`${BACKEND_URL}/api/annotations/photos/${photoId}`);
    const annotations = await res.json();
    expect(annotations).toHaveLength(1);
    expect(annotations[0].body).toBe('test-label');
  });

  test('should edit an annotation label', async ({ page }) => {
    // Create an annotation first
    await page.click('[data-testid="osd-annotate-draw"]');
    const box = await drawAnnotation(page, 'original-label');

    // Switch to edit mode
    await page.click('[data-testid="osd-annotate-edit"]');

    // Click on the annotation area (center of where we drew)
    const centerX = box.x + box.width * 0.45;
    const centerY = box.y + box.height * 0.45;
    await page.mouse.click(centerX, centerY);

    // Wait for edit panel
    const editPanel = page.locator('[data-testid="osd-edit-body-panel"]');
    await editPanel.waitFor({ state: 'visible', timeout: 10000 });

    // Clear and fill with new label
    const input = page.locator('[data-testid="osd-edit-body-input"]');
    await input.clear();
    await input.fill('updated-label');

    // Click Save
    await page.click('[data-testid="osd-edit-body-save"]');

    // Verify panel closes
    await expect(editPanel).not.toBeVisible({ timeout: 5000 });

    // Verify via API
    await page.waitForTimeout(1000);
    const res = await fetch(`${BACKEND_URL}/api/annotations/photos/${photoId}`);
    const annotations = await res.json();
    expect(annotations).toHaveLength(1);
    expect(annotations[0].body).toBe('updated-label');
  });

  test('should delete an annotation via edit panel', async ({ page }) => {
    // Create an annotation first
    await page.click('[data-testid="osd-annotate-draw"]');
    const box = await drawAnnotation(page, 'to-delete');

    // Verify annotation exists
    let res = await fetch(`${BACKEND_URL}/api/annotations/photos/${photoId}`);
    let annotations = await res.json();
    expect(annotations).toHaveLength(1);

    // Switch to edit mode
    await page.click('[data-testid="osd-annotate-edit"]');

    // Click on the annotation
    const centerX = box.x + box.width * 0.45;
    const centerY = box.y + box.height * 0.45;
    await page.mouse.click(centerX, centerY);

    // Wait for edit panel
    const editPanel = page.locator('[data-testid="osd-edit-body-panel"]');
    await editPanel.waitFor({ state: 'visible', timeout: 10000 });

    // Click Delete
    await page.click('[data-testid="osd-edit-body-delete"]');

    // Verify panel closes
    await expect(editPanel).not.toBeVisible({ timeout: 5000 });

    // Verify via API: 0 annotations
    await page.waitForTimeout(1000);
    res = await fetch(`${BACKEND_URL}/api/annotations/photos/${photoId}`);
    annotations = await res.json();
    expect(annotations).toHaveLength(0);
  });

  test.afterEach(async ({ page }) => {
    // Close zoom view if open
    try {
      const closeBtn = page.locator('[data-testid="osd-viewer-close"]');
      if (await closeBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
        await closeBtn.click();
        await page.waitForTimeout(500);
      }
    } catch (_) {}

    // Logout
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
    } catch (_) {}
  });
});
