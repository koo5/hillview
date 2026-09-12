import path from 'node:path';
import { defineConfig } from '@playwright/test';

// Enrich workbench e2e — the fast tier: the vite dev server is real, the API
// is route-stubbed per test (see helpers/terrainFixtures.ts), so no backend,
// worker, or RabbitMQ is needed. The nightly compose tier runs the same specs
// against the deployed stack (PW_BASE_URL + PW_NO_STUBS, later).
//
// WebGL: swiftshader flags force software GL so the terrain viewer's WebGL2
// context works in headless CI runners without a GPU.
export default defineConfig({
	testDir: '.',
	timeout: 30_000,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 1 : 0,
	// NOT 8071: the built enrich_web container publishes 127.0.0.1:8071, and with
	// reuseExistingServer playwright would take that -- the LAST BUILD, not the working
	// tree -- and every test would quietly exercise stale code (a day was lost to
	// "flaky" failures that were exactly this). The dev server gets its own port.
	use: {
		baseURL: process.env.PW_BASE_URL || 'http://localhost:8072',
		viewport: { width: 1280, height: 800 },
		trace: 'retain-on-failure'
	},
	webServer: {
		command: 'bun run dev -- --port 8072 --strictPort',
		cwd: path.join(import.meta.dirname, '..'),
		url: 'http://localhost:8072',
		reuseExistingServer: !process.env.CI,
		timeout: 60_000
	},
	projects: [
		{
			name: 'chromium',
			use: {
				browserName: 'chromium',
				launchOptions: {
					args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader']
				}
			}
		}
	]
});
