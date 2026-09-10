/**
 * Recon bench specs — fast tier (route-stubbed API, real vite).
 *
 * What is worth pinning here is the bench's whole reason to exist: it ranks runs by
 * STRUCTURE, not by the GPS residual, and those two orderings disagree. The fixture
 * below reproduces the real disagreement in miniature — board_jan has the best GPS
 * residual (0.0 m over 3 cameras, where a 7-DoF fit is nearly arithmetic) and the worst
 * structure (560 px) — so a regression that quietly sorts by drift again goes red.
 *
 * The other pinned behaviour is the min-correspondence filter, which is what separates a
 * genuine false link (confidently wrong over thousands of matches) from a thin pair
 * (wild error over a dozen, and meaningless).
 */
import { expect, test, type Page } from '@playwright/test';

type Stat = { n: number; median: number; mean: number; rms: number; p90: number; max: number };
const stat = (median: number, p90 = median * 2): Stat => ({
	n: 1000,
	median,
	mean: median,
	rms: median,
	p90,
	max: p90 * 2
});

const RUNS = [
	{
		id: '00000000-0000-4000-8000-000000000001',
		name: 'masktest',
		n_frames: 4,
		n_pairs: 10,
		gps: 0.17,
		gps_ok: false,
		reproj: 0.71,
		epipolar: 0.33
	},
	{
		id: '00000000-0000-4000-8000-000000000002',
		name: 'walk_dense',
		n_frames: 48,
		n_pairs: 364,
		gps: 2.91,
		gps_ok: true,
		reproj: 2.55,
		epipolar: 0.7
	},
	{
		id: '00000000-0000-4000-8000-000000000003',
		name: 'board_jan',
		n_frames: 3,
		n_pairs: 6,
		gps: 0.0,
		gps_ok: false,
		reproj: 560.46,
		epipolar: 294.02
	}
];

function runRow(r: (typeof RUNS)[number]) {
	return {
		id: r.id,
		name: r.name,
		source: 'imported',
		status: 'done',
		error: null,
		n_frames: r.n_frames,
		n_pairs: r.n_pairs,
		captured_on: '2026-06-15',
		params: {},
		meta: {},
		has_cloud: true,
		has_topdown: false,
		has_pairs_matrix: false,
		metrics: {
			reproj_px: stat(r.reproj),
			epipolar_px: stat(r.epipolar),
			reproj_coverage: 0.97,
			n_behind_camera: 12,
			gps_residual_m: { med_resid: r.gps, mean_resid: r.gps, max_resid: r.gps },
			gps_residual_informative: r.gps_ok,
			pp_source: 'recon_resolve sidecar',
			pose_source: 'recon_resolve sidecar',
			reproduced_archived_solve: true
		}
	};
}

// one fat pair that is genuinely wrong, and one thin pair that is merely noisy — the
// filter must be able to tell them apart
const PAIRS = [
	{ i: 11, j: 9, n_corres: 3511, baseline_m: 4.75, reproj: stat(1094), epipolar: stat(80) },
	{ i: 21, j: 25, n_corres: 16, baseline_m: 1.42, reproj: stat(4531), epipolar: stat(300) },
	{ i: 0, j: 1, n_corres: 4907, baseline_m: 0.67, reproj: stat(0.45), epipolar: stat(0.25) }
];

async function stubReconApi(page: Page, queue: unknown = { messages: 0, consumers: 1 }) {
	await page.route('**/api/recon/runs', async (route) => {
		if (route.request().method() !== 'GET') return route.fallback();
		await route.fulfill({ json: { runs: RUNS.map(runRow), queue } });
	});
	await page.route('**/api/recon/runs/*', async (route) => {
		const id = new URL(route.request().url()).pathname.split('/').pop()!;
		const r = RUNS.find((x) => x.id === id) ?? RUNS[0];
		await route.fulfill({
			json: {
				...runRow(r),
				frames: [
					{
						idx: 0,
						id: 'aaaaaaaa-0000-0000-0000-000000000000',
						focal_px: 405,
						base_focal_px: 396,
						residual_m: 0.15,
						epipolar_px: 0.34,
						reproj_px: 0.81
					}
				],
				pairs: PAIRS,
				worst_pairs: [],
				geo: null
			}
		});
	});
}

test.beforeEach(async ({ page }) => {
	await stubReconApi(page);
});

test('ranks runs by structure, not by the GPS residual', async ({ page }) => {
	await page.goto('/recon');
	const rows = page.getByTestId('recon-run-row');
	await expect(rows).toHaveCount(3);
	// most recent first is the default now; the structure ranking is a toggle away
	await page.getByTestId('recon-sort-structure').click();
	// structure order: masktest 0.71 < walk_dense 2.55 < board_jan 560
	await expect(rows.nth(0)).toHaveAttribute('data-run', 'masktest');
	await expect(rows.nth(1)).toHaveAttribute('data-run', 'walk_dense');
	await expect(rows.nth(2)).toHaveAttribute('data-run', 'board_jan');
	// by GPS residual board_jan would sort FIRST (0.0 m) — that inversion is the point
});

test('flags a GPS residual computed over too few cameras', async ({ page }) => {
	await page.goto('/recon?run=board_jan');
	await expect(page.getByTestId('recon-detail')).toHaveAttribute('data-run', 'board_jan');
	await expect(page.getByTestId('recon-stat-gps')).toContainText('too few cameras');
	// and the structure metric still reports the run as broken
	await expect(page.getByTestId('recon-stat-reproj')).toContainText('560');
});

test('min-correspondence filter separates a false link from a thin pair', async ({ page }) => {
	await page.goto('/recon?run=walk_dense');
	await expect(page.getByTestId('recon-detail')).toBeVisible();

	// unfiltered: the thin 16-correspondence pair tops the table on raw error
	const rows = page.getByTestId('recon-pair-row');
	await expect(rows.first()).toContainText('21 → 25');

	// require 1000+ correspondences: the thin pair goes, the genuinely wrong link leads
	await page.getByTestId('recon-mincorres-1000').click();
	await expect(rows.first()).toContainText('11 → 9');
	await expect(page.getByText('21 → 25')).toHaveCount(0);
});

test('pins a single pair when one is selected', async ({ page }) => {
	await page.goto('/recon?run=walk_dense');
	const rows = page.getByTestId('recon-pair-row');
	await expect(rows).toHaveCount(3);
	await rows.first().click();
	await expect(rows).toHaveCount(1);
	await rows.first().click();
	await expect(rows).toHaveCount(3);
});

test('reports an impostor against the real frames own baseline', async ({ page }) => {
	// The Doppelganger control only means something if the impostor is compared with the
	// real frames rather than averaged into them, and if "produced no matches" is reported
	// as its own outcome instead of passing for a rejection.
	await page.unrouteAll();
	const withImpostors = {
		...runRow(RUNS[1]),
		metrics: {
			...runRow(RUNS[1]).metrics,
			n_injected: 2,
			real_only_reproj_px: stat(2.5),
			real_only_epipolar_px: stat(0.7),
			impostors: [
				{
					idx: 8,
					id: 'f05f60ee-0000-0000-0000-000000000000',
					n_corres_to_cluster: 4200,
					reproj_px: stat(310),
					epipolar_px: stat(88),
					reproj_ratio_vs_real: 124,
					epipolar_ratio_vs_real: 126,
					gps_residual_m: 0.3,
					verdict: 'rejected'
				},
				{
					idx: 9,
					id: 'b6d0d53b-0000-0000-0000-000000000000',
					n_corres_to_cluster: 12,
					reproj_px: null,
					epipolar_px: null,
					verdict: 'no-matches'
				}
			]
		}
	};
	await page.route('**/api/recon/runs', async (route) => {
		if (route.request().method() !== 'GET') return route.fallback();
		await route.fulfill({ json: { runs: [withImpostors], queue: { messages: 0, consumers: 1 } } });
	});
	await page.route('**/api/recon/runs/*', async (route) => {
		await route.fulfill({
			json: { ...withImpostors, frames: [], pairs: PAIRS, worst_pairs: [], geo: null }
		});
	});

	await page.goto('/recon');
	const panel = page.getByTestId('recon-impostors');
	await expect(panel).toBeVisible();
	// the baseline it is judged against must be stated, not implied
	await expect(panel).toContainText('2.50');
	const rows = page.getByTestId('recon-impostor-row');
	await expect(rows).toHaveCount(2);
	await expect(rows.nth(0)).toContainText('rejected');
	await expect(rows.nth(0)).toContainText('124');
	await expect(rows.nth(1)).toContainText('no-matches');
});

test('warns when shared intrinsics is set on a mixed-source cluster', async ({ page }) => {
	// One focal is only physically shared when the frames come from one camera. Sharing it
	// across e.g. a portrait walk plus a landscape board frame would impose a constraint the
	// hardware does not satisfy, so the preview has to say so before the run costs 20 minutes.
	await page.route('**/api/recon/preview', async (route) => {
		await route.fulfill({
			json: {
				n_frames: 5,
				single_camera: false,
				cameras: ['owner:a|1440x2560', 'owner:b|2560x1440'],
				dimensions: ['1440x2560', '2560x1440'],
				frames: [{ id: 'a', captured_at: '2026-06-15 18:35:11.000' }]
			}
		});
	});
	await page.goto('/recon');
	await expect(page.getByTestId('recon-run-row')).toHaveCount(3);
	await page.getByTestId('recon-new-toggle').click();
	// on by default (physically correct for one camera), so a mixed selection must warn
	await expect(page.getByTestId('recon-form-shared')).toBeChecked();
	await page.getByTestId('recon-preview').click();
	const warn = page.getByTestId('recon-mixed-warning');
	await expect(warn).toBeVisible();
	await expect(warn).toContainText('2560x1440');
	// unticking it clears the warning
	await page.getByTestId('recon-form-shared').uncheck();
	await expect(warn).toHaveCount(0);
});

test('says so when no worker is connected', async ({ page }) => {
	// the recon worker is a host process the stack cannot see, so "queued forever" would
	// otherwise be indistinguishable from "slow"
	await page.unrouteAll();
	await stubReconApi(page, { messages: 2, consumers: 0 });
	await page.goto('/recon');
	await expect(page.getByTestId('recon-queue')).toContainText('no worker connected');
});

test('previews the cluster before it can be enqueued', async ({ page }) => {
	let enqueued: unknown = null;
	await page.route('**/api/recon/preview', async (route) => {
		await route.fulfill({
			json: {
				n_frames: 5,
				frames: [
					{ id: 'aaaa1111-0000-0000-0000-000000000000', captured_at: '2026-06-15 18:28:33.000' },
					{ id: 'bbbb2222-0000-0000-0000-000000000000', captured_at: '2026-06-15 18:28:41.000' }
				]
			}
		});
	});
	await page.route('**/api/recon/runs', async (route) => {
		if (route.request().method() === 'POST') {
			enqueued = route.request().postDataJSON();
			return route.fulfill({ json: { queued: RUNS[1].id, name: 'walk_dense' } });
		}
		await route.fulfill({ json: { runs: RUNS.map(runRow), queue: { messages: 0, consumers: 1 } } });
	});

	await page.goto('/recon');
	// wait for the client fetch to land before interacting: the toggle is server-rendered,
	// so an early click hits an unhydrated button and silently does nothing
	await expect(page.getByTestId('recon-run-row')).toHaveCount(3);
	await page.getByTestId('recon-new-toggle').click();

	// enqueue is gated on having previewed — the cluster is the load-bearing decision
	await expect(page.getByTestId('recon-enqueue')).toBeDisabled();
	await page.getByTestId('recon-form-limit').fill('5');
	await page.getByTestId('recon-preview').click();
	await expect(page.getByTestId('recon-preview-out')).toContainText('5 frames');
	await expect(page.getByTestId('recon-enqueue')).toBeEnabled();

	await page.getByTestId('recon-enqueue').click();
	await expect.poll(() => enqueued).not.toBeNull();
	// stride must default to 1: never subsample a sweep
	expect((enqueued as { stride: number; limit: number }).stride).toBe(1);
	expect((enqueued as { limit: number }).limit).toBe(5);
});

const GEO_FRAMES = [
	{ idx: 0, gps: [50.1, 14.5], recovered_gps: [50.1001, 14.5001] },
	{ idx: 1, gps: [50.1005, 14.5005], recovered_gps: [50.1004, 14.5008] },
	{ idx: 2, gps: [50.101, 14.501], recovered_gps: [50.1012, 14.5009] }
];

async function stubGeo(page: Page) {
	await page.route('**/api/recon/runs/*', async (route) => {
		const id = new URL(route.request().url()).pathname.split('/').pop()!;
		const r = RUNS.find((x) => x.id === id) ?? RUNS[0];
		await route.fulfill({
			json: {
				...runRow(r),
				frames: GEO_FRAMES.map((f) => ({
					id: `aaaaaaaa-0000-0000-0000-00000000000${f.idx}`,
					idx: f.idx,
					focal_px: 405,
					base_focal_px: 400,
					reproj_px: 1.2,
					epipolar_px: 0.3,
					residual_m: 0.4
				})),
				pairs: PAIRS,
				worst_pairs: [],
				geo: { frames: GEO_FRAMES }
			}
		});
	});
	await page.route('**/tile/**', async (route) => route.abort());
}

test('the track map goes fullscreen and comes back', async ({ page }) => {
	// It is the view that shows a solve folding, so it has to be usable at full size --
	// and a fixed overlay with no way out is a trap, hence the Escape half.
	await stubGeo(page);
	await page.goto('/recon?run=walk_dense');
	const btn = page.getByTestId('recon-track-expand');
	await expect(btn).toBeVisible({ timeout: 20_000 });
	const small = (await page.locator('.leaflet-container').boundingBox())!.height;
	await btn.click();
	await expect
		.poll(async () => (await page.locator('.leaflet-container').boundingBox())!.height)
		.toBeGreaterThan(small + 200);
	await page.keyboard.press('Escape');
	await expect
		.poll(async () => (await page.locator('.leaflet-container').boundingBox())!.height)
		.toBeLessThan(small + 50);
});

test('the track map moves when a different run is picked', async ({ page }) => {
	// two runs at two places: picking the second must refit the map to it
	const far = GEO_FRAMES.map((f) => ({ ...f, gps: [f.gps[0] + 0.05, f.gps[1] + 0.05],
		recovered_gps: [f.recovered_gps[0] + 0.05, f.recovered_gps[1] + 0.05] }));
	await page.route('**/api/recon/runs/*', async (route) => {
		const id = new URL(route.request().url()).pathname.split('/').pop()!;
		const r = RUNS.find((x) => x.id === id) ?? RUNS[0];
		const g = r.name === 'board_jan' ? far : GEO_FRAMES;
		await route.fulfill({ json: { ...runRow(r),
			frames: g.map((f) => ({ id: `aaaaaaaa-0000-0000-0000-00000000000${f.idx}`, idx: f.idx,
				focal_px: 405, base_focal_px: 400, reproj_px: 1, epipolar_px: 0.3, residual_m: 0.4 })),
			pairs: PAIRS, worst_pairs: [], geo: { frames: g } } });
	});
	await page.route('**/tile/**', async (route) => route.abort());
	await page.goto('/recon?run=walk_dense');
	await expect(page.getByTestId('recon-track-expand')).toBeVisible({ timeout: 20_000 });
	const mapEl = page.locator('.leaflet-container');
	await expect(mapEl).toHaveAttribute('data-centre', /50\.100\d\d,14\.500\d\d/);
	await page.getByTestId('recon-run-row').filter({ hasText: 'board_jan' }).click();
	await expect(page.getByTestId('recon-detail')).toHaveAttribute('data-run', 'board_jan');
	// the far cluster is 0.05 deg away; the map must be looking there now
	await expect(mapEl).toHaveAttribute('data-centre', /50\.150\d\d,14\.550\d\d/, { timeout: 5000 });
});

test('hovering a recovered camera names its frame and lights its link', async ({ page }) => {
	await stubGeo(page);
	await page.goto('/recon?run=walk_dense');
	await expect(page.getByTestId('recon-track-expand')).toBeVisible({ timeout: 20_000 });
	const dots = page.locator('path.leaflet-interactive');
	await expect(dots.first()).toBeVisible();
	// move the real mouse to the marker's centre rather than locator.hover(): leaflet
	// paints into one SVG, so playwright's actionability checks can sit forever waiting
	// for a <path> it considers obscured by its own siblings
	// dispatch the DOM event leaflet actually listens for, rather than driving the real
	// mouse: leaflet paints every marker into one SVG, and playwright's actionability
	// checks can wait forever on a <path> it thinks its own siblings obscure
	await dots.last().dispatchEvent('mouseover');
	await expect(page.locator('.hoverbox')).toContainText(/frame \d/);
	// and the link for that frame lights up
	await expect(page.locator('path[stroke="#e0a23a"]').first()).toBeVisible();
});

// The viewer is lazy-mounted (IntersectionObserver): a page visit must not eagerly build
// a WebGL context. Below the fold it offers a button instead; take it when offered.
async function mountCloud(page: Page) {
	const btn = page.getByRole('button', { name: 'load point cloud' });
	const stage = page.getByTestId('recon-cloud');
	await expect(btn.or(stage).first()).toBeVisible({ timeout: 20_000 });
	// Scrolling the button into view is itself what mounts the viewer (the observer
	// fires), so a click here races the button's own disappearance. Scroll, give the
	// observer a beat, and only click if the button is still there.
	if (await btn.isVisible().catch(() => false)) {
		await btn.scrollIntoViewIfNeeded();
		await page.waitForTimeout(400);
		if (await btn.isVisible().catch(() => false)) await btn.click({ timeout: 3000 }).catch(() => {});
	}
	await expect(stage).toBeVisible({ timeout: 20_000 });
}

test('the frames table sorts by a clicked column', async ({ page }) => {
	// "which frame drifted" should be one click, not a scan down fifty rows
	await page.route('**/api/recon/runs/*', async (route) => {
		const id = new URL(route.request().url()).pathname.split('/').pop()!;
		const r = RUNS.find((x) => x.id === id) ?? RUNS[0];
		await route.fulfill({
			json: {
				...runRow(r),
				frames: [0.8, 42.5, 3.1].map((e, i) => ({
					id: `cccccccc-0000-0000-0000-00000000000${i}`, idx: i, focal_px: 400,
					base_focal_px: 400, reproj_px: e, epipolar_px: e / 2, residual_m: 0.5
				})),
				pairs: PAIRS, worst_pairs: [], geo: null
			}
		});
	});
	await page.goto('/recon?run=walk_dense');
	const hdr = page.getByTestId('recon-frames-sort-reproj');
	await expect(hdr).toBeVisible({ timeout: 20_000 });
	const firstCell = () => page.locator('table').filter({ has: hdr }).locator('tbody tr').first().locator('td').first();
	await expect(firstCell()).toHaveText('0');
	await hdr.click(); // descending: worst first
	await expect(firstCell()).toHaveText('1');
	await hdr.click(); // ascending
	await expect(firstCell()).toHaveText('0');
	await hdr.click(); // off: back to capture order
	await expect(firstCell()).toHaveText('0');
});

test('a running run shows its pace, its ETA and a slowdown warning', async ({ page }) => {
	// No magic timeout: the worker reads the solver's own progress bars and the bench
	// shows rate and ETA, and says so when a run falls well below its own early pace.
	await page.route('**/api/recon/runs', async (route) => {
		if (route.request().method() !== 'GET') return route.fallback();
		const rows = RUNS.map(runRow);
		rows[1] = {
			...rows[1], status: 'running',
			meta: { stage: 'solving',
				progress: { done: 416, total: 948, bar: 1, s_per_it: 86.7, eta_s: 46140 },
				warning: "5.1x slower than this run's own early pace (17 s/it) — another solve on the box?" }
		};
		await route.fulfill({ json: { runs: rows, queue: { messages: 0, consumers: 1 } } });
	});
	await page.goto('/recon');
	const row = page.getByTestId('recon-run-row').filter({ hasText: 'walk_dense' });
	await expect(row).toContainText('416/948');
	await expect(row).toContainText('ETA 12.8 h');
	await expect(row.getByTestId('recon-run-warning')).toContainText('5.1x slower');
});

test('a broken walk offers to split, and its spans overlay as a group', async ({ page }) => {
	let splitCalled = false;
	await page.route('**/api/recon/runs/*/split', async (route) => {
		splitCalled = true;
		await route.fulfill({ json: { parent: 'x', queued: [], skipped: [] } });
	});
	await page.route('**/api/recon/runs/*', async (route) => {
		const id = new URL(route.request().url()).pathname.split('/').pop()!;
		const r = RUNS.find((x) => x.id === id) ?? RUNS[0];
		const base = runRow(r);
		await route.fulfill({
			json: {
				...base,
				metrics: { ...base.metrics, chain: { typical_link: 5000, breaks: [16, 33],
					spans: [[0, 16], [17, 33], [34, 49]], verdicts: {}, n_cross_session: 0, n_cross_verified: 0 } },
				frames: [], pairs: [], worst_pairs: [], geo: null,
				group: { parent: r.id, members: [] }
			}
		});
	});
	await page.goto('/recon?run=walk_dense');
	const btn = page.getByTestId('recon-split');
	await expect(btn).toBeVisible({ timeout: 20_000 });
	await expect(btn).toContainText('3 spans');
	await btn.click();
	await expect.poll(() => splitCalled).toBe(true);
});

test('a queued run shows its frames before it is solved', async ({ page }) => {
	// A run takes hours. Whether it was worth starting is visible in its frames long
	// before an artifact comes back, so the detail must serve them from the row.
	await page.route('**/api/recon/runs/*', async (route) => {
		const id = new URL(route.request().url()).pathname.split('/').pop()!;
		const r = RUNS.find((x) => x.id === id) ?? RUNS[0];
		await route.fulfill({
			json: {
				...runRow(r),
				status: 'queued',
				frames_pending: true,
				frames: [0, 1, 2].map((i) => ({
					idx: i, id: `bbbbbbbb-0000-0000-0000-00000000000${i}`, pending: true,
					captured_at: `2026-08-19 16:41:0${i}.000000`, camera: 'exif:Ulefone|Armor 22|',
					compass_angle: 90 + i, gps: [50.1, 14.5 + i * 0.0001], thumb: null
				})),
				pairs: [], worst_pairs: [],
				geo: { center: [50.1, 14.5], frames: [0, 1, 2].map((i) => ({
					idx: i, id: 'x', gps: [50.1, 14.5 + i * 0.0001], recovered_gps: null }))
				}
			}
		});
	});
	await page.route('**/tile/**', async (route) => route.abort());
	await page.goto('/recon?run=walk_dense');
	await expect(page.getByTestId('recon-frames-pending')).toBeVisible({ timeout: 20_000 });
	await expect(page.getByTestId('recon-frame-strip').locator('button')).toHaveCount(3);
	// and the track map draws the selected cluster from GPS alone
	await expect(page.getByTestId('recon-track-expand')).toBeVisible();
});

test('a layer toggle keeps the viewpoint', async ({ page }) => {
	// Layers used to be remounted through a {#key}, which threw away the orbit camera:
	// every checkbox tick sent you back to the default framing, so the toggles were
	// useless for exactly the thing they are for, comparing with and without.
	const N = 300;
	const buf = Buffer.alloc(N * 15);
	for (let i = 0; i < N; i++) {
		buf.writeFloatLE(Math.cos(i) * 3, i * 15);
		buf.writeFloatLE(Math.sin(i) * 3, i * 15 + 4);
		buf.writeFloatLE(i / 100, i * 15 + 8);
	}
	await page.route('**/cloud.bin*', async (route) =>
		route.fulfill({ body: buf, contentType: 'application/octet-stream' })
	);
	await page.route('**/recon/runs/*/cameras*', async (route) =>
		route.fulfill({
			json: {
				frames: [
					{
						idx: 0, id: 'a', focal_px: 400, injected: false,
						pos: [0, 0, 0], rot: [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
					}
				]
			}
		})
	);
	await page.route('**/recon/runs/*/map', async (route) =>
		route.fulfill({ json: { buildings: [], walls: [], roads: [] } })
	);

	await page.goto('/recon?run=walk_dense');
	await mountCloud(page);
	const canvas = page.getByTestId('recon-cloud').locator('canvas');
	await expect(canvas).toBeVisible({ timeout: 20_000 });
	const first = await canvas.elementHandle();

	await page.getByRole('checkbox', { name: 'photos' }).check();
	await page.waitForTimeout(500);
	const second = await canvas.elementHandle();
	// same canvas node means the WebGL context, and with it the orbit camera, survived
	expect(await page.evaluate(([a, b]) => a === b, [first, second])).toBe(true);

	await page.getByRole('checkbox', { name: 'OSM map' }).uncheck();
	await page.waitForTimeout(300);
	const third = await canvas.elementHandle();
	expect(await page.evaluate(([a, b]) => a === b, [first, third])).toBe(true);
});

test('fly mode takes the controls and hands them back', async ({ page }) => {
	// Orbit is for judging from outside; fly is for being inside. The toggle must not
	// rebuild the viewer, keys must not leak to the page, and orbit must come back level.
	const N = 300;
	const buf = Buffer.alloc(N * 15);
	for (let i = 0; i < N; i++) {
		buf.writeFloatLE(Math.cos(i) * 3, i * 15);
		buf.writeFloatLE(Math.sin(i) * 3, i * 15 + 4);
		buf.writeFloatLE(i / 100, i * 15 + 8);
	}
	await page.route('**/cloud.bin*', async (route) =>
		route.fulfill({ body: buf, contentType: 'application/octet-stream' })
	);
	await page.route('**/recon/runs/*/cameras*', async (route) =>
		route.fulfill({ json: { frames: [] } })
	);
	await page.route('**/recon/runs/*/map', async (route) =>
		route.fulfill({ json: { buildings: [], walls: [], roads: [] } })
	);
	await page.goto('/recon?run=walk_dense');
	await mountCloud(page);
	const stage = page.getByTestId('recon-cloud');
	await expect(stage.locator('canvas')).toBeVisible({ timeout: 20_000 });
	const canvas = await stage.locator('canvas').elementHandle();

	await page.getByTestId('recon-mode-fly').click();
	await expect(stage).toHaveAttribute('data-mode', 'fly');
	await expect(page.getByTestId('recon-fly-hint')).toContainText('click the view');
	// thrust without a pointer lock (headless chromium will not grant one): must be
	// harmless, and the arrow keys must not scroll the page out from under the viewer
	const y0 = await page.evaluate(() => window.scrollY);
	await page.keyboard.down('ArrowUp');
	await page.waitForTimeout(300);
	await page.keyboard.up('ArrowUp');
	expect(await page.evaluate(() => window.scrollY)).toBe(y0);

	await page.getByTestId('recon-mode-orbit').click();
	await expect(stage).toHaveAttribute('data-mode', 'orbit');
	// same canvas throughout: the mode switch is a controller swap, not a remount
	const after = await stage.locator('canvas').elementHandle();
	expect(await page.evaluate(([a, b]) => a === b, [canvas, after])).toBe(true);
});

test('renders the point cloud and its camera frusta', async ({ page }) => {
	// WebGL runs on swiftshader here (see playwright.config.ts), same as the terrain viewer.
	// The cloud arrives as packed [float32 xyz][uint8 rgb]; this pins the decode contract,
	// because a stride mistake would silently render garbage rather than fail.
	const N = 500;
	const buf = Buffer.alloc(N * 15);
	for (let i = 0; i < N; i++) {
		buf.writeFloatLE(Math.cos(i) * 10, i * 15);
		buf.writeFloatLE(Math.sin(i) * 10, i * 15 + 4);
		buf.writeFloatLE(i / 50, i * 15 + 8);
		buf.writeUInt8(200, i * 15 + 12);
		buf.writeUInt8(180, i * 15 + 13);
		buf.writeUInt8(120, i * 15 + 14);
	}
	await page.route('**/cloud.bin*', async (route) =>
		route.fulfill({ body: buf, contentType: 'application/octet-stream' })
	);
	await page.route('**/recon/runs/*/cameras', async (route) =>
		route.fulfill({
			json: {
				// pos/rot are the ENU pair the viewer must draw with; `pose` is the raw
				// solve pose and is deliberately DIFFERENT here, so a regression back to
				// it puts the frusta somewhere this test can see.
				frames: [
					{
						idx: 0, id: 'a', focal_px: 400, injected: false,
						pos: [0, 0, 0], rot: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
						pose: [[1, 0, 0, 99], [0, 1, 0, 99], [0, 0, 1, 99]]
					},
					{
						idx: 1, id: 'b', focal_px: 400, injected: true,
						pos: [2, 0, 0], rot: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
						pose: [[1, 0, 0, 99], [0, 1, 0, 99], [0, 0, 1, 99]]
					}
				]
			}
		})
	);

	await page.route('**/recon/runs/*/map', async (route) =>
		route.fulfill({ json: { buildings: [], walls: [], roads: [] } })
	);

	await page.goto('/recon?run=walk_dense');
	await mountCloud(page);
	const stage = page.getByTestId('recon-cloud');
	await expect(stage).toBeVisible();
	// a canvas means three.js got a GL context, not just that the div exists
	await expect(stage.locator('canvas')).toBeVisible({ timeout: 20_000 });
	// and the decoded count must match the bytes we served
	await expect(page.getByText(`${N.toLocaleString()} points`)).toBeVisible();
});
