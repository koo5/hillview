import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { FLY_LAYERS, appCentre, flightAtRest, metresBetween, openWorldScene, overGroundM } from './helpers/worldScene';

/**
 * Flying, the height stick moves straight up from the earth, not along the camera's own up (the operator, 2026-11-10:
 * "the height knob should probably fly you up and down perpendicular to earth, not your own axis"). Looking 60°
 * down, the camera's up leans 60° off the vertical: a rise along it slid ~1.7 m over the ground per metre gained.
 * Now the ground point stays put. Reads public earth (VITE_EARTH_URL), so it is @stress, not in test:quick.
 */
const START = { lat: 50.0875, lng: 14.4214 };
const LOOK_DOWN_DEG = -60;

test.describe('3D world height stick @stress', () => {
	test.skip(({ browserName }) => browserName !== 'chromium', 'the 3D world needs WebGL: SwiftShader in Chromium');

	test('flying and looking down, the stick rises straight up from the earth', async ({ page }) => {
		test.setTimeout(T(300_000));
		await page.addInitScript(({ start, layers }) => {
			if (sessionStorage.getItem('world-height-stick')) return;
			sessionStorage.setItem('world-height-stick', '1');
			localStorage.setItem('spatialState', JSON.stringify({ center: start, zoom: 17, bounds: null, range: 50, source: 'map', ts: Date.now() }));
			localStorage.setItem('bearingState', JSON.stringify({ bearing: 90, source: 'map', ts: Date.now() }));
			localStorage.setItem('world.scene.layers', JSON.stringify(layers));
			localStorage.setItem('world.fly.speedMps', '50');
		}, { start: START, layers: FLY_LAYERS });
		await page.goto('/');
		const scene = await openWorldScene(page);

		// look 60° down: the drag grabs the view, so up the pane tilts it down (degrees per pixel: the fov over the height)
		const box = (await scene.boundingBox())!;
		const pitch = async () => Number(await scene.getAttribute('data-pitch'));
		for (let i = 0; i < 6 && Math.abs((await pitch()) - LOOK_DOWN_DEG) > 3; i++) {
			const dy = Math.max(-box.height * 0.4, Math.min(box.height * 0.4, (LOOK_DOWN_DEG - (await pitch())) / (55 / box.height)));
			await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 - dy / 2);
			await page.mouse.down();
			await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + dy / 2, { steps: 8 });
			await page.mouse.up();
		}
		expect(Math.abs((await pitch()) - LOOK_DOWN_DEG)).toBeLessThan(3);

		// take off with a tap of R, then come to rest
		await scene.focus();
		await page.keyboard.down('KeyR');
		await expect.poll(() => overGroundM(page), { timeout: T(30_000) }).not.toBeNull();
		await page.keyboard.up('KeyR');
		const h0 = await flightAtRest(page), c0 = await appCentre(page);

		// a full pull of the stick for a second
		const stick = (await page.getByTestId('world-scene-stick').boundingBox())!;
		await page.mouse.move(stick.x + stick.width / 2, stick.y + stick.height / 2);
		await page.mouse.down();
		await page.mouse.move(stick.x + stick.width / 2, stick.y + stick.height / 2 - 40, { steps: 5 });
		await page.waitForTimeout(1000);
		await page.mouse.up();
		const h1 = await flightAtRest(page), c1 = await appCentre(page);

		const slid = metresBetween(c0, c1);
		console.log(`looking ${await pitch()}°: the stick rose ${(h1 - h0).toFixed(1)} m, sliding ${slid.toFixed(2)} m over the ground`);
		await expect(scene).toHaveAttribute('data-flying', 'true');
		expect(h1 - h0).toBeGreaterThan(10);
		expect(slid).toBeLessThan(Math.max(1, (h1 - h0) * 0.05));
	});
});
