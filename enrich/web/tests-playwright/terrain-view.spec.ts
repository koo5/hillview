/**
 * Terrain viewer specs — the fast tier (route-stubbed API, real vite + WebGL).
 *
 * The heart is the cross-language golden thread: make_fixture.py picked pixel
 * targets and computed their geo coordinates with the PYTHON renderer; these
 * specs click those pixels and assert the TypeScript click-back agrees within
 * golden.tolerance_deg. If renderer.py and shared/terrain ever drift apart,
 * this is the suite that goes red.
 */
import { expect, test } from '@playwright/test';
import {
	colorDist,
	golden,
	openFixtureRender,
	pagePoint,
	readPixelAt,
	renderRow,
	SKY_RGB,
	stubTerrainApi
} from './helpers/terrainFixtures';

test.beforeEach(async ({ page }) => {
	await stubTerrainApi(page, () => [renderRow()]);
	await openFixtureRender(page);
});

async function clickAndReadCoords(page: import('@playwright/test').Page, pick: {
	col: number;
	row: number;
}) {
	const box = (await page.getByTestId('terrain-canvas').boundingBox())!;
	const p = pagePoint(box, pick);
	await page.mouse.click(p.x, p.y);
	const text = await page.getByTestId('terrain-picked').innerText();
	const m = text.match(/(-?\d+\.\d+), (-?\d+\.\d+)/);
	expect(m, `no coords in picked panel: "${text}"`).toBeTruthy();
	return { lat: parseFloat(m![1]), lon: parseFloat(m![2]), text };
}

test('paints terrain and sky distinctly', async ({ page }) => {
	const summitPx = await readPixelAt(page, golden.summit);
	const skyPx = await readPixelAt(page, golden.sky);
	// sky pixel sits near the configured sky color; terrain pixel does not
	expect(colorDist(skyPx, SKY_RGB)).toBeLessThan(40);
	expect(colorDist(summitPx, SKY_RGB)).toBeGreaterThan(60);
});

test('golden click-back: summit coords match the Python renderer', async ({ page }) => {
	const tol = golden.tolerance_deg + 1e-5; // + display rounding (toFixed(5))
	const got = await clickAndReadCoords(page, golden.summit);
	expect(Math.abs(got.lat - golden.summit.lat)).toBeLessThan(tol);
	expect(Math.abs(got.lon - golden.summit.lon)).toBeLessThan(tol);
	expect(got.text).toContain(`${(golden.summit.distance_m / 1000).toFixed(1)} km`);
	// the map link carries the same coordinates
	const href = await page.getByTestId('terrain-picked').locator('a').getAttribute('href');
	expect(href).toContain(`lat=${got.lat}`);
});

test('golden click-back: far ridge and near slope', async ({ page }) => {
	const tol = golden.tolerance_deg + 1e-5;
	for (const pick of [golden.far_ridge, golden.near_slope]) {
		const got = await clickAndReadCoords(page, pick);
		expect(Math.abs(got.lat - pick.lat)).toBeLessThan(tol);
		expect(Math.abs(got.lon - pick.lon)).toBeLessThan(tol);
	}
});

test('click-back survives zoom (cursor-anchored) ', async ({ page }) => {
	const box = (await page.getByTestId('terrain-canvas').boundingBox())!;
	const p = pagePoint(box, golden.summit);
	await page.mouse.move(p.x, p.y);
	for (let i = 0; i < 4; i++) await page.mouse.wheel(0, -100); // zoomAt anchors cursor
	const got = await clickAndReadCoords(page, golden.summit);
	const tol = golden.tolerance_deg + 1e-5;
	expect(Math.abs(got.lat - golden.summit.lat)).toBeLessThan(tol);
	expect(Math.abs(got.lon - golden.summit.lon)).toBeLessThan(tol);
});

test('sky click clears the pick', async ({ page }) => {
	await clickAndReadCoords(page, golden.summit);
	const box = (await page.getByTestId('terrain-canvas').boundingBox())!;
	const s = pagePoint(box, golden.sky);
	await page.mouse.click(s.x, s.y);
	await expect(page.getByTestId('terrain-picked')).toHaveCount(0);
});

test('fog is Koschmieder-shaped: distance-dependent, live', async ({ page }) => {
	const vis = page.getByTestId('terrain-visibility');
	await vis.fill('300'); // ~clear: far ridge (54 km) half-fogged, near hill (4 km) barely
	const farClear = await readPixelAt(page, golden.far_ridge);
	const nearClear = await readPixelAt(page, golden.near_slope);
	await vis.fill('30'); // hazy: far ridge fully swallowed, near hill only partly
	const farHazy = await readPixelAt(page, golden.far_ridge);
	const nearHazy = await readPixelAt(page, golden.near_slope);

	const toSky = (px: number[]) => colorDist(px, SKY_RGB);
	// far ridge converges hard toward the sky color…
	expect(toSky(farHazy)).toBeLessThan(15);
	expect(toSky(farClear) - toSky(farHazy)).toBeGreaterThan(25);
	// …while the near hill moves much less: fog depends on DEPTH, not uniformly
	expect(toSky(nearClear) - toSky(nearHazy)).toBeLessThan(
		(toSky(farClear) - toSky(farHazy)) * 0.6
	);
});
