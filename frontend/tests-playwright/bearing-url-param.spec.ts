import { test, expect } from './fixtures';
import { recreateTestUsers, loginAsTestUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { ensureSourceEnabled } from './helpers/sourceHelpers';

type Page = import('@playwright/test').Page;

function getUrlParams(url: string): URLSearchParams {
  return new URL(url).searchParams;
}

/**
 * Regression coverage for URL `bearing` param ownership.
 *
 * The `bearing` URL param is owned by `bearingState` (onBearingStateChange)
 * and must not be overwritten by `photoInFront` changes. Previously,
 * Main.svelte's `flushPhotoToUrl` wrote `bearing: photo.bearing.toString()`
 * on every photoInFront change — so map panning (which re-derives
 * navigablePhotos → may flip photoInFront) silently overwrote the user's
 * actual look-direction in the URL with the selected photo's EXIF bearing.
 *
 * Test photos (from frontend/test-assets/) have EXIF bearings ~24° and ~334°.
 * We pass bearing=137 to guarantee the "closest photo by bearing" does not
 * happen to match — so any overwrite is visible as a distinct value change.
 */
test.describe('Bearing URL param ownership', () => {
  const INITIAL_BEARING = '137';

  test.beforeEach(async ({ testUsers }) => {
    await recreateTestUsers();
  });

  test('URL bearing param is preserved after photoInFront auto-selects on load', async ({ page, testUsers }) => {
    // Upload a photo whose EXIF bearing (~24°) differs from INITIAL_BEARING.
    await loginAsTestUser(page, testUsers.passwords.test);
    await uploadPhoto(page, testPhotos[0]);

    await page.goto(`/?lat=50.1153&lon=14.4938&zoom=18&bearing=${INITIAL_BEARING}`);
    await page.waitForLoadState('networkidle');
    await ensureSourceEnabled(page, 'hillview', true);

    // Wait for photoInFront to become populated (main-photo visible) and for
    // the `update_url = true` timeout + debounced URL flush to run.
    const mainPhoto = page.locator('[data-testid="main-photo"]');
    await mainPhoto.waitFor({ state: 'visible', timeout: 30000 });
    await page.waitForTimeout(1000);

    // Bearing URL param must still match what we passed in — NOT the photo's
    // EXIF bearing. If a subscriber wrote photo.bearing here, this fails.
    const params = getUrlParams(page.url());
    expect(params.get('bearing')).toBe(INITIAL_BEARING);
  });

  test('map panning does not change the bearing URL param', async ({ page, testUsers }) => {
    // Upload two photos so panning can realistically shift which photo is
    // nearest-by-bearing (triggering photoInFront to fire a change event).
    await loginAsTestUser(page, testUsers.passwords.test);
    await uploadPhoto(page, testPhotos[0]);
    await uploadPhoto(page, testPhotos[2]); // different GPS + bearing

    await page.goto(`/?lat=50.1153&lon=14.4938&zoom=18&bearing=${INITIAL_BEARING}`);
    await page.waitForLoadState('networkidle');
    await ensureSourceEnabled(page, 'hillview', true);

    // With multiple photos in range the gallery renders left/front/right
    // images all tagged `main-photo` — any being visible is enough to confirm
    // photoInFront resolved.
    const mainPhoto = page.locator('[data-testid="main-photo"]').first();
    await mainPhoto.waitFor({ state: 'visible', timeout: 30000 });
    await page.waitForTimeout(1000);

    const paramsBefore = getUrlParams(page.url());
    expect(paramsBefore.get('bearing')).toBe(INITIAL_BEARING);
    const latBefore = paramsBefore.get('lat');

    // Pan the map — changes spatialState, re-derives navigablePhotos/photoInFront.
    const mapContainer = page.locator('.leaflet-container');
    const mapBounds = await mapContainer.boundingBox();
    expect(mapBounds).not.toBeNull();
    const centerX = mapBounds!.x + mapBounds!.width / 2;
    const centerY = mapBounds!.y + mapBounds!.height / 2;

    await page.mouse.move(centerX, centerY);
    await page.mouse.down();
    await page.mouse.move(centerX + 100, centerY + 60, { steps: 10 });
    await page.mouse.up();

    // Wait for debounced URL flush (100ms) plus margin for any photoInFront
    // updates the pan triggers.
    await page.waitForTimeout(1500);

    const paramsAfter = getUrlParams(page.url());
    // lat must have moved (proves onSpatialStateChange is still wired up).
    expect(paramsAfter.get('lat')).not.toBe(latBefore);
    // Bearing must be untouched — only bearingState changes are allowed to
    // rewrite this param.
    expect(paramsAfter.get('bearing')).toBe(INITIAL_BEARING);
  });
});
