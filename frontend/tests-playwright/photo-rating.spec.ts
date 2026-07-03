import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';

test.describe('Photo Rating', () => {
	test.describe.configure({ mode: 'serial' });

	let photoUid = '';

	test('setup: upload a test photo', async ({ page, testUsers }) => {
		test.setTimeout(120_000);
		await loginAsTestUser(page, testUsers.passwords.test);
		const photoId = await uploadPhoto(page, testPhotos[0]);
		expect(photoId).toBeTruthy();

		// UID format is {source}-{id}
		photoUid = `hillview-${photoId}`;
		console.log(`Uploaded photo: id=${photoId}, uid=${photoUid}`);
	});

	test('should rate a photo thumbs up and see count update', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		await page.goto(`/photo/${photoUid}`);
		await expect(page.getByTestId('photo-detail')).toBeVisible({ timeout: 11*10000 });

		const thumbsUp = page.getByTestId('thumbs-up-button');
		await expect(thumbsUp).toBeVisible();

		// Initial count should be 0
		const initialCount = await thumbsUp.locator('.rating-count').textContent();
		expect(initialCount?.trim()).toBe('0');

		// Click thumbs up
		await thumbsUp.click();

		// Button should become active and count should be 1
		await expect(thumbsUp).toHaveClass(/active/, { timeout: 11*5000 });
		await expect(thumbsUp.locator('.rating-count')).toHaveText('1');
	});

	test('should toggle rating off when clicking same button again', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		await page.goto(`/photo/${photoUid}`);
		await expect(page.getByTestId('photo-detail')).toBeVisible({ timeout: 11*10000 });

		const thumbsUp = page.getByTestId('thumbs-up-button');

		// Should still be active from previous test (rating persisted)
		await expect(thumbsUp).toHaveClass(/active/, { timeout: 11*5000 });
		await expect(thumbsUp.locator('.rating-count')).toHaveText('1');

		// Click again to remove rating
		await thumbsUp.click();

		// Should no longer be active, count back to 0
		await expect(thumbsUp).not.toHaveClass(/active/, { timeout: 11*5000 });
		await expect(thumbsUp.locator('.rating-count')).toHaveText('0');
	});

	test('should switch from thumbs up to thumbs down', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		await page.goto(`/photo/${photoUid}`);
		await expect(page.getByTestId('photo-detail')).toBeVisible({ timeout: 11*10000 });

		const thumbsUp = page.getByTestId('thumbs-up-button');
		const thumbsDown = page.getByTestId('thumbs-down-button');

		// Rate thumbs up first
		await thumbsUp.click();
		await expect(thumbsUp).toHaveClass(/active/, { timeout: 11*5000 });
		await expect(thumbsUp.locator('.rating-count')).toHaveText('1');

		// Now click thumbs down — should switch
		await thumbsDown.click();
		await expect(thumbsDown).toHaveClass(/active/, { timeout: 11*5000 });
		await expect(thumbsDown.locator('.rating-count')).toHaveText('1');

		// Thumbs up should no longer be active, count back to 0
		await expect(thumbsUp).not.toHaveClass(/active/);
		await expect(thumbsUp.locator('.rating-count')).toHaveText('0');
	});

	test('should rate with * / & keyboard shortcuts', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		await page.goto(`/photo/${photoUid}`);
		await expect(page.getByTestId('photo-detail')).toBeVisible({ timeout: 11*10000 });

		const thumbsUp = page.getByTestId('thumbs-up-button');
		const thumbsDown = page.getByTestId('thumbs-down-button');

		// Start from a clean slate regardless of state left by earlier tests.
		for (const btn of [thumbsUp, thumbsDown]) {
			if (/active/.test((await btn.getAttribute('class')) ?? '')) {
				await btn.click();
				await expect(btn).not.toHaveClass(/active/, { timeout: 11*5000 });
			}
		}

		// '*' likes.
		await page.keyboard.press('*');
		await expect(thumbsUp).toHaveClass(/active/, { timeout: 11*5000 });
		await expect(thumbsUp.locator('.rating-count')).toHaveText('1');

		// '&' switches to dislike.
		await page.keyboard.press('&');
		await expect(thumbsDown).toHaveClass(/active/, { timeout: 11*5000 });
		await expect(thumbsDown.locator('.rating-count')).toHaveText('1');
		await expect(thumbsUp).not.toHaveClass(/active/);
		await expect(thumbsUp.locator('.rating-count')).toHaveText('0');

		// '*' switches back to like.
		await page.keyboard.press('*');
		await expect(thumbsUp).toHaveClass(/active/, { timeout: 11*5000 });
		await expect(thumbsDown).not.toHaveClass(/active/);

		// Pressing the same like key again toggles the rating off.
		await page.keyboard.press('*');
		await expect(thumbsUp).not.toHaveClass(/active/, { timeout: 11*5000 });
		await expect(thumbsUp.locator('.rating-count')).toHaveText('0');
	});
});
