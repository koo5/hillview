import { expect, test } from '@playwright/test';

// The day the root filesystem filled up, every request 500'd and the only symptom on
// screen was "queue unknown". The machine card is the numbers that would have said why.
test('the dashboard shows machine health and its warnings', async ({ page }) => {
	await page.route('**/api/health', async (route) =>
		route.fulfill({ json: { ok: true, checks: [{ dep: 'workbench-db', ok: true, ms: 1 }] } })
	);
	await page.route('**/api/sync/status', async (route) =>
		route.fulfill({ json: { running: false, tables: [], runs: [] } })
	);
	await page.route('**/api/health/machine', async (route) =>
		route.fulfill({
			json: {
				ok: false,
				warnings: ['disk /artifacts: 3.1 GB free (99.0% used)'],
				disks: [{ path: '/artifacts', total_gb: 294.2, free_gb: 3.1, used_pct: 99.0 }],
				memory: { total_gb: 59.1, available_gb: 49.0 },
				load: { '1m': 14.9, '5m': 14.9, '15m': 11.5, cores: 16 },
				recon_queue: { messages: 8, consumers: 0 }
			}
		})
	);
	await page.goto('/');
	const card = page.getByTestId('machine-card');
	await expect(card).toBeVisible({ timeout: 20_000 });
	await expect(page.getByTestId('machine-warning')).toContainText('3.1 GB free');
	await expect(card).toContainText('8 waiting');
	await expect(card).toContainText('0 workers');
});
