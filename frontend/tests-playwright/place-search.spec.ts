// This feature needs no accounts or photo fixtures: mock only the geocoder,
// keeping the activity, coordinate parser, shared state, map, and URL real.
import { test, expect } from '@playwright/test';
import { T } from './helpers/timeouts';

const place = {
	id: '42', name: 'Praha', display_name: 'Praha, Česko', lat: 50.0875, lon: 14.4213,
	bounds: [49.94, 50.18, 14.22, 14.71]
};

test.beforeEach(async ({ page }) => {
	await page.addInitScript(() => {
		localStorage.setItem('sourceStates', JSON.stringify({
			hillview: true, mapillary: false, panoramax: false, device: false
		}));
	});
});

test('search is a peer activity and selecting a result moves the map', async ({ page }) => {
	let queries = 0;
	await page.route('**/places/search?*', async route => {
		queries++;
		expect(new URL(route.request().url()).searchParams.get('q')).toBe('Praha');
		await route.fulfill({ json: [place] });
	});
	await page.goto('/?lat=49.5&lon=15.5&zoom=12&activity=view');
	await page.getByTestId('search-button').click();
	await expect(page.getByTestId('search-pane')).toBeVisible();
	await page.getByTestId('place-search-input').fill('Praha');
	expect(queries).toBe(0);
	await page.getByTestId('place-search-input').press('Enter');
	await expect(page.getByTestId('place-search-result')).toContainText('Praha, Česko');
	await page.getByTestId('place-search-result').click();
	await expect.poll(() => new URL(page.url()).searchParams.get('lat'), { timeout: T(10000) }).toBe('50.0875');
	expect(new URL(page.url()).searchParams.get('lon')).toBe('14.4213');
	expect(Number(new URL(page.url()).searchParams.get('zoom'))).toBeLessThan(16);
	await expect(page.getByTestId('search-pane')).toBeVisible();
	await page.getByTestId('lines-button').click();
	await expect(page.getByTestId('lines-view')).toBeVisible();
	await expect(page.getByTestId('search-pane')).toBeHidden();
	await page.getByTestId('search-button').click();
	await expect(page.getByTestId('search-pane')).toBeVisible();
	await expect.poll(() => new URL(page.url()).searchParams.get('activity')).toBe('search');
	await page.reload();
	await expect(page.getByTestId('search-pane')).toBeVisible();
	await page.getByTestId('search-button').click();
	await expect(page.getByTestId('search-pane')).toBeHidden();
});

test('pasted DMS coordinates bypass the geocoder and move the map', async ({ page }) => {
	let queries = 0;
	await page.route('**/places/search?*', async route => { queries++; await route.fulfill({ json: [] }); });
	await page.goto('/?lat=49.5&lon=15.5&zoom=12&activity=search');
	await page.getByTestId('place-search-input').fill('50°10\'29.869"N, 14°38\'52.907"E');
	await page.getByTestId('place-search-submit').click();
	await expect(page.getByTestId('place-search-result')).toContainText('50.1749636, 14.6480297');
	await page.getByTestId('place-search-result').click();
	await expect.poll(() => Number(new URL(page.url()).searchParams.get('lat'))).toBeCloseTo(50.1749636, 5);
	expect(Number(new URL(page.url()).searchParams.get('lon'))).toBeCloseTo(14.6480297, 5);
	expect(queries).toBe(0);
});

test('the lines URL activity also yields to a later toolbar choice', async ({ page }) => {
	await page.goto('/?activity=lines&lat=49.5&lon=15.5&zoom=12');
	await expect(page.getByTestId('lines-view')).toBeVisible();
	await page.getByTestId('search-button').click();
	await expect(page.getByTestId('search-pane')).toBeVisible();
	await expect.poll(() => new URL(page.url()).searchParams.get('activity')).toBe('search');
	await expect(page.getByTestId('lines-view')).toBeHidden();
});

test('empty results and a failed search leave the form usable', async ({ page }) => {
	await page.route('**/places/search?*', async route => {
		const q = new URL(route.request().url()).searchParams.get('q');
		await route.fulfill(q === 'missing' ? { json: [] } : { status: 502, json: { detail: 'Unavailable' } });
	});
	await page.goto('/?activity=search&lat=49.5&lon=15.5&zoom=12');
	await page.getByTestId('place-search-input').fill('missing');
	await page.getByTestId('place-search-submit').click();
	await expect(page.getByTestId('place-search-empty')).toBeVisible();
	await page.getByTestId('place-search-input').fill('Praha');
	await page.getByTestId('place-search-submit').click();
	await expect(page.getByTestId('place-search-error')).toBeVisible();
	await expect(page.getByTestId('place-search-submit')).toBeEnabled();
});
