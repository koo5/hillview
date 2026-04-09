import { test, expect } from './fixtures';
import { recreateTestUsers, loginAsTestUser, logoutUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { ensureSourceEnabled } from './helpers/sourceHelpers';

// ─── Helpers ───────────────────────────────────────────────────────────

type Page = import('@playwright/test').Page;

const MAP_URL = '/?lat=50.1153&lon=14.4938&zoom=18';

/** Navigate to the map with a photo visible (no login required). */
async function navigateToMap(page: Page) {
  await page.goto(MAP_URL);
  await page.waitForLoadState('networkidle');
  await ensureSourceEnabled(page, 'hillview', true);
  await page.locator('[data-testid="main-photo"]').waitFor({ state: 'visible', timeout: 30000 });
}

/** Open the OSD viewer by clicking the main photo. */
async function openViewer(page: Page) {
  const mainPhoto = page.locator('[data-testid="main-photo"]');
  await mainPhoto.waitFor({ state: 'visible', timeout: 30000 });
  await mainPhoto.click();
  await page.locator('[data-testid="osd-viewer-overlay"]').waitFor({ state: 'visible', timeout: 15000 });
  await page.locator('.openseadragon-canvas').waitFor({ state: 'visible', timeout: 15000 });
  await page.waitForTimeout(500);
}

/** Assert the sign-in modal is visible. */
async function expectModalVisible(page: Page) {
  await expect(page.locator('[data-testid="sign-in-modal"]')).toBeVisible({ timeout: 5000 });
}

/** Assert the sign-in modal is not visible. */
async function expectModalHidden(page: Page) {
  await expect(page.locator('[data-testid="sign-in-modal"]')).not.toBeVisible({ timeout: 5000 });
}

/** Click the Cancel button on the sign-in modal. */
async function dismissModal(page: Page) {
  await page.click('[data-testid="sign-in-modal-cancel"]');
  await expectModalHidden(page);
}

// ─── Tests ─────────────────────────────────────────────────────────────

test.describe('Sign-In Modal', () => {
  test.describe.configure({ mode: 'serial' });

  // ── Zoom view — unauthenticated ──

  test.describe('Zoom view - unauthenticated', () => {

    test.beforeEach(async ({ page, testUsers }) => {
      await recreateTestUsers();
      await loginAsTestUser(page, testUsers.passwords.test);
      await uploadPhoto(page, testPhotos[0]);
      await logoutUser(page);
      await navigateToMap(page);
      await openViewer(page);
    });

    test('Draw button shows sign-in modal', async ({ page }) => {
      const drawBtn = page.locator('[data-testid="osd-annotate-draw"]');
      await expect(drawBtn).toBeVisible();
      await drawBtn.click();

      await expectModalVisible(page);

      // Button should NOT be in active state
      const isActive = await drawBtn.evaluate(el => el.classList.contains('active'));
      expect(isActive).toBe(false);
    });

    test('Edit button shows sign-in modal', async ({ page }) => {
      const editBtn = page.locator('[data-testid="osd-annotate-edit"]');
      await expect(editBtn).toBeVisible();
      await editBtn.click();

      await expectModalVisible(page);

      const isActive = await editBtn.evaluate(el => el.classList.contains('active'));
      expect(isActive).toBe(false);
    });

    test('"d" key shows sign-in modal', async ({ page }) => {
      await page.keyboard.press('d');
      await expectModalVisible(page);
    });

    test('"e" key shows sign-in modal', async ({ page }) => {
      await page.keyboard.press('e');
      await expectModalVisible(page);
    });

    test('Sign In button navigates to /login', async ({ page }) => {
      await page.locator('[data-testid="osd-annotate-draw"]').click();
      await expectModalVisible(page);

      await page.click('[data-testid="sign-in-modal-login"]');
      await page.waitForURL('/login', { timeout: 15000 });
    });

    test('Cancel button closes the modal', async ({ page }) => {
      await page.locator('[data-testid="osd-annotate-draw"]').click();
      await expectModalVisible(page);

      await dismissModal(page);

      // Viewer and buttons should still be visible
      await expect(page.locator('[data-testid="osd-viewer-overlay"]')).toBeVisible();
      await expect(page.locator('[data-testid="osd-annotate-draw"]')).toBeVisible();
      await expect(page.locator('[data-testid="osd-annotate-edit"]')).toBeVisible();
    });

    test('Escape key closes the modal', async ({ page }) => {
      await page.locator('[data-testid="osd-annotate-edit"]').click();
      await expectModalVisible(page);

      await page.keyboard.press('Escape');
      await expectModalHidden(page);
    });

    test('Modal can be reopened after Cancel', async ({ page }) => {
      // First open/cancel cycle
      await page.locator('[data-testid="osd-annotate-draw"]').click();
      await expectModalVisible(page);
      await dismissModal(page);

      // Second open/cancel cycle
      await page.locator('[data-testid="osd-annotate-edit"]').click();
      await expectModalVisible(page);
      await dismissModal(page);

      // Third open via keyboard
      await page.keyboard.press('d');
      await expectModalVisible(page);
      await dismissModal(page);
    });
  });

  // ── Zoom view — authenticated ──

  test.describe('Zoom view - authenticated', () => {

    test.beforeEach(async ({ page, testUsers }) => {
      await recreateTestUsers();
      await loginAsTestUser(page, testUsers.passwords.test);
      await uploadPhoto(page, testPhotos[0]);
      await navigateToMap(page);
      await openViewer(page);
    });

    test('Draw button activates draw mode without modal', async ({ page }) => {
      const drawBtn = page.locator('[data-testid="osd-annotate-draw"]');
      await drawBtn.click();

      await expectModalHidden(page);
      const isActive = await drawBtn.evaluate(el => el.classList.contains('active'));
      expect(isActive).toBe(true);
    });

    test('Edit button activates edit mode without modal', async ({ page }) => {
      const editBtn = page.locator('[data-testid="osd-annotate-edit"]');
      await editBtn.click();

      await expectModalHidden(page);
      const isActive = await editBtn.evaluate(el => el.classList.contains('active'));
      expect(isActive).toBe(true);
    });

    test('"d" key activates draw mode without modal', async ({ page }) => {
      await page.keyboard.press('d');

      await expectModalHidden(page);
      const isActive = await page.locator('[data-testid="osd-annotate-draw"]')
        .evaluate(el => el.classList.contains('active'));
      expect(isActive).toBe(true);
    });

    test('"e" key activates edit mode without modal', async ({ page }) => {
      await page.keyboard.press('e');

      await expectModalHidden(page);
      const isActive = await page.locator('[data-testid="osd-annotate-edit"]')
        .evaluate(el => el.classList.contains('active'));
      expect(isActive).toBe(true);
    });
  });

  // ── Gallery — unauthenticated ──

  test.describe('Gallery - unauthenticated', () => {

    test.beforeEach(async ({ page, testUsers }) => {
      await recreateTestUsers();
      await loginAsTestUser(page, testUsers.passwords.test);
      await uploadPhoto(page, testPhotos[0]);
      await logoutUser(page);
      await navigateToMap(page);
    });

    test('Thumbs up shows sign-in modal', async ({ page }) => {
      await page.locator('[data-testid="thumbs-up-button"]').click();
      await expectModalVisible(page);
    });

    test('Thumbs down shows sign-in modal', async ({ page }) => {
      await page.locator('[data-testid="thumbs-down-button"]').click();
      await expectModalVisible(page);
    });
  });

  // ── Full login flow ──

  test.describe('Full login flow', () => {

    test('Draw while unauthenticated, sign in, return, Draw works', async ({ page, testUsers }) => {
      test.setTimeout(120_000);

      await recreateTestUsers();
      await loginAsTestUser(page, testUsers.passwords.test);
      await uploadPhoto(page, testPhotos[0]);
      await logoutUser(page);
      await navigateToMap(page);
      await openViewer(page);

      // Click Draw — should show sign-in modal
      await page.locator('[data-testid="osd-annotate-draw"]').click();
      await expectModalVisible(page);

      // Click Sign In — navigates to /login
      await page.click('[data-testid="sign-in-modal-login"]');
      await page.waitForURL('/login', { timeout: 15000 });

      // Log in
      await page.fill('input[type="text"]', 'test');
      await page.fill('input[type="password"]', testUsers.passwords.test);
      await page.click('button[type="submit"]');
      await page.waitForURL('/', { timeout: 15000 });

      // Navigate back to map, open viewer
      await navigateToMap(page);
      await openViewer(page);

      // Draw button should now work without modal
      const drawBtn = page.locator('[data-testid="osd-annotate-draw"]');
      await drawBtn.click();
      await expectModalHidden(page);
      const isActive = await drawBtn.evaluate(el => el.classList.contains('active'));
      expect(isActive).toBe(true);
    });
  });
});
