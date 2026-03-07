import { test, expect } from './fixtures';
import path from 'path';
import { fileURLToPath } from 'url';


const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const testAssetsDir = path.join(__dirname, '..', 'test-assets');
const testPhoto = '2025-07-10-19-10-37_🔶∏🗿↻🌞🌲.jpg';

test.describe('Filters Modal', () => {
	test.describe.configure({ mode: 'serial' });

	let testPassword: string;

	test.beforeAll(async () => {
		// Clean up and get test credentials
		const response = await fetch('http://localhost:8055/api/debug/recreate-test-users', {
			method: 'POST'
		});
		const result = await response.json();
		testPassword = result.details?.user_passwords?.test;
		if (!testPassword) {
			throw new Error('Test user password not returned from recreate-test-users');
		}
	});

	test.beforeEach(async ({ page }) => {


		// Login
		await page.goto('/login');
		await page.waitForLoadState('networkidle');
		await page.fill('input[type="text"]', 'test');
		await page.fill('input[type="password"]', testPassword);
		await page.click('button[type="submit"]');
		await page.waitForURL('/', { timeout: 15000 });
		await page.waitForLoadState('networkidle');

		// Clear localStorage filters to start fresh
		await page.evaluate(() => localStorage.removeItem('hillview_filters'));
	});

	test('should open and close the filters modal', async ({ page }) => {
		await page.goto('/');
		await page.waitForSelector('.leaflet-container', { timeout: 10000 });

		const filtersButton = page.locator('[data-testid="filters-button"]');
		await expect(filtersButton).toBeVisible();
		await filtersButton.click();

		const modal = page.locator('[data-testid="filters-modal"]');
		await expect(modal).toBeVisible();

		// Close via close button
		await modal.locator('.close-button').click();
		await expect(modal).not.toBeVisible();
	});

	test('clear button and show-unanalyzed toggle should be disabled when no filters active', async ({ page }) => {
		await page.goto('/');
		await page.waitForSelector('.leaflet-container', { timeout: 10000 });

		await page.locator('[data-testid="filters-button"]').click();
		const modal = page.locator('[data-testid="filters-modal"]');
		await expect(modal).toBeVisible();

		const clearButton = modal.locator('[data-testid="clear-filters"]');
		await expect(clearButton).toBeDisabled();

		const showUnanalyzed = modal.locator('[data-testid="show-unanalyzed"] input[type="checkbox"]');
		await expect(showUnanalyzed).toBeDisabled();
	});

	test('selecting a filter should enable clear button and show-unanalyzed toggle', async ({ page }) => {
		await page.goto('/');
		await page.waitForSelector('.leaflet-container', { timeout: 10000 });

		await page.locator('[data-testid="filters-button"]').click();
		const modal = page.locator('[data-testid="filters-modal"]');

		// Click a filter chip
		const dayFilter = modal.locator('[data-testid="filter"][data-filter-name="time_of_day"][data-filter-value="day"]');
		await dayFilter.click();

		// Chip should be selected
		await expect(dayFilter).toHaveClass(/selected/);

		// Clear and show-unanalyzed should now be enabled
		const clearButton = modal.locator('[data-testid="clear-filters"]');
		await expect(clearButton).toBeEnabled();

		const showUnanalyzed = modal.locator('[data-testid="show-unanalyzed"] input[type="checkbox"]');
		await expect(showUnanalyzed).toBeEnabled();
	});

	test('clicking a selected filter should deselect it (toggle behavior)', async ({ page }) => {
		await page.goto('/');
		await page.waitForSelector('.leaflet-container', { timeout: 10000 });

		await page.locator('[data-testid="filters-button"]').click();
		const modal = page.locator('[data-testid="filters-modal"]');

		const dayFilter = modal.locator('[data-testid="filter"][data-filter-name="time_of_day"][data-filter-value="day"]');

		// Select
		await dayFilter.click();
		await expect(dayFilter).toHaveClass(/selected/);

		// Deselect
		await dayFilter.click();
		await expect(dayFilter).not.toHaveClass(/selected/);

		// Clear button should be disabled again
		await expect(modal.locator('[data-testid="clear-filters"]')).toBeDisabled();
	});

	test('clear all filters should deselect everything', async ({ page }) => {
		await page.goto('/');
		await page.waitForSelector('.leaflet-container', { timeout: 10000 });

		await page.locator('[data-testid="filters-button"]').click();
		const modal = page.locator('[data-testid="filters-modal"]');

		// Select multiple filters
		await modal.locator('[data-testid="filter"][data-filter-name="time_of_day"][data-filter-value="day"]').click();
		await modal.locator('[data-testid="filter"][data-filter-name="location_type"][data-filter-value="outdoors"]').click();

		// Both should be selected
		await expect(modal.locator('[data-testid="filter"][data-filter-name="time_of_day"][data-filter-value="day"]')).toHaveClass(/selected/);
		await expect(modal.locator('[data-testid="filter"][data-filter-name="location_type"][data-filter-value="outdoors"]')).toHaveClass(/selected/);

		// Click clear
		await modal.locator('[data-testid="clear-filters"]').click();

		// No filters should be selected
		const selectedFilters = modal.locator('[data-testid="filter"].selected');
		await expect(selectedFilters).toHaveCount(0);

		// Clear and show-unanalyzed should be disabled again
		await expect(modal.locator('[data-testid="clear-filters"]')).toBeDisabled();
		await expect(modal.locator('[data-testid="show-unanalyzed"] input[type="checkbox"]')).toBeDisabled();
	});

	test('filters button should show active filter count', async ({ page }) => {
		await page.goto('/');
		await page.waitForSelector('.leaflet-container', { timeout: 10000 });

		const filtersButton = page.locator('[data-testid="filters-button"]');

		// Open modal and select two filters
		await filtersButton.click();
		const modal = page.locator('[data-testid="filters-modal"]');

		await modal.locator('[data-testid="filter"][data-filter-name="time_of_day"][data-filter-value="day"]').click();
		await modal.locator('[data-testid="filter"][data-filter-name="location_type"][data-filter-value="outdoors"]').click();

		// Close modal
		await modal.locator('.close-button').click();

		// Filters button should show count
		await expect(filtersButton).toContainText('(2)');
	});

	test('show-unanalyzed toggle should be checked by default', async ({ page }) => {
		await page.goto('/');
		await page.waitForSelector('.leaflet-container', { timeout: 10000 });

		await page.locator('[data-testid="filters-button"]').click();
		const modal = page.locator('[data-testid="filters-modal"]');

		// Activate a filter first so the toggle is enabled
		await modal.locator('[data-testid="filter"][data-filter-name="time_of_day"][data-filter-value="day"]').click();

		const showUnanalyzed = modal.locator('[data-testid="show-unanalyzed"] input[type="checkbox"]');
		await expect(showUnanalyzed).toBeChecked();
	});
});

test.describe('Filters with uploaded photos', () => {
	test.describe.configure({ mode: 'serial' });

	let testPassword: string;

	test.beforeAll(async () => {
		const response = await fetch('http://localhost:8055/api/debug/recreate-test-users', {
			method: 'POST'
		});
		const result = await response.json();
		testPassword = result.details?.user_passwords?.test;
		if (!testPassword) {
			throw new Error('Test user password not returned from recreate-test-users');
		}
	});

	async function loginAndUploadPhoto(page: import('@playwright/test').Page) {
		// Login
		await page.goto('/login');
		await page.waitForLoadState('networkidle');
		await page.fill('input[type="text"]', 'test');
		await page.fill('input[type="password"]', testPassword);
		await page.click('button[type="submit"]');
		await page.waitForURL('/', { timeout: 15000 });
		await page.waitForLoadState('networkidle');

		// Clear filters
		await page.evaluate(() => localStorage.removeItem('hillview_filters'));

		// Upload a test photo
		await page.goto('/photos');
		await page.waitForLoadState('networkidle');

		const photoPath = path.join(testAssetsDir, testPhoto);
		await page.locator('[data-testid="photo-file-input"]').setInputFiles(photoPath);

		const licenseCheckbox = page.locator('[data-testid="license-checkbox"]');
		if (!await licenseCheckbox.isChecked()) {
			await licenseCheckbox.check();
		}

		await expect(page.locator('[data-testid="upload-submit-button"]')).toBeEnabled({ timeout: 10000 });
		await page.locator('[data-testid="upload-submit-button"]').click();

		// Wait for upload completion
		await page.waitForFunction(() => {
			const input = document.querySelector('[data-testid="photo-file-input"]') as HTMLInputElement;
			return input && input.value === '';
		}, { timeout: 15000 });
	}

	test('applying a filter should hide unanalyzed photos on map', async ({ page }) => {

		await loginAndUploadPhoto(page);

		// Go to map
		await page.goto('/');
		await page.waitForSelector('.leaflet-container', { timeout: 10000 });
		await page.waitForTimeout(3000); // wait for photos to load on map

		// Check that photo markers are visible (unanalyzed photos show by default)
		const markersBeforeFilter = page.locator('[data-testid^="photo-marker-"]');
		const countBefore = await markersBeforeFilter.count();
		expect(countBefore).toBeGreaterThan(0);

		// Open filters and select a filter
		await page.locator('[data-testid="filters-button"]').click();
		const modal = page.locator('[data-testid="filters-modal"]');
		await expect(modal).toBeVisible();

		// Select "Day" time filter — since photo is unanalyzed and show_unanalyzed defaults to true,
		// it should still show
		await modal.locator('[data-testid="filter"][data-filter-name="time_of_day"][data-filter-value="day"]').click();

		// Close modal to see the map
		await modal.locator('.close-button').click();
		await page.waitForTimeout(3000); // wait for re-fetch

		// Photos should still be visible (show_unanalyzed is true by default)
		const markersWithFilter = page.locator('[data-testid^="photo-marker-"]');
		const countWithFilter = await markersWithFilter.count();
		expect(countWithFilter).toBeGreaterThan(0);
	});

	test('disabling show-unanalyzed should hide unanalyzed photos', async ({ page }) => {

		await loginAndUploadPhoto(page);

		// Go to map
		await page.goto('/');
		await page.waitForSelector('.leaflet-container', { timeout: 10000 });
		await page.waitForTimeout(3000);

		// Confirm markers exist
		const markersBefore = page.locator('[data-testid^="photo-marker-"]');
		const countBefore = await markersBefore.count();
		expect(countBefore).toBeGreaterThan(0);

		// Open filters, select a filter, then uncheck show-unanalyzed
		await page.locator('[data-testid="filters-button"]').click();
		const modal = page.locator('[data-testid="filters-modal"]');

		await modal.locator('[data-testid="filter"][data-filter-name="time_of_day"][data-filter-value="day"]').click();

		const showUnanalyzed = modal.locator('[data-testid="show-unanalyzed"] input[type="checkbox"]');
		await expect(showUnanalyzed).toBeChecked();
		await showUnanalyzed.uncheck();
		await expect(showUnanalyzed).not.toBeChecked();

		// Close modal
		await modal.locator('.close-button').click();
		await page.waitForTimeout(3000); // wait for re-fetch

		// All photos are unanalyzed, so none should show
		const markersAfter = page.locator('[data-testid^="photo-marker-"]');
		await expect(markersAfter).toHaveCount(0, { timeout: 10000 });
	});

	test('re-enabling show-unanalyzed should bring photos back', async ({ page }) => {

		await loginAndUploadPhoto(page);

		// Go to map
		await page.goto('/');
		await page.waitForSelector('.leaflet-container', { timeout: 10000 });
		await page.waitForTimeout(3000);

		// Open filters, select a filter, uncheck show-unanalyzed
		await page.locator('[data-testid="filters-button"]').click();
		const modal = page.locator('[data-testid="filters-modal"]');

		await modal.locator('[data-testid="filter"][data-filter-name="time_of_day"][data-filter-value="day"]').click();
		await modal.locator('[data-testid="show-unanalyzed"] input[type="checkbox"]').uncheck();

		// Close and wait
		await modal.locator('.close-button').click();
		await page.waitForTimeout(3000);

		// No markers
		await expect(page.locator('[data-testid^="photo-marker-"]')).toHaveCount(0, { timeout: 10000 });

		// Re-open and re-enable show-unanalyzed
		await page.locator('[data-testid="filters-button"]').click();
		await expect(modal).toBeVisible();
		await modal.locator('[data-testid="show-unanalyzed"] input[type="checkbox"]').check();

		// Close and wait
		await modal.locator('.close-button').click();
		await page.waitForTimeout(3000);

		// Markers should be back
		const markersAfter = page.locator('[data-testid^="photo-marker-"]');
		const count = await markersAfter.count();
		expect(count).toBeGreaterThan(0);
	});
});
