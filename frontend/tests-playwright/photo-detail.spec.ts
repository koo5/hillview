import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { BACKEND_URL } from './helpers/adminAuth';

test.describe('Photo Detail Page', () => {
	test.describe.configure({ mode: 'serial' });

	let photoUid = '';
	let photoId = '';

	test('setup: upload a test photo', async ({ page, testUsers }) => {
		test.setTimeout(120_000);
		await loginAsTestUser(page, testUsers.passwords.test);
		photoId = await uploadPhoto(page, testPhotos[0]);
		expect(photoId).toBeTruthy();

		// Get the photo UID
		const response = await page.request.get(`${BACKEND_URL}/api/photos`, {
			headers: { 'Accept': 'application/json' }
		});
		const photos = await response.json();
		const uploaded = photos.find((p: any) => p.id === photoId);
		expect(uploaded).toBeTruthy();
		photoUid = uploaded.uid;
		console.log(`Uploaded photo: id=${photoId}, uid=${photoUid}`);
	});

	test('should load and display photo details', async ({ page }) => {
		await page.goto(`/photo/${photoUid}`);
		await page.waitForLoadState('networkidle');

		await expect(page.getByTestId('photo-detail')).toBeVisible({ timeout: 10000 });
		await expect(page.getByTestId('photo-detail-image')).toBeVisible();

		// Owner should be shown
		await expect(page.getByTestId('photo-detail-owner')).toHaveText('@test');

		// View on Map link should be present (test photos have GPS)
		await expect(page.getByTestId('photo-detail-view-on-map')).toBeVisible();
	});

	test('should show 404 for invalid uid', async ({ page }) => {
		await page.goto('/photo/nonexistent-uid-12345');
		await page.waitForLoadState('networkidle');

		await expect(page.getByTestId('photo-detail-error')).toBeVisible({ timeout: 10000 });
	});

	test('should navigate to map when View on Map is clicked', async ({ page }) => {
		await page.goto(`/photo/${photoUid}`);
		await page.waitForLoadState('networkidle');
		await expect(page.getByTestId('photo-detail')).toBeVisible({ timeout: 10000 });

		await page.getByTestId('photo-detail-view-on-map').click();

		// Should navigate to the map page with coordinates
		await page.waitForURL(/\/\?.*lat=.*lon=/, { timeout: 10000 });
	});

	test('should show action buttons', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		await page.goto(`/photo/${photoUid}`);
		await page.waitForLoadState('networkidle');
		await expect(page.getByTestId('photo-detail')).toBeVisible({ timeout: 10000 });

		// Rating buttons
		await expect(page.getByTestId('thumbs-up-button')).toBeVisible();
		await expect(page.getByTestId('thumbs-down-button')).toBeVisible();

		// Share, flag, hide buttons
		await expect(page.getByTestId('menu-share')).toBeVisible();
		await expect(page.getByTestId('menu-flag')).toBeVisible();
		await expect(page.getByTestId('menu-hide-photo')).toBeVisible();

		// Owner-only: delete button (test user owns this photo)
		await expect(page.getByTestId('photo-detail-owner-actions')).toBeVisible();
		await expect(page.getByTestId('delete-photo-button')).toBeVisible();
	});

	test('should flag and unflag a photo', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		await page.goto(`/photo/${photoUid}`);
		await page.waitForLoadState('networkidle');
		await expect(page.getByTestId('photo-detail')).toBeVisible({ timeout: 10000 });

		const flagButton = page.getByTestId('menu-flag');

		// Flag the photo
		await flagButton.click();
		await expect(flagButton).toHaveClass(/flagged/, { timeout: 5000 });
		await expect(flagButton).toContainText('Remove Flag');

		// Unflag the photo
		await flagButton.click();
		await expect(flagButton).not.toHaveClass(/flagged/, { timeout: 5000 });
		await expect(flagButton).toContainText('Flag');
	});

	test('should navigate to user profile when owner link is clicked', async ({ page }) => {
		await page.goto(`/photo/${photoUid}`);
		await page.waitForLoadState('networkidle');
		await expect(page.getByTestId('photo-detail')).toBeVisible({ timeout: 10000 });

		await page.getByTestId('photo-detail-owner').click();

		// Should navigate to the user profile page
		await page.waitForURL(/\/users\//, { timeout: 10000 });
	});
});
