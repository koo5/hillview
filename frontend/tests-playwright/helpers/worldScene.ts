/**
 * The 3D world pane for specs that fly it (hillview_common WorldScene): opening it, its height readout, flight coming
 * to rest, and the app's location it writes back. Its scene needs WebGL (SwiftShader in Chromium) and public earth.
 */
import { expect, type Page } from '@playwright/test';
import { T } from './timeouts';

/** the layers a flying spec wants: bare ground and nothing else to load, the height readout on */
export const FLY_LAYERS = { terrain: 'bare', ortho: false, buildings: false, atlas: null, names: false, readout: true };

const M_PER_DEG = 111_320;

/** open the 3D pane and wait until its scene has settled (the ground under the observer loaded) */
export async function openWorldScene(page: Page) {
	await page.getByTestId('world-button').click({ timeout: T(30_000) });
	const scene = page.getByTestId('world-scene');
	await expect(scene).toBeVisible({ timeout: T(30_000) });
	for (const b of await page.locator('.main-page-alert-area button').all()) await b.click().catch(() => {});
	await expect(scene).toHaveAttribute('data-settled', 'true', { timeout: T(120_000) });
	return scene;
}

/** the flown camera's height over the ground, from the readout; null standing, or with no ground under it loaded */
export async function overGroundM(page: Page): Promise<number | null> {
	const m = (await page.getByTestId('world-scene-readout').innerText()).match(/(-?[\d.]+) m over ground/);
	return m ? Number(m[1]) : null;
}

/** flight at rest: the same height 500 ms apart, both read inside one poll (expect.poll calls at once, before a frame
 * was drawn, so a read against the one before it took a camera still coasting for one at rest); that height */
export async function flightAtRest(page: Page): Promise<number> {
	let last: number | null = null;
	await expect.poll(async () => {
		const before = await overGroundM(page);
		await page.waitForTimeout(500);
		last = await overGroundM(page);
		return before !== null && last !== null && Math.abs(last - before) < 0.05;
	}, { timeout: T(30_000), intervals: [0] }).toBe(true);
	return last!;
}

/** the app's location (spatialState), which flight writes back */
export function appCentre(page: Page): Promise<{ lat: number; lng: number }> {
	return page.evaluate(() => JSON.parse(localStorage.getItem('spatialState') ?? 'null').center);
}

/** ground distance between two points a few hundred metres apart, metres */
export function metresBetween(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
	return Math.hypot((a.lat - b.lat) * M_PER_DEG, (a.lng - b.lng) * M_PER_DEG * Math.cos((a.lat * Math.PI) / 180));
}
