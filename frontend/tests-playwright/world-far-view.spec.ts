import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';

/**
 * The 3D world from far away (the operator, 2026-11-03: "a test that starts in prague, flies 30km away and then looks
 * back and zooms in back on prague. The final loading time is huge, and IPR buildings dont show").
 *
 * Start standing in Prague's Old Town; fly ~30 km out at 1500 m/s (the scene re-lays its frame past 20 km); land,
 * rise to ~300 m with the height stick, face Prague, level the view, zoom to ~6 degrees. What it holds:
 * - the re-layout keeps what was loaded (it used to drop every tile: '0/218', and the camera fell 1 km under the
 *   ground it no longer had);
 * - the flown camera never goes under the loaded ground;
 * - zoomed on Prague, the view settles with IPR's buildings drawn (a 3 km reach in metres drew none from 30 km).
 * It logs each phase's time and requests. Reads public earth (VITE_EARTH_URL), so it is @stress, not in test:quick.
 */
const START = { lat: 50.0875, lng: 14.4214 };

test.describe('3D world from far away @stress', () => {
	test.skip(({ browserName }) => browserName !== 'chromium', 'the 3D world needs WebGL: SwiftShader in Chromium');

	test('fly 30 km out of Prague, look back and zoom: the view settles with its buildings', async ({ page }) => {
		test.setTimeout(T(600_000));
		const requests: Record<string, Record<string, number>> = {};
		let phase = 'start';
		page.on('request', (r) => {
			const u = r.url();
			const kind = /\/terrain\//.test(u) ? 'terrain' : /\/ortho\//.test(u) ? 'ortho' : /\/models\//.test(u) ? 'models' : null;
			if (kind) (requests[phase] ??= {})[kind] = (requests[phase]?.[kind] ?? 0) + 1;
		});
		await page.addInitScript((start) => {
			if (sessionStorage.getItem('world-far-view')) return;
			sessionStorage.setItem('world-far-view', '1');
			localStorage.setItem('spatialState', JSON.stringify({ center: start, zoom: 15, bounds: null, range: 500, source: 'map', ts: Date.now() }));
			localStorage.setItem('bearingState', JSON.stringify({ bearing: 120, source: 'map', ts: Date.now() }));
			localStorage.setItem('world.scene.layers', JSON.stringify({ terrain: 'bare', ortho: true, buildings: true, atlas: null, names: false, readout: true }));
			localStorage.setItem('world.fly.speedMps', '1500');
		}, START);
		await page.goto('/');
		await page.getByTestId('world-button').click({ timeout: T(30_000) });
		const scene = page.getByTestId('world-scene');
		await expect(scene).toBeVisible({ timeout: T(30_000) });
		for (const b of await page.locator('.main-page-alert-area button').all()) await b.click().catch(() => {});

		const settled = async (what: string, limitMs: number) => {
			const t0 = Date.now();
			await expect(scene).toHaveAttribute('data-settled', 'true', { timeout: limitMs });
			console.log(`${what}: settled in ${Math.round((Date.now() - t0) / 1000)} s, tiles ${await scene.getAttribute('data-tiles')}, buildings ${await scene.getAttribute('data-buildings')}`);
		};
		const away = () => page.evaluate((s) => {
			const c = JSON.parse(localStorage.getItem('spatialState') ?? 'null').center;
			return Math.hypot((c.lat - s.lat) * 111_320, (c.lng - s.lng) * 111_320 * Math.cos((s.lat * Math.PI) / 180));
		}, START);
		const overGround = async () => {
			const m = (await page.getByTestId('world-scene-readout').innerText()).match(/(-?[\d.]+) m over ground/);
			return m ? Number(m[1]) : null;
		};
		await settled('standing in Prague', T(120_000));
		const frame0 = await scene.getAttribute('data-frame');

		// fly ~30 km out (past the 20 km re-layout); the camera never goes under the ground it has
		phase = 'fly';
		await scene.focus();
		await page.keyboard.down('KeyR');
		await page.waitForTimeout(1500);
		await page.keyboard.up('KeyR');
		await page.keyboard.down('KeyW');
		let lowest = Infinity;
		for (let i = 0; i < 240 && (await away()) < 30_000; i++) {
			const h = await overGround();
			if (h !== null) lowest = Math.min(lowest, h);
			await page.waitForTimeout(500);
		}
		await page.keyboard.up('KeyW');
		expect(await away()).toBeGreaterThan(29_000);
		expect(await scene.getAttribute('data-frame')).not.toBe(frame0);                 // it re-laid its frame
		expect(Number((await scene.getAttribute('data-tiles'))?.split('/')[0])).toBeGreaterThan(0);   // and kept its tiles
		expect(lowest).toBeGreaterThanOrEqual(1.4);                                       // never under the ground
		console.log(`flown ${Math.round(await away())} m, lowest ${lowest} m over the ground`);

		// land, rise to ~300 m, face Prague, level the view
		phase = 'aim';
		await page.keyboard.press('Escape');
		const stick = (await page.getByTestId('world-scene-stick').boundingBox())!;
		await page.mouse.move(stick.x + stick.width / 2, stick.y + stick.height / 2);
		await page.mouse.down();
		await page.mouse.move(stick.x + stick.width / 2, stick.y + stick.height / 2 - 40, { steps: 5 });
		await expect.poll(async () => Number(await scene.getAttribute('data-eye-m')), { timeout: T(30_000) }).toBeGreaterThan(300);
		await page.mouse.up();
		const bearing = async () => Number(await scene.getAttribute('data-bearing'));
		const target = await page.evaluate((s) => {
			const c = JSON.parse(localStorage.getItem('spatialState') ?? 'null').center;
			const dn = (s.lat - c.lat) * 111_320, de = (s.lng - c.lng) * 111_320 * Math.cos((s.lat * Math.PI) / 180);
			return ((Math.atan2(de, dn) * 180) / Math.PI + 360) % 360;
		}, START);
		const box = (await scene.boundingBox())!;
		const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
		const drag = async (dx: number, dy: number) => {
			await page.mouse.move(cx, cy);
			await page.mouse.down();
			await page.mouse.move(cx + dx, cy + dy, { steps: 8 });
			await page.mouse.up();
			await page.waitForTimeout(300);
		};
		const b0 = await bearing();
		await drag(40, 0);
		const degPerPx = ((((await bearing()) - b0 + 540) % 360) - 180) / 40;
		for (let k = 0; k < 6; k++) {
			const left = ((target - (await bearing()) + 540) % 360) - 180;
			if (Math.abs(left) < 0.3) break;
			await drag(Math.max(-500, Math.min(500, left / degPerPx)), 0);
		}
		await drag(0, Math.round((-0.5 - Number(await scene.getAttribute('data-pitch'))) / Math.abs(degPerPx)));

		// zoom to ~6 degrees on Prague: the view settles, with IPR's buildings
		phase = 'zoom';
		await scene.focus();
		for (let i = 0; i < 24; i++) await page.keyboard.press('Equal');
		await settled('zoomed on Prague from 30 km', T(300_000));
		const drawn = Number((await scene.getAttribute('data-buildings'))?.match(/^(\d+) drawn/)?.[1] ?? 0);
		expect(drawn).toBeGreaterThan(0);
		console.log('requests per phase', JSON.stringify(requests));
	});
});
