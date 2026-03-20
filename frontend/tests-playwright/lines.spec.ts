import { test, expect } from './fixtures';

test.describe('Lines Component', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('.leaflet-container', { timeout: 10000 });
  });

  test('should open and close Lines view via toolbar button', async ({ page }) => {
    const linesButton = page.locator('[data-testid="lines-button"]');
    await expect(linesButton).toBeVisible({ timeout: 10000 });

    // Open Lines view
    await linesButton.click({ force: true });
    await expect(page.locator('[data-testid="lines-view"]')).toBeVisible({ timeout: 5000 });

    // Close Lines view by clicking the button again
    await linesButton.click({ force: true });
    await expect(page.locator('[data-testid="lines-view"]')).not.toBeVisible({ timeout: 5000 });
  });

  test('should add a line', async ({ page }) => {
    const linesButton = page.locator('[data-testid="lines-button"]');
    await expect(linesButton).toBeVisible({ timeout: 10000 });
    await linesButton.click({ force: true });
    await expect(page.locator('[data-testid="lines-view"]')).toBeVisible({ timeout: 5000 });

    // Initially no lines table
    await expect(page.locator('[data-testid="lines-table"]')).not.toBeVisible();

    // Click Add line
    await page.click('[data-testid="lines-add-btn"]');

    // Table and first row should appear
    await expect(page.locator('[data-testid="lines-table"]')).toBeVisible({ timeout: 3000 });
    await expect(page.locator('[data-testid="lines-row-0"]')).toBeVisible();
  });

  test('should edit a line label', async ({ page }) => {
    const linesButton = page.locator('[data-testid="lines-button"]');
    await expect(linesButton).toBeVisible({ timeout: 10000 });
    await linesButton.click({ force: true });
    await expect(page.locator('[data-testid="lines-view"]')).toBeVisible({ timeout: 5000 });

    // Add a line
    await page.click('[data-testid="lines-add-btn"]');
    await expect(page.locator('[data-testid="lines-row-0"]')).toBeVisible({ timeout: 3000 });

    // Edit the label
    const labelInput = page.locator('[data-testid="line-label-0"]');
    await labelInput.fill('Test Line');
    await expect(labelInput).toHaveValue('Test Line');
  });

  test('should toggle line visibility', async ({ page }) => {
    const linesButton = page.locator('[data-testid="lines-button"]');
    await expect(linesButton).toBeVisible({ timeout: 10000 });
    await linesButton.click({ force: true });
    await expect(page.locator('[data-testid="lines-view"]')).toBeVisible({ timeout: 5000 });

    // Add a line
    await page.click('[data-testid="lines-add-btn"]');
    await expect(page.locator('[data-testid="lines-row-0"]')).toBeVisible({ timeout: 3000 });

    // Toggle visibility off
    const visCheckbox = page.locator('[data-testid="line-visible-0"]');
    await expect(visCheckbox).toBeChecked();
    await visCheckbox.click();
    await expect(visCheckbox).not.toBeChecked();

    // Toggle visibility back on
    await visCheckbox.click();
    await expect(visCheckbox).toBeChecked();
  });

  test('should delete a line', async ({ page }) => {
    const linesButton = page.locator('[data-testid="lines-button"]');
    await expect(linesButton).toBeVisible({ timeout: 10000 });
    await linesButton.click({ force: true });
    await expect(page.locator('[data-testid="lines-view"]')).toBeVisible({ timeout: 5000 });

    // Add a line
    await page.click('[data-testid="lines-add-btn"]');
    await expect(page.locator('[data-testid="lines-row-0"]')).toBeVisible({ timeout: 3000 });

    // Delete it
    await page.click('[data-testid="line-delete-0"]');
    await expect(page.locator('[data-testid="lines-row-0"]')).not.toBeVisible({ timeout: 3000 });
    await expect(page.locator('[data-testid="lines-table"]')).not.toBeVisible();
  });

  test('should add multiple lines and delete one', async ({ page }) => {
    const linesButton = page.locator('[data-testid="lines-button"]');
    await expect(linesButton).toBeVisible({ timeout: 10000 });
    await linesButton.click({ force: true });
    await expect(page.locator('[data-testid="lines-view"]')).toBeVisible({ timeout: 5000 });

    // Add two lines
    await page.click('[data-testid="lines-add-btn"]');
    await page.click('[data-testid="lines-add-btn"]');
    await expect(page.locator('[data-testid="lines-row-0"]')).toBeVisible({ timeout: 3000 });
    await expect(page.locator('[data-testid="lines-row-1"]')).toBeVisible();

    // Label them
    await page.locator('[data-testid="line-label-0"]').fill('First');
    await page.locator('[data-testid="line-label-1"]').fill('Second');

    // Delete first line
    await page.click('[data-testid="line-delete-0"]');

    // Only one row should remain, and it should have the second label
    await expect(page.locator('[data-testid="lines-row-0"]')).toBeVisible();
    await expect(page.locator('[data-testid="lines-row-1"]')).not.toBeVisible();
    // After deleting the first line, the remaining line gets re-indexed as row 0
    await expect(page.locator('[data-testid="line-label-0"]')).toHaveValue('Second');
  });

  test('should toggle global lines visibility', async ({ page }) => {
    const linesButton = page.locator('[data-testid="lines-button"]');
    await expect(linesButton).toBeVisible({ timeout: 10000 });
    await linesButton.click({ force: true });
    await expect(page.locator('[data-testid="lines-view"]')).toBeVisible({ timeout: 5000 });

    const globalToggle = page.locator('[data-testid="lines-visible-toggle"] input[type="checkbox"]');
    // Toggle "Show on map" on
    if (!(await globalToggle.isChecked())) {
      await globalToggle.click();
    }
    await expect(globalToggle).toBeChecked();

    // Toggle off
    await globalToggle.click();
    await expect(globalToggle).not.toBeChecked();
  });
});
