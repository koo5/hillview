import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { ensureSourceEnabled } from './helpers/sourceHelpers';

/**
 * Coverage for the photo info window (the 'i' key toggle).
 *
 * A single persisted store (`showPhotoInfoWindow`) drives two overlays at once:
 * one over the map pane and one in the corner of the zoom view. Either window's
 * 'x' button closes both. Camera/lens EXIF is fetched (cached) from the public
 * photo endpoint for hillview photos; base metadata comes off the local photo.
 */

const INFO_WINDOW = '[data-testid="photo-info-window"]';
const MAP_INFO_WINDOW = `.map-panel ${INFO_WINDOW}`;
// Test-asset location (testPhotos[0] sits near here — see bearing-url-param.spec).
const AT_PHOTO = '/?lat=50.1153&lon=14.4938&zoom=18';

test.describe('Photo info window (i key)', () => {
  test('i toggles the window over the map; both i and the x button close it', async ({ page }) => {
    await page.goto(AT_PHOTO);
    await page.waitForSelector('.leaflet-container', { timeout: T(15000) });

    const win = page.locator(MAP_INFO_WINDOW);
    await expect(win).not.toBeVisible();

    // Open with 'i'.
    await page.keyboard.press('i');
    await expect(win).toBeVisible({ timeout: T(5000) });

    // 'i' again closes it.
    await page.keyboard.press('i');
    await expect(win).not.toBeVisible();

    // Reopen, then close with the window's own 'x' button.
    await page.keyboard.press('i');
    await expect(win).toBeVisible({ timeout: T(5000) });
    await win.locator('[data-testid="photo-info-close"]').click();
    await expect(win).not.toBeVisible();
  });

  test('window visibility persists across a reload', async ({ page }) => {
    await page.goto(AT_PHOTO);
    await page.waitForSelector('.leaflet-container', { timeout: T(15000) });

    await page.keyboard.press('i');
    await expect(page.locator(MAP_INFO_WINDOW)).toBeVisible({ timeout: T(5000) });

    await page.reload();
    await page.waitForSelector('.leaflet-container', { timeout: T(15000) });

    // The persisted flag re-opens the window without another keypress.
    await expect(page.locator(MAP_INFO_WINDOW)).toBeVisible({ timeout: T(5000) });
  });

  test('shows EXIF for the hillview photo in front and mirrors into the zoom view', async ({ page, testUsers }) => {
    // Inject deterministic curated EXIF into the public-photo response the window
    // fetches — the test-asset JPEGs carry only a GPS direction, no camera tags.
    await page.route('**/photos/public/**', route =>
      route.fulfill({
        json: {
          exif: {
            focal_length: 24,
            focal_length_35mm: 36,
            f_number: 2.8,
            iso: 200,
            exposure_time: 0.004,
            make: 'Canon',
            model: 'Canon EOS R6',
            lens: 'RF24-70mm F2.8 L IS USM',
          },
        },
      })
    );

    await loginAsTestUser(page, testUsers.passwords.test);
    await uploadPhoto(page, testPhotos[0]);

    await page.goto(AT_PHOTO);
    await ensureSourceEnabled(page, 'hillview', true);

    // main-photo visible == photoInFront resolved to the uploaded hillview photo.
    const mainPhoto = page.locator('[data-testid="main-photo"]').first();
    await mainPhoto.waitFor({ state: 'visible', timeout: T(30000) });

    // Open the info window over the map.
    await page.keyboard.press('i');
    const mapWin = page.locator(MAP_INFO_WINDOW);
    await expect(mapWin).toBeVisible({ timeout: T(5000) });

    // Curated EXIF, rendered precisely by the formatters.
    await expect(mapWin).toContainText('24 mm (36 mm eq.)');
    await expect(mapWin).toContainText('ƒ/2.8');
    await expect(mapWin).toContainText('ISO 200');
    await expect(mapWin).toContainText('1/250 s');
    await expect(mapWin).toContainText('Canon EOS R6');
    // Base metadata comes off the local photo object (no fetch needed).
    await expect(mapWin).toContainText('Bearing');

    // The same store must also render a corner window inside the zoom view.
    await mainPhoto.click();
    const osd = page.locator('[data-testid="osd-viewer-overlay"]');
    await osd.waitFor({ state: 'visible', timeout: T(15000) });
    const zoomWin = osd.locator(INFO_WINDOW);
    await expect(zoomWin).toBeVisible({ timeout: T(5000) });
    await expect(zoomWin).toContainText('24 mm (36 mm eq.)');

    // The 'x' on the zoom-view window closes the shared store (both windows).
    await zoomWin.locator('[data-testid="photo-info-close"]').click();
    await expect(zoomWin).not.toBeVisible();
    // The zoom view itself stays open — only the info window closed.
    await expect(osd).toBeVisible();
  });
});
