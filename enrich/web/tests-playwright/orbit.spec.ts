import { expect, test } from '@playwright/test';

// Visual assessment rig: load one run's cloud and screenshot it from several angles.
// RUN=<name> DENSE=1 PHOTOS=1 OUT=/dir PREFIX=name VIEWS="az,el,zoom;az,el,zoom;..."
test('orbit', async ({ page }) => {
	test.setTimeout(600_000);
	await page.goto(`/recon?run=${process.env.RUN}`);
	const loadBtn = page.getByRole('button', { name: 'load point cloud' });
	const stage = page.getByTestId('recon-cloud');
	await expect(loadBtn.or(stage).first()).toBeVisible({ timeout: 60_000 });
	await page.mouse.wheel(0, 4000);
	if (await loadBtn.isVisible().catch(() => false)) await loadBtn.click();
	await expect(stage).toBeVisible({ timeout: 30_000 });
	if (process.env.DENSE) {
		await page.getByRole('button', { name: 'dense', exact: true }).click();
		await expect(page.getByText(/points \(dense\)/)).toBeVisible({ timeout: 150_000 });
	} else {
		await expect(page.getByText(/[\d,]+ points/)).toBeVisible({ timeout: 120_000 });
	}
	if (process.env.NOMAP) await page.getByRole('checkbox', { name: 'OSM map' }).uncheck();
	if (process.env.PHOTOS) {
		await page.getByRole('checkbox', { name: 'photos' }).check();
		await expect(page.getByText(/\d+ loaded/)).toBeVisible({ timeout: 90_000 });
	}
	if (process.env.PTSIZE) {
		await page.locator('.hud label', { hasText: 'points' }).locator('input').first()
			.fill(process.env.PTSIZE);
	}
	if (process.env.CAMSIZE) {
		await page.locator('.hud label', { hasText: 'cameras' }).locator('input').first()
			.fill(process.env.CAMSIZE);
	}
	if (process.env.NOEDL) await page.getByRole('checkbox', { name: 'solid' }).uncheck();
	await stage.scrollIntoViewIfNeeded();
	await page.waitForTimeout(2500);

	const box = (await stage.boundingBox())!;
	const cx = box.x + box.width / 2;
	const cy = box.y + box.height / 2;
	// OrbitControls: one drag of the full canvas width is ~2*PI in azimuth
	const views = (process.env.VIEWS || '0,0,0').split(';');
	let curAz = 0, curEl = 0, curZoom = 0;
	for (let i = 0; i < views.length; i++) {
		const [az, el, zoom] = views[i].split(',').map(Number);
		const dx = ((az - curAz) / 360) * box.width;
		const dy = ((el - curEl) / 180) * box.height;
		if (dx || dy) {
			await page.mouse.move(cx, cy);
			await page.mouse.down();
			await page.mouse.move(cx + dx, cy + dy, { steps: 20 });
			await page.mouse.up();
		}
		const dz = zoom - curZoom;
		if (dz) {
			await page.mouse.move(cx, cy);
			for (let k = 0; k < Math.abs(dz); k++) {
				await page.mouse.wheel(0, dz > 0 ? 120 : -120);
				await page.waitForTimeout(40);
			}
		}
		curAz = az; curEl = el; curZoom = zoom;
		await page.waitForTimeout(900);
		await stage.screenshot({ path: `${process.env.OUT}/${process.env.PREFIX}_${i}.png` });
		console.log(`shot ${i}: az=${az} el=${el} zoom=${zoom}`);
	}
});
