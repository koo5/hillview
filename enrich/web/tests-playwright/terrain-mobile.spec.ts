/**
 * Mobile layout smoke for the terrain bench: at a phone viewport the page
 * must not scroll horizontally, the stacked sidebar must leave the stage a
 * real share of the screen, and the viewer must still load and paint.
 */
import { expect, test } from '@playwright/test';
import { openFixtureRender, renderRow, stubTerrainApi } from './helpers/terrainFixtures';

test.use({ viewport: { width: 390, height: 844 } });

test('phone viewport: no horizontal overflow, stage gets real height', async ({ page }) => {
	await stubTerrainApi(page, () => [renderRow()]);
	await openFixtureRender(page); // waits until the canvas actually paints

	const m = await page.evaluate(() => ({
		scrollW: document.documentElement.scrollWidth,
		innerW: window.innerWidth,
		bodyScrollH: document.body.scrollHeight,
		innerH: window.innerHeight
	}));
	expect(m.scrollW).toBeLessThanOrEqual(m.innerW);
	expect(m.bodyScrollH).toBeLessThanOrEqual(m.innerH + 1); // page owns the viewport

	const canvas = (await page.getByTestId('terrain-canvas').boundingBox())!;
	expect(canvas.width).toBeGreaterThan(380);
	expect(canvas.height).toBeGreaterThan(844 * 0.3); // stage ≥ ~30% of the screen

	// the render list must have real height (regression: flex-remainder
	// inside the capped sidebar collapsed it to 0 — "there's no list")
	const listH = await page.getByTestId('terrain-row').first().evaluate(
		(el) => (el.closest('ul') as HTMLElement).clientHeight
	);
	expect(listH).toBeGreaterThan(80);
});
