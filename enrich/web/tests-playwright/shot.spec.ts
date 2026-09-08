import { expect, test } from '@playwright/test';
test('shot', async ({ page }) => {
	test.setTimeout(180_000);
	await page.goto(`/recon?run=${process.env.RUN}`);
	// the viewer is lazy-mounted (IntersectionObserver) so a page visit does not eagerly
	// build a WebGL context; scroll to it, and take the manual fallback if offered
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
	console.log('HUD:', (await page.locator('.hud').first().innerText()).replace(/\n/g, ' | '));
	// ZOOM=n scrolls the orbit camera out n notches — a subject-scale cloud frames itself
	// at a few metres, so the OSM map layer around it is only visible zoomed out
	if (process.env.ZOOM) {
		const box = (await page.getByTestId('recon-cloud').boundingBox())!;
		await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
		for (let i = 0; i < Number(process.env.ZOOM); i++) {
			await page.mouse.wheel(0, 120);
			await page.waitForTimeout(60);
		}
	}
	await page.waitForTimeout(3000);
	await page.getByTestId('recon-cloud').screenshot({ path: process.env.SHOT! });
});
