/**
 * Terrain bench lifecycle — enqueue and status transitions with a mutable
 * stubbed render list (the worker is simulated by mutating rows between
 * refreshes; the full-stack compose tier exercises the real queue).
 */
import { expect, test } from '@playwright/test';
import { renderRow, stubTerrainApi } from './helpers/terrainFixtures';

test('enqueue → queued → done across refreshes', async ({ page }) => {
	const rows: ReturnType<typeof renderRow>[] = [];
	await stubTerrainApi(page, () => rows);
	await page.goto('/terrain');
	await expect(page.getByTestId('terrain-row')).toHaveCount(0);

	await page.getByTestId('terrain-lat').fill('50.0');
	await page.getByTestId('terrain-lon').fill('14.5');
	rows.push(renderRow({ status: 'queued', meta: null, has_depth: false, has_preview: false }));
	await page.getByTestId('terrain-enqueue').click();
	await expect(page.getByTestId('terrain-row')).toHaveAttribute('data-status', 'queued');

	// "worker finishes" — the next refresh sees it done
	Object.assign(rows[0], renderRow());
	await page.getByTestId('terrain-refresh').click();
	await expect(page.getByTestId('terrain-row')).toHaveAttribute('data-status', 'done');
});

test('worker error surfaces on the row', async ({ page }) => {
	const err = 'RuntimeError: viewpoint outside the DEM / on nodata';
	await stubTerrainApi(page, () => [
		renderRow({ status: 'error', error: err, meta: null, has_depth: false, has_preview: false })
	]);
	await page.goto('/terrain');
	await expect(page.getByTestId('terrain-row')).toHaveAttribute('data-status', 'error');
	await expect(page.getByTestId('terrain-row')).toContainText('viewpoint outside the DEM');
});
