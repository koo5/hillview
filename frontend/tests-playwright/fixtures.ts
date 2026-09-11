import { test as base } from '@playwright/test';
import { T } from './helpers/timeouts';
import { recreateTestUsers, type TestUserSetupResult } from './helpers/testUsers';
import { setupConsoleLogging } from './helpers/consoleLogging';
import { trackPendingRequests } from './helpers/pendingRequests';
import { mockPanoramaxSearch } from './helpers/panoramaxMocks';

/**
 * Track which spec file last triggered user recreation.
 * With workers: 1 and fullyParallel: false, this gives us
 * per-file isolation: users are recreated when a new spec
 * file starts, cascade-deleting photos/hidden_users/annotations
 * from the previous file.
 */
let lastSetupFile = '';
let cachedResult: TestUserSetupResult | null = null;

/**
 * Custom test fixtures applied to every Playwright test.
 *
 * Import { test, expect } from './fixtures' instead of '@playwright/test'.
 *
 * Available fixtures:
 *   testUsers - automatically recreates test users once per spec file.
 *               Provides { passwords, users_created, users_deleted }.
 *   panoramaxDefault - opt back in to the app's real default for the Panoramax
 *               source (on). Off for every test unless a spec says
 *               `test.use({ panoramaxDefault: true })`. See below.
 */
export const test = base.extend<{ testUsers: TestUserSetupResult; panoramaxDefault: boolean }>({
	panoramaxDefault: [false, { option: true }],

	page: async ({ page, panoramaxDefault }, use) => {
		// Make every fake-camera capture produce unique pixel data so the
		// server-side duplicate-detection (MD5-based) never triggers across
		// captures within or between tests.
		await page.addInitScript(() => {
			let captureCounter = 0;
			const origDrawImage = CanvasRenderingContext2D.prototype.drawImage;
			CanvasRenderingContext2D.prototype.drawImage = function (...args: any[]) {
				origDrawImage.apply(this, args);
				if (args[0] instanceof HTMLVideoElement) {
					captureCounter++;
					this.fillStyle = 'rgba(255,255,255,0.01)';
					this.font = '10px monospace';
					this.fillText(`${captureCounter}-${Date.now()}`, 1, 10);
				}
			};
		});

		// Panoramax is on by default in the app and its photos are fetched from
		// the public instance by the photo WORKER — and Playwright cannot route a
		// worker's requests in WebKit (probed on 1.59.1: the handler never fires,
		// page.route and context.route alike). So the route mock below holds on
		// chromium and firefox only, and on WebKit every map test was quietly
		// loading ~99 real photos from api.panoramax.xyz, which broke any test
		// counting markers or picking "the" photo off the map.
		//
		// Turning the source off before the app boots is the part that works
		// everywhere: no request, no markers, whatever the browser does with
		// routes. A spec that is actually about Panoramax opts out with
		// `test.use({ panoramaxDefault: true })`.
		if (!panoramaxDefault) {
			await page.addInitScript(() => {
				try {
					const raw = window.localStorage.getItem('sourceStates');
					const states = raw ? JSON.parse(raw) : {};
					if (states.panoramax === undefined) {
						states.panoramax = false;
						window.localStorage.setItem('sourceStates', JSON.stringify(states));
					}
				} catch {
					/* private mode or a corrupt value — the route mock is still there */
				}
			});
		}
		await mockPanoramaxSearch(page, []);

		// Relay browser console/errors to test output (gated by PLAYWRIGHT_CONSOLE_LOG env var)
		setupConsoleLogging(page);

		// Instrument waits so we can see which sleeps are slow / unnecessary
		const origTimeout = page.waitForTimeout.bind(page);
		page.waitForTimeout = async (ms: number) => {
			const caller = new Error().stack?.split('\n')[2]?.trim() || '?';
			console.log(`⏱️ [SLEEP] waitForTimeout(${ms}) — start — ${caller}`);
			const t = Date.now();
			await origTimeout(ms);
			console.log(`⏱️ [SLEEP] waitForTimeout(${ms}) — done in ${Date.now() - t}ms`);
		};

		// Track in-flight requests so a networkidle timeout can show what
		// was still outstanding when the wait failed.
		const tracker = trackPendingRequests(page);

		const origLoadState = page.waitForLoadState.bind(page);
		page.waitForLoadState = async (state?: any, options?: any) => {
			const caller = new Error().stack?.split('\n')[2]?.trim() || '?';
			console.log(`⏱️ [SLEEP] waitForLoadState(${state}) — start — ${caller}`);
			const t = Date.now();
			try {
				await origLoadState(state, options);
			} catch (e) {
				tracker.logSnapshot(`⏱️ [SLEEP] waitForLoadState(${state}) — TIMEOUT after ${Date.now() - t}ms; `);
				throw e;
			}
			console.log(`⏱️ [SLEEP] waitForLoadState(${state}) — done in ${Date.now() - t}ms`);
		};

		// Every navigation waits for the app to be interactive AND showing this
		// visitor's own view, not just painted. Two things go wrong otherwise, both
		// traced on 2026-09-04:
		//
		//   `data-hydrated` — `waitUntil: 'load'` is about subresources and resolves
		//   BEFORE hydration on the server-rendered routes. A goto resolved and the
		//   test's click landed 50ms before that document's client code started, on
		//   markup the server had sent. Svelte 5 replays onload/onerror only, so the
		//   click was simply lost.
		//
		//   `data-loading` — the server has no session, so those pages first paint
		//   the ANONYMOUS view and correct it once auth settles. A rating test read
		//   "not rated yet" off that anonymous paint and pressed its shortcut against
		//   stale state. See $lib/pageLoading.
		//
		// A timeout here is not flake, it is "this build has no markers" — usually a
		// stale `hillview_frontend` container. Fail loudly rather than silently going
		// back to racing the app.
		const goto = page.goto.bind(page);
		page.goto = async (url: string, options?: any) => {
			const response = await goto(url, options);
			await page.waitForFunction(
				() => {
					const html = document.documentElement;
					return html.hasAttribute('data-hydrated') && !html.hasAttribute('data-loading');
				},
				undefined,
				{ timeout: T(15000) }
			);
			return response;
		};

		// NOT here: a retry for "page.goto: WebKit encountered an internal error",
		// the harness fault that took down six unrelated specs in one full run.
		// Tried and reverted 2026-09-03 — the second navigation lands while the
		// first one's token refresh is still in flight, and the backend runs
		// single-use refresh rotation with reuse detection, which revokes the
		// whole session. The retry turned a legible harness error on /account into
		// "Failed to load profile: 401" and an unrelated-looking assertion failure.
		// Any retry here has to survive that, and a plain re-goto does not.

		await use(page);
	},

	testUsers: [async ({}, use, testInfo) => {
		// Recreate test users once per spec file for isolation.
		// Subsequent tests within the same file reuse the cached result.
		if (testInfo.file !== lastSetupFile) {
			lastSetupFile = testInfo.file;
			cachedResult = await recreateTestUsers();
		}
		await use(cachedResult!);
	}, { auto: true }],
});

export { expect } from '@playwright/test';
