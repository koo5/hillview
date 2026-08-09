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
				frames: [
					{ idx: 0, id: 'a', pose: [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]], focal_px: 400, injected: false },
					{ idx: 1, id: 'b', pose: [[1, 0, 0, 2], [0, 1, 0, 0], [0, 0, 1, 0]], focal_px: 400, injected: true }
				]
			}
		})
	);

	await page.goto('/recon?run=walk_dense');
	const stage = page.getByTestId('recon-cloud');
	await expect(stage).toBeVisible();
	// a canvas means three.js got a GL context, not just that the div exists
	await expect(stage.locator('canvas')).toBeVisible({ timeout: 20_000 });
	// and the decoded count must match the bytes we served
	await expect(page.getByText(`${N.toLocaleString()} points`)).toBeVisible();
});
