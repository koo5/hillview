<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api';
	import { apiBase } from '$lib/config';
	import Help from '$lib/components/Help.svelte';
	import ReconPairSpread from '$lib/components/ReconPairSpread.svelte';
	import ReconTrackMap from '$lib/components/ReconTrackMap.svelte';
	import ReconCloudViewer from '$lib/components/ReconCloudViewer.svelte';

	type Stat = { n: number; median: number; mean: number; rms: number; p90: number; max: number };
	type Impostor = {
		idx: number;
		id: string | null;
		n_corres_to_cluster: number;
		reproj_px?: Stat | null;
		epipolar_px?: Stat | null;
		gps_residual_m?: number | null;
		reproj_ratio_vs_real?: number;
		epipolar_ratio_vs_real?: number;
		verdict: 'rejected' | 'registered' | 'no-matches' | 'ambiguous';
	};
	type Metrics = {
		reproj_px?: Stat | null;
		epipolar_px?: Stat | null;
		reproj_coverage?: number | null;
		n_behind_camera?: number | null;
		gps_residual_m?: { med_resid: number; mean_resid: number; max_resid: number } | null;
		ground_split?: {
			camera_height_m: number | null;
			camera_height_sd_m?: number;
			stationary?: boolean;
			neighbour_step_cm?: { median: number; p90: number; max: number; n: number } | null;
			error?: string;
		} | null;
		chain?: {
			typical_link: number;
			breaks: number[];
			spans: [number, number][];
			verdicts: Record<string, number>;
			n_cross_session: number;
			n_cross_verified: number;
			error?: string;
		} | null;
		gps_residual_informative?: boolean;
		pp_source?: string;
		pose_source?: string;
		reproduced_archived_solve?: boolean;
		n_degenerate_baseline_pairs?: number;
		loaded_size?: { h: number; w: number } | null;
		n_injected?: number;
		real_only_reproj_px?: Stat | null;
		real_only_epipolar_px?: Stat | null;
		impostors?: Impostor[];
		depth_horizon?: {
			units: string;
			baseline_max: number;
			horizon_20pct: number;
			median_focal_px: number;
			depth_p50?: number;
			depth_p90?: number;
			depth_max?: number;
			frac_beyond_horizon?: number;
			over_reported?: boolean;
		} | null;
	};
	type Run = {
		enqueued_at?: string | null;
		id: string;
		name: string;
		source: string;
		status: string;
		error?: string | null;
		n_frames: number | null;
		n_pairs: number | null;
		captured_on: string | null;
		params: Record<string, unknown>;
		metrics: Metrics | null;
		meta?: { stage?: string; rundir?: string; elapsed_s?: number; warning?: string | null; progress?: { done: number; total: number; bar?: number; s_per_it?: number | null; eta_s?: number | null } | null; [k: string]: unknown } | null;
		has_cloud: boolean;
		has_dense_cloud?: boolean;
		has_topdown: boolean;
		has_pairs_matrix: boolean;
	};
	type Pair = {
		i: number;
		j: number;
		n_corres: number;
		baseline_m?: number | null;
		degenerate_baseline?: boolean;
		reproj?: Stat | null;
		epipolar?: Stat | null;
	};
	type Frame = {
		idx: number;
		thumb?: string | null;
		pending?: boolean;
		captured_at?: string | null;
		camera?: string | null;
		compass_angle?: number | null;
		id: string;
		focal_px: number;
		base_focal_px: number;
		residual_m: number | null;
		epipolar_px: number | null;
		reproj_px: number | null;
		injected?: boolean;
	};
	type Detail = Run & {
		frames_pending?: boolean;
		frames: Frame[];
		pairs: Pair[];
		worst_pairs: { i: number; j: number; metric: string; median_px: number; n_corres: number }[];
		geo: {
			center: [number, number];
			frames: {
				idx: number;
				gps: [number, number] | null;
				recovered_gps: [number, number] | null;
				captured_at: string | null;
			}[];
		} | null;
		artifact_error?: string;
	};

	type Queue = { messages: number; consumers: number } | null;

	let runs = $state<Run[]>([]);
	let queue = $state<Queue>(null);
	let detail = $state<Detail | null>(null);
	let err = $state<string | null>(null);
	let loading = $state(false);
	let metric = $state<'reproj' | 'epipolar'>('reproj');
	let selPair = $state<string | null>(null);
	let selFrame = $state<number | null>(null);
	// dense by default where it exists: the sparse cloud is anchor points only and reads as
	// spray, which is what made these clouds look nonsensical
	let showDense = $state(true);
	// Frames table sort: click a header to cycle asc / desc / off. "Which frame drifted"
	// is a scan down the reprojection column otherwise, and fifty rows is a long scan.
	type FrameKey = 'idx' | 'reproj_px' | 'epipolar_px' | 'residual_m' | 'focal_px' | 'captured_at';
	let frameSort = $state<{ key: FrameKey; dir: 1 | -1 } | null>(null);
	function cycleFrameSort(key: FrameKey) {
		if (!frameSort || frameSort.key !== key) frameSort = { key, dir: -1 };
		else if (frameSort.dir === -1) frameSort = { key, dir: 1 };
		else frameSort = null;
	}
	function sortArrow(key: FrameKey) {
		return frameSort?.key === key ? (frameSort.dir === -1 ? ' ▼' : ' ▲') : '';
	}
	const sortedFrames = $derived.by(() => {
		const fs = detail?.frames ?? [];
		if (!frameSort) return fs;
		const { key, dir } = frameSort;
		return [...fs].sort((a, b) => {
			const va = (a as Record<string, unknown>)[key];
			const vb = (b as Record<string, unknown>)[key];
			if (va == null && vb == null) return 0;
			if (va == null) return 1; // nulls last either way
			if (vb == null) return -1;
			return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
		});
	});
	let showMap = $state(true);
	let showPhotos = $state(false);
	// …but do NOT mount the viewer until it is actually on screen. A dense cloud is
	// hundreds of thousands of points and a WebGL context; eagerly loading one per run
	// visit made the page heavy enough to crash a headless tab.
	let cloudVisible = $state(false);
	function watchCloud(node: HTMLElement) {
		const io = new IntersectionObserver(
			(entries) => {
				if (entries.some((e) => e.isIntersecting)) {
					cloudVisible = true;
					io.disconnect();
				}
			},
			{ rootMargin: '200px' }
		);
		io.observe(node);
		return { destroy: () => io.disconnect() };
	}

	// --- new run ---------------------------------------------------------------
	// Defaults are the Prosek walk centre — the site every experiment so far used.
	let showNew = $state(false);
	let busy = $state(false);
	let form = $state({
		name: '',
		lat: 50.1172,
		lon: 14.4893,
		radius_m: 300,
		limit: 8,
		offset: 0,
		stride: 1,
		after: '',
		before: '',
		inject: '',
		dense: true,
		win: 4,
		mask_anon: true,
		mask_solocator: false,
		// ON by default for single-camera clusters, where it is physically true. Its A/B raised
		// the median (11.0 -> 14.7 px) and lowered p90 (228 -> 179), which is not a regression:
		// a per-frame focal is a free parameter the optimizer uses to ABSORB error, so a low
		// reprojection bought with a 119-degree fisheye on a phone is overfitting, not accuracy.
		// Constrain the lens to what the hardware actually is and the residual surfaces where it
		// belongs. (The preview warns if the selection turns out to be mixed-source.)
		shared_intrinsics: true
	});
	let previewed = $state<{
		n_frames: number;
		single_camera?: boolean;
		dimensions?: string[];
		frames: { id: string; captured_at: string }[];
	} | null>(null);

	function body() {
		return {
			name: form.name || null,
			lat: Number(form.lat),
			lon: Number(form.lon),
			radius_m: Number(form.radius_m),
			limit: Number(form.limit),
			offset: Number(form.offset),
			stride: Number(form.stride),
			after: form.after || null,
			before: form.before || null,
			inject: form.inject
				.split(/[\s,]+/)
				.map((s) => s.trim())
				.filter(Boolean),
			params: {
				dense: form.dense,
				win: Number(form.win),
				mask_anon: form.mask_anon,
				mask_solocator: form.mask_solocator,
				shared_intrinsics: form.shared_intrinsics
			}
		};
	}

	async function preview() {
		busy = true;
		err = null;
		try {
			previewed = await api.post('/recon/preview', body());
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
			previewed = null;
		} finally {
			busy = false;
		}
	}

	async function enqueue() {
		busy = true;
		err = null;
		try {
			const r = await api.post<{ queued: string; name: string }>('/recon/runs', body());
			previewed = null;
			await loadRuns();
			goto(`/recon?run=${encodeURIComponent(r.name)}`, { noScroll: true });
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			busy = false;
		}
	}

	// Most recent first by default: with a queue of multi-hour jobs, the question the
	// list answers most often is "what did I just start, and how is it doing". The
	// structure ranking — the ordering that deliberately differs from the GPS one — is a
	// toggle away, and the tests pin it.
	let sortBy = $state<'recent' | 'structure'>('recent');
	const sorted = $derived(
		sortBy === 'structure'
			? [...runs].sort((a, b) => (rp(a) ?? Infinity) - (rp(b) ?? Infinity))
			: [...runs].sort((a, b) => (b.enqueued_at ?? '').localeCompare(a.enqueued_at ?? ''))
	);
	function rp(r: Run): number | null {
		return r.metrics?.reproj_px?.median ?? null;
	}
	function ep(r: Run): number | null {
		return r.metrics?.epipolar_px?.median ?? null;
	}
	function fmtEta(sec: number): string {
		if (sec < 90) return `${Math.round(sec)} s`;
		if (sec < 5400) return `${Math.round(sec / 60)} min`;
		return `${(sec / 3600).toFixed(1)} h`;
	}
	function fmtPx(v: number | null | undefined): string {
		if (v == null) return '—';
		return v < 10 ? v.toFixed(2) : v < 1000 ? v.toFixed(1) : Math.round(v).toLocaleString();
	}

	async function loadRuns() {
		try {
			const d = await api.get<{ runs: Run[]; queue: Queue }>('/recon/runs');
			runs = d.runs;
			queue = d.queue;
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		}
	}

	async function loadDetail(id: string) {
		loading = true;
		try {
			detail = await api.get<Detail>(`/recon/runs/${id}`);
			selPair = null;
			selFrame = null;
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
			detail = null;
		} finally {
			loading = false;
		}
	}

	function select(r: Run) {
		goto(`/recon?run=${encodeURIComponent(r.name)}`, { noScroll: true, keepFocus: true });
	}

	// URL is the state: ?run=<name> deep-links a run (shareable next to the field notes)
	$effect(() => {
		const want = page.url.searchParams.get('run');
		if (!runs.length) return;
		const r = runs.find((x) => x.name === want) ?? sorted[0];
		if (r && detail?.name !== r.name && !loading) loadDetail(r.id);
	});

	$effect(() => {
		loadRuns();
	});

	// Poll only while something is actually in flight. A reconstruction runs for tens of
	// minutes, so 6 s is plenty to feel live without hammering the API; idle pages don't
	// poll at all.
	const active = $derived(runs.some((r) => r.status === 'queued' || r.status === 'running'));
	$effect(() => {
		if (!active) return;
		const t = setInterval(() => {
			loadRuns();
			if (detail && (detail.status === 'queued' || detail.status === 'running'))
				loadDetail(detail.id);
		}, 6000);
		return () => clearInterval(t);
	});

	const residualsByIdx = $derived(
		Object.fromEntries(
			(detail?.frames ?? []).map((f) => [
				f.idx,
				{ residual_m: f.residual_m, reproj_px: f.reproj_px }
			])
		)
	);
	const pairByKey = $derived(
		Object.fromEntries((detail?.pairs ?? []).map((p) => [`${p.i}-${p.j}`, p]))
	);
	// A pair built on a handful of correspondences will show a wild error whether or not
	// anything is wrong — it is noise, not a finding. Filtering by correspondence count is
	// what separates "this pair is thin" from "this pair is a false link": the latter is
	// confidently wrong over thousands of matches, and that is the one worth chasing.
	let minCorres = $state(0);
	const CORRES_STEPS = [0, 100, 1000];
	const shownPairs = $derived(
		selPair && pairByKey[selPair]
			? [pairByKey[selPair]]
			: [...(detail?.pairs ?? [])]
					.filter((p) => (metric === 'reproj' ? p.reproj : p.epipolar))
					.filter((p) => p.n_corres >= minCorres)
					.sort(
						(a, b) =>
							((metric === 'reproj' ? b.reproj : b.epipolar)?.median ?? 0) -
							((metric === 'reproj' ? a.reproj : a.epipolar)?.median ?? 0)
					)
					.slice(0, 12)
	);
	const hiddenThin = $derived(
		(detail?.pairs ?? []).filter(
			(p) => (metric === 'reproj' ? p.reproj : p.epipolar) && p.n_corres < minCorres
		).length
	);
	const tailRatio = $derived(
		detail?.metrics?.reproj_px
			? detail.metrics.reproj_px.p90 / detail.metrics.reproj_px.median
			: null
	);
</script>

<h1>
	Recon <Help>
		<h4>What this bench shows</h4>
		<p>
			MASt3R-SfM reconstructions of photo clusters, ranked by <b>structure</b>, not by drift. Runs
			here were imported from the archived <code>scripts/enrich/runs</code> experiments; running new
			ones from the bench is the next step.
		</p>
		<dl>
			<dt>reprojection error (px)</dt>
			<dd>
				The structure metric. A correspondence is unprojected through one frame's depth and
				projected into the other; the miss is measured in pixels of the 512-px frames the solver
				worked on. Tests depth and pose together.
			</dd>
			<dt>epipolar error (px)</dt>
			<dd>
				A cheap screen computed from poses alone — but <b>blind along its own epipolar lines</b>. A
				2° pose error worth 14 px of reprojection measured 0.10 px here. Low epipolar next to high
				reprojection means the depth is wrong, not the poses.
			</dd>
			<dt>GPS residual (m)</dt>
			<dd>
				The old number: camera centres vs the phone's GPS after one 7-DoF fit. It is a
				<b>drift gate, not a quality score</b> — across these runs it ranks them with a Spearman
				correlation of 0.07 against structure. It is shown to be disagreed with.
			</dd>
			<dt>tail (p90 ÷ median)</dt>
			<dd>
				The two failure modes. A broken solve is uniformly broken (ratio ≈ 1); a good solve is an
				excellent core wrapped in a warped minority (ratio 35–81 on the walks). You need both
				numbers.
			</dd>
			<dt>coverage</dt>
			<dd>
				Share of correspondences the reprojection metric could score. The rest had their depth
				cleaned away or landed behind the other camera — so <b>low coverage flatters a bad solve</b
				>, because those correspondences are excluded rather than penalized.
			</dd>
		</dl>
		<h4>Why per-pair</h4>
		<p>
			A run-level median averages away the thing you are hunting: a single false link between
			lookalike places folds two parts of the city together. The spread chart plots every image
			pair, so the tail is visible and clickable.
		</p>
		<p class="muted">Method and caveats: <code>docs/reconstruction-field-notes.md</code></p>
	</Help>
</h1>

{#if err}<p class="err">{err}</p>{/if}

<div class="bar">
	<button data-testid="recon-new-toggle" onclick={() => (showNew = !showNew)}>
		{showNew ? '× close' : '+ new run'}
	</button>
	{#if queue}
		{#if queue.consumers === 0}
			<span class="pill bad" data-testid="recon-queue" title="start it with enrich/recon/run_worker.sh"
				>no worker connected</span
			>
		{:else}
			<span class="pill" data-testid="recon-queue"
				>{queue.consumers} worker{queue.consumers === 1 ? '' : 's'}{#if queue.messages}
					· {queue.messages} queued{/if}</span
			>
		{/if}
	{:else}
		<span class="pill muted" data-testid="recon-queue" title="no broker configured, or the queue does not exist yet">queue unknown</span>
	{/if}
	{#if active}<span class="muted small">polling…</span>{/if}
</div>

{#if showNew}
	<div class="card newrun">
		<h3>New reconstruction</h3>
		<p class="muted small">
			The cluster is the decision that matters most — preview it before committing. Frames are
			ordered by capture time (index-based selection silently mixed months in the June
			experiments) and must overlap: <b>never subsample a sweep</b>, which is why stride defaults
			to 1. At ~14 m spacing the solve collapsed to 81 m of drift.
		</p>
		<div class="grid">
			<label>name <input placeholder="auto" data-testid="recon-form-name" bind:value={form.name} /></label>
			<label>lat <input data-testid="recon-form-lat" bind:value={form.lat} /></label>
			<label>lon <input data-testid="recon-form-lon" bind:value={form.lon} /></label>
			<label>radius m <input data-testid="recon-form-radius" bind:value={form.radius_m} /></label>
			<label>frames <input data-testid="recon-form-limit" bind:value={form.limit} /></label>
			<label>offset <input bind:value={form.offset} /></label>
			<label title="1 = every frame. Higher values are for reproducing the strided-collapse control, not for real runs.">
				stride <input data-testid="recon-form-stride" bind:value={form.stride} />
			</label>
			<label>window size <input bind:value={form.win} /></label>
			<label class="wide">after <input placeholder="YYYY-MM-DD HH:MM:SS" bind:value={form.after} /></label>
			<label class="wide">before <input placeholder="YYYY-MM-DD HH:MM:SS" bind:value={form.before} /></label>
			<label
				class="wide"
				title="Photo ids added to the cluster as impostors. They are excluded from the GPS alignment fit and scored separately, so the Doppelganger claim can be tested rather than argued."
			>
				inject (impostor photo ids)
				<input placeholder="uuid, uuid — the Doppelganger control" data-testid="recon-form-inject" bind:value={form.inject} />
			</label>
		</div>
		<div class="flags">
				<label
				title="Solve ONE focal for the whole cluster — physically correct when the frames come from one camera at one zoom, which the preview checks. Expect the median reprojection to RISE and p90 to fall: a free per-frame focal lets the optimizer absorb error into an impossible lens (one frame solved to a 119-degree fisheye on a phone), so removing it surfaces the real residual instead of hiding it."
			>
				<input type="checkbox" data-testid="recon-form-shared" bind:checked={form.shared_intrinsics} />
				shared intrinsics
			</label>
			<label><input type="checkbox" bind:checked={form.dense} /> dense (needed for the reprojection metric)</label>
			<label><input type="checkbox" bind:checked={form.mask_anon} /> mask anon boxes</label>
			<label><input type="checkbox" bind:checked={form.mask_solocator} /> mask Solocator overlay</label>
		</div>
		<div class="actions">
			<button data-testid="recon-preview" onclick={preview} disabled={busy}>preview selection</button>
			<button data-testid="recon-enqueue" onclick={enqueue} disabled={busy || !previewed}>
				enqueue{previewed ? ` ${previewed.n_frames} frames` : ''}
			</button>
			{#if busy}<span class="muted small">working…</span>{/if}
		</div>
		{#if previewed}
			<p class="small" data-testid="recon-preview-out">
				<b>{previewed.n_frames} frames</b>
				{#if previewed.frames.length}
					· {previewed.frames[0].captured_at.slice(0, 19)} → {previewed.frames[
						previewed.frames.length - 1
					].captured_at.slice(0, 19)}
				{/if}
				{#if previewed.n_frames < 2}<span class="err"> — need at least 2</span>{/if}
			</p>
			{#if previewed.single_camera === false && form.shared_intrinsics}
				<p class="small err" data-testid="recon-mixed-warning">
					Mixed sources ({previewed.dimensions?.join(', ')}) — one focal is not physically shared
					across these frames. Turn <b>shared intrinsics</b> off, or narrow the selection.
				</p>
			{:else if previewed.single_camera && !form.shared_intrinsics}
				<p class="small muted">
					Single camera ({previewed.dimensions?.join(', ')}) — the focal is physically constant
					here, so <b>shared intrinsics</b> is the correct setting and removes the focal-wander
					tail.
				</p>
			{/if}
		{/if}
	</div>
{/if}

<div class="cols">
	<div class="runlist card">
		<div class="seg listsort">
			<button class:on={sortBy === 'recent'} onclick={() => (sortBy = 'recent')}
				data-testid="recon-sort-recent">recent</button
			>
			<button class:on={sortBy === 'structure'} onclick={() => (sortBy = 'structure')}
				title="ranked by reprojection error, best first"
				data-testid="recon-sort-structure">structure</button
			>
		</div>
		<table>
			<thead>
				<tr><th>run</th><th class="num">frames</th><th class="num">reproj px</th></tr>
			</thead>
			<tbody>
				{#each sorted as r (r.id)}
					<tr
						data-testid="recon-run-row"
						data-run={r.name}
						class:sel={detail?.id === r.id}
						onclick={() => select(r)}
						title="{r.n_pairs} pairs · GPS residual {r.metrics?.gps_residual_m?.med_resid ?? '—'} m"
					>
						<td>
							<b>{r.name}</b>
							<span class="sub">
								{#if r.status !== 'done'}
									<span class="st" class:bad={r.status === 'error'}
										>{r.status}{#if r.status === 'running' && r.meta?.stage}
											· {r.meta.stage}{/if}{#if r.status === 'running' && r.meta?.progress?.total}
											· {r.meta.progress.done}/{r.meta.progress.total}{#if r.meta.progress.eta_s != null}
												· ETA {fmtEta(r.meta.progress.eta_s)}{/if}{/if}</span
									>
									{#if r.meta?.warning}
										<span class="st warn" title={r.meta.warning} data-testid="recon-run-warning"
											>⚠ {r.meta.warning}</span
										>
									{/if}
								{:else}
									{r.captured_on ?? ''}
								{/if}
							</span>
						</td>
						<td class="num">{r.n_frames ?? '—'}</td>
						<td class="num">{fmtPx(rp(r))}</td>
					</tr>
				{/each}
				{#if !runs.length}
					<tr><td colspan="3" class="muted">no runs imported yet</td></tr>
				{/if}
			</tbody>
		</table>
	</div>

	<div class="detail">
		{#if loading && !detail}
			<p class="muted">loading…</p>
		{:else if detail}
			{@const m = detail.metrics ?? {}}
			<div class="card head" data-testid="recon-detail" data-run={detail.name}>
				<div class="titlerow">
					<h2>{detail.name}</h2>
					<span class="pill">{detail.source}</span>
					{#if detail.status !== 'done'}
						<span class="pill" class:bad={detail.status === 'error'} data-testid="recon-status">
							{detail.status}{#if detail.status === 'running' && detail.meta?.stage}
								· {detail.meta.stage}{/if}{#if detail.meta?.elapsed_s}
								· {detail.meta.elapsed_s}s{/if}
						</span>
					{/if}
					{#if m.pp_source && m.pp_source !== 'scene.npz'}
						<span class="pill" title="principal points recovered by recon_resolve.py, since scene.npz predates saving them">
							intrinsics recovered
						</span>
					{/if}
					{#if m.reproduced_archived_solve === false}
						<span class="pill bad" title="the re-solve is genuinely a different reconstruction than the archived one">
							re-solve differs
						</span>
					{/if}
				</div>
				<div class="stats">
					<div class="stat" data-testid="recon-stat-reproj">
						<span class="lbl">reprojection</span>
						<span class="val">{fmtPx(m.reproj_px?.median)}<small>px</small></span>
						<span class="ctx">p90 {fmtPx(m.reproj_px?.p90)}{#if tailRatio} · tail ×{tailRatio.toFixed(0)}{/if}</span>
					</div>
					<div class="stat" data-testid="recon-stat-epipolar">
						<span class="lbl">epipolar</span>
						<span class="val">{fmtPx(m.epipolar_px?.median)}<small>px</small></span>
						<span class="ctx">screen only — blind along its lines</span>
					</div>
					<div class="stat" data-testid="recon-stat-gps">
						<span class="lbl">GPS residual</span>
						<span class="val">{m.gps_residual_m?.med_resid?.toFixed(1) ?? '—'}<small>m</small></span>
						<span class="ctx">
							{#if m.gps_residual_informative === false}
								too few cameras to mean anything
							{:else}
								drift gate, not quality
							{/if}
						</span>
					</div>
					{#if m.ground_split && !m.ground_split.error}
						<div class="stat" data-testid="recon-stat-ground"
							title="where two neighbouring frames see the same patch of ground, how far apart do they put it? A flat plaza solves to under a centimetre; a staircase of tiles reads as tens">
							<span class="lbl">ground agreement</span>
							<span class="val"
								>{m.ground_split.neighbour_step_cm?.median?.toFixed(1) ?? '—'}<small>cm</small></span
							>
							<span class="ctx">
								p90 {m.ground_split.neighbour_step_cm?.p90?.toFixed(0) ?? '—'} cm · camera
								{m.ground_split.camera_height_m?.toFixed(2) ?? '—'} m above its floor
							</span>
						</div>
					{/if}
					{#if m.chain && !m.chain.error}
						<div class="stat" data-testid="recon-stat-chain"
							title="consecutive frames judged on their own two-view geometry, independent of the solve; a break is a link an order of magnitude weaker than the run's typical one">
							<span class="lbl">chain</span>
							<span class="val">{m.chain.spans?.length ?? 1}<small>span{(m.chain.spans?.length ?? 1) === 1 ? '' : 's'}</small></span>
							<span class="ctx">
								{#if m.chain.breaks?.length}breaks after {m.chain.breaks.join(', ')}{:else}holds throughout{/if}
								{#if m.chain.n_cross_session}
									· {m.chain.n_cross_verified}/{m.chain.n_cross_session} cross-session links verified{/if}
							</span>
						</div>
					{/if}
					<div class="stat" data-testid="recon-stat-coverage">
						<span class="lbl">coverage</span>
						<span class="val"
							>{m.reproj_coverage != null ? (100 * m.reproj_coverage).toFixed(0) : '—'}<small
								>%</small
							></span
						>
						<span class="ctx">{(m.n_behind_camera ?? 0).toLocaleString()} behind a camera</span>
					</div>
				</div>
			</div>

			{#if m.depth_horizon}
				{@const dh = m.depth_horizon}
				<div class="card" data-testid="recon-horizon">
					<h3>Depth reach</h3>
					<p class="small">
						Baseline <b>{dh.baseline_max} {dh.units}</b> · honest to
						<b>~{dh.horizon_20pct} {dh.units}</b> (20% error) · this solve reports depth out to
						<b>{dh.depth_max} {dh.units}</b>
					</p>
					<p class="muted small">
						Triangulated depth error grows as z²/(f·B), so a cluster has a hard reach.
						{#if dh.over_reported}
							<span class="err"
								>{(100 * (dh.frac_beyond_horizon ?? 0)).toFixed(1)}% of the depth here is beyond
								what this baseline can constrain — that part is the monocular prior, not measured
								geometry.</span
							>
						{:else}
							Compare the horizon against how far away your <b>subject</b> is: a solve can sit
							honestly inside its own reach and still miss the scene entirely. A lookout pan
							stays within ~114 m while photographing landmarks kilometres away — for anything
							past a few hundred metres use the terrain bench (DEM) or triangulation across
							separated viewpoints, not SfM.
						{/if}
					</p>
				</div>
			{/if}

			{#if m.impostors?.length}
				<div class="card" data-testid="recon-impostors">
					<h3>Doppelganger control</h3>
					<p class="muted small">
						Injected frames are excluded from the GPS alignment fit, so they cannot drag it toward
						themselves, and are scored against the <b>real frames' own baseline</b> — reproj
						{fmtPx(m.real_only_reproj_px?.median)} px, epipolar
						{fmtPx(m.real_only_epipolar_px?.median)} px. The thesis is that a frame which fools
						pairwise matching cannot register into a globally consistent solve. A ratio near 1
						means it registered as well as a genuine frame, and the thesis failed for that case.
					</p>
					<div class="tblwrap">
						<table>
							<thead>
								<tr>
									<th class="num">#</th>
									<th>photo</th>
									<th>verdict</th>
									<th class="num">reproj px</th>
									<th class="num">× real</th>
									<th class="num">epipolar px</th>
									<th class="num">× real</th>
									<th class="num">corres to cluster</th>
									<th class="num">GPS resid m</th>
								</tr>
							</thead>
							<tbody>
								{#each m.impostors as imp (imp.idx)}
									<tr data-testid="recon-impostor-row">
										<td class="num">{imp.idx}</td>
										<td>{imp.id ? imp.id.slice(0, 8) : '—'}</td>
										<td>
											<span
												class="pill"
												class:ok={imp.verdict === 'rejected'}
												class:bad={imp.verdict === 'registered'}>{imp.verdict}</span
											>
										</td>
										<td class="num">{fmtPx(imp.reproj_px?.median)}</td>
										<td class="num">{imp.reproj_ratio_vs_real ?? '—'}</td>
										<td class="num">{fmtPx(imp.epipolar_px?.median)}</td>
										<td class="num">{imp.epipolar_ratio_vs_real ?? '—'}</td>
										<td class="num">{imp.n_corres_to_cluster.toLocaleString()}</td>
										<td class="num">{imp.gps_residual_m ?? '—'}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<p class="muted small">
						<b>rejected</b> = ≥5× the real baseline, global consistency threw it out.
						<b>registered</b> = ≤2×, it passed as genuine. <b>no-matches</b> = under 100
						correspondences, so it was never a test of anything — an impostor that produces no
						matches must not be counted as a pass.
					</p>
				</div>
			{/if}

			<div class="card">
				<div class="secthead">
					<h3>Per-pair spread</h3>
					<div class="controls">
						<div class="seg">
							<button class:on={metric === 'reproj'} onclick={() => (metric = 'reproj')}
								>reprojection</button
							>
							<button class:on={metric === 'epipolar'} onclick={() => (metric = 'epipolar')}
								>epipolar</button
							>
						</div>
						<div class="seg" title="a pair built on a few correspondences is wild whether or not anything is wrong — raise this to separate real false links from thin noise">
							<span class="seglbl">min corres</span>
							{#each CORRES_STEPS as c (c)}
								<button
									data-testid="recon-mincorres-{c}"
									class:on={minCorres === c}
									onclick={() => (minCorres = c)}
									>{c === 0 ? 'all' : c.toLocaleString()}</button
								>
							{/each}
						</div>
					</div>
				</div>
				<ReconPairSpread
					pairs={detail.pairs}
					{metric}
					selected={selPair}
					onselect={(k) => (selPair = k)}
				/>
				<table class="pairs">
					<thead>
						<tr>
							<th>pair</th>
							<th class="num">median px</th>
							<th class="num">p90</th>
							<th class="num">corres</th>
							<th class="num">baseline m</th>
						</tr>
					</thead>
					<tbody>
						{#each shownPairs as p (`${p.i}-${p.j}`)}
							{@const s = metric === 'reproj' ? p.reproj : p.epipolar}
							<tr
								data-testid="recon-pair-row"
								class:sel={selPair === `${p.i}-${p.j}`}
								onclick={() =>
									(selPair = selPair === `${p.i}-${p.j}` ? null : `${p.i}-${p.j}`)}
							>
								<td>{p.i} → {p.j}{#if p.degenerate_baseline}<span class="sub">zero baseline</span>{/if}</td>
								<td class="num">{fmtPx(s?.median)}</td>
								<td class="num">{fmtPx(s?.p90)}</td>
								<td class="num">{p.n_corres.toLocaleString()}</td>
								<td class="num">{p.baseline_m ?? '—'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
				<p class="muted small">
					{#if selPair}
						one pinned pair — click it again to see the worst 12
					{:else}
						worst 12 pairs by {metric === 'reproj' ? 'reprojection' : 'epipolar'} error{#if minCorres}, of
							those with ≥{minCorres.toLocaleString()} correspondences ({hiddenThin} thinner pairs
							hidden){/if}. Pairs are directional: reprojection uses the source frame's depth, so i→j
						and j→i differ legitimately. A pair that is confidently wrong over
						<em>thousands</em> of correspondences is the false-link signature; a wild error over a
						dozen is just a thin pair.
					{/if}
				</p>
			</div>

			{#if detail.geo?.frames?.length}
				<div class="card">
					<h3>Recovered track vs GPS</h3>
					<p class="muted small">
						Grey = the phone's GPS, blue = recovered cameras after the Umeyama fit, thin
						connectors are the residual. Click a camera to select its frame.
					</p>
					<ReconTrackMap
						frames={detail.geo.frames}
						residuals={residualsByIdx}
						selected={selFrame}
						onselect={(i) => (selFrame = selFrame === i ? null : i)}
					/>
				</div>
			{/if}

			<div class="card">
				<div class="secthead">
					<h3>Frames</h3>
					{#if detail.frames_pending}
						<span class="st" data-testid="recon-frames-pending"
							>selected, not yet solved — judge the cluster here before the hours are spent</span
						>
					{/if}
				</div>
				<div class="strip" data-testid="recon-frame-strip">
					{#each detail.frames as f (f.idx)}
						<button
							class="thumbbtn"
							class:sel={selFrame === f.idx}
							title="frame {f.idx} · {f.captured_at ?? ''}"
							onclick={() => (selFrame = selFrame === f.idx ? null : f.idx)}
						>
							{#if f.thumb}
								<img src={f.thumb} alt="frame {f.idx}" loading="lazy" />
							{:else}
								<span class="muted small">{f.idx}</span>
							{/if}
							<span class="idx">{f.idx}</span>
						</button>
					{/each}
				</div>
				<div class="tblwrap">
					<table>
						<thead>
							<tr>
								<th class="num sortable" onclick={() => cycleFrameSort('idx')}>#{sortArrow('idx')}</th>
								<th>photo</th>
								{#if detail.frames_pending}
									<th class="sortable" onclick={() => cycleFrameSort('captured_at')}
										>captured{sortArrow('captured_at')}</th
									>
									<th>camera</th>
									<th class="num">compass</th>
								{:else}
									<th class="num sortable" onclick={() => cycleFrameSort('reproj_px')}
										data-testid="recon-frames-sort-reproj">reproj px{sortArrow('reproj_px')}</th
									>
									<th class="num sortable" onclick={() => cycleFrameSort('epipolar_px')}
										>epipolar px{sortArrow('epipolar_px')}</th
									>
									<th class="num sortable" onclick={() => cycleFrameSort('residual_m')}
										>GPS resid m{sortArrow('residual_m')}</th
									>
									<th class="num sortable" onclick={() => cycleFrameSort('focal_px')}
										>focal px{sortArrow('focal_px')}</th
									>
								{/if}
							</tr>
						</thead>
						<tbody>
							{#each sortedFrames as f (f.idx)}
								<tr
									class:sel={selFrame === f.idx}
									onclick={() => (selFrame = selFrame === f.idx ? null : f.idx)}
								>
									<td class="num">{f.idx}</td>
									<td>
										<a href="/photos/{f.id}" title="open the photo record">{f.id.slice(0, 8)}</a>
										{#if f.injected}<span class="st" title="injected impostor — excluded from the GPS alignment fit"
												>impostor</span
											>{/if}
									</td>
									{#if detail.frames_pending}
										<td>{f.captured_at?.slice(0, 19) ?? '—'}</td>
										<td class="small">{f.camera ?? '—'}</td>
										<td class="num">{f.compass_angle?.toFixed(0) ?? '—'}°</td>
									{:else}
										<td class="num">{fmtPx(f.reproj_px)}</td>
										<td class="num">{fmtPx(f.epipolar_px)}</td>
										<td class="num">{f.residual_m ?? '—'}</td>
										<td class="num">{f.focal_px?.toFixed(0) ?? '—'}</td>
									{/if}
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>

			{#if detail.has_cloud}
				<div class="card">
					<div class="secthead">
						<h3>Point cloud</h3>
						<div class="seg">
							<button class:on={!showDense} onclick={() => (showDense = false)}>sparse</button>
							<button
								class:on={showDense && !!detail.has_dense_cloud}
								disabled={!detail.has_dense_cloud}
								title={detail.has_dense_cloud
									? 'per-pixel depth — the readable one'
									: 'this run was solved without --dense'}
								onclick={() => (showDense = true)}>dense</button
							>
						</div>
						<label class="mapchk">
							<input type="checkbox" bind:checked={showMap} /> OSM map
						</label>
						<label class="mapchk" title="hang each photograph in its own frustum, at the pose the solve gave it">
							<input type="checkbox" bind:checked={showPhotos} /> photos
						</label>
					</div>
					<div use:watchCloud>
						{#if cloudVisible}
							<!-- keyed on the run and on which cloud is served, because those change the data the
									viewer is built from. NOT on the layer toggles: those are handled in
									place so a checkbox never costs you your viewpoint. -->
								{#key `${detail.id}-${showDense && !!detail.has_dense_cloud}`}
								<ReconCloudViewer
									runId={detail.id}
									dense={showDense && !!detail.has_dense_cloud}
									{showMap}
									{showPhotos}
								/>
							{/key}
						{:else}
							<button class="loadcloud" onclick={() => (cloudVisible = true)}
								>load point cloud</button
							>
						{/if}
					</div>
					<p class="muted small">
						In real-world metres, GPS-aligned: <b>Z is up, +Y is north</b>, grid squares are 5 m.
						Cameras are drawn as frusta from the solved poses — a collapsed run shows them piled
						together, and an injected impostor (amber) sits where the real ones do not.
						{#if !detail.has_dense_cloud}
							This run has no dense cloud; the sparse one is anchor points only and reads as
							spray.
						{/if}
					</p>
				</div>
			{/if}

			<div class="card">
				<h3>Artifacts</h3>
				<div class="arts">
					{#if detail.has_topdown}
						<figure>
							<img src="{apiBase}/recon/runs/{detail.id}/topdown" alt="top-down point cloud" />
							<figcaption class="muted small">top-down cloud + camera centres</figcaption>
						</figure>
					{/if}
					{#if detail.has_pairs_matrix}
						<figure>
							<img
								src="{apiBase}/recon/runs/{detail.id}/pairs_matrix"
								alt="pair correspondence-count matrix"
							/>
							<figcaption class="muted small">correspondence counts per pair</figcaption>
						</figure>
					{/if}
				</div>
				<p class="muted small">
					{#if detail.has_cloud}
						<a href="{apiBase}/recon/runs/{detail.id}/cloud">points.ply</a> —
					{/if}
					the forward-pass cache (1.8–2.7 GB per run) is deliberately not imported: it is
					regenerable and only needed to re-solve. A 3-D viewer is a later bite.
				</p>
			</div>
		{:else}
			<p class="muted">pick a run</p>
		{/if}
		{#if detail?.error}
			<div class="card">
				<h3>Error</h3>
				<pre class="errbox">{detail.error}</pre>
			</div>
		{/if}
	</div>
</div>

<style>
	.cols {
		display: flex;
		gap: 14px;
		align-items: flex-start;
	}
	.runlist {
		flex: 0 0 300px;
		order: 1;
		padding: 0;
		overflow: hidden;
	}
	.detail {
		flex: 1;
		min-width: 460px;
		order: 2;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.runlist tr {
		cursor: pointer;
	}
	.runlist tr.sel,
	tbody tr.sel {
		background: color-mix(in srgb, currentColor 8%, transparent);
	}
	.sub {
		display: block;
		font-size: 11px;
		opacity: 0.65;
	}
	.num {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	.titlerow {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-wrap: wrap;
	}
	h2 {
		margin: 0;
		font-size: 17px;
	}
	h3 {
		margin: 0 0 8px;
		font-size: 14px;
	}
	.head .stats {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 12px;
		margin-top: 12px;
	}
	.stat {
		display: flex;
		flex-direction: column;
		gap: 1px;
	}
	.stat .lbl {
		font-size: 11px;
		opacity: 0.7;
	}
	.stat .val {
		font-size: 24px;
		font-weight: 600;
	}
	.stat .val small {
		font-size: 13px;
		font-weight: 400;
		opacity: 0.7;
		margin-left: 2px;
	}
	.stat .ctx {
		font-size: 11px;
		opacity: 0.6;
	}
	.secthead {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 10px;
	}
	.controls {
		display: flex;
		gap: 12px;
		align-items: center;
		flex-wrap: wrap;
	}
	.seg {
		display: inline-flex;
		align-items: center;
		gap: 4px;
	}
	th.sortable {
		cursor: pointer;
		user-select: none;
		white-space: nowrap;
	}
	th.sortable:hover {
		text-decoration: underline;
	}
	.st.warn {
		color: #e0a23a;
		max-width: 26em;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		display: inline-block;
		vertical-align: bottom;
	}
	.listsort {
		padding: 6px 8px 2px;
	}
	.strip {
		display: flex;
		gap: 4px;
		overflow-x: auto;
		padding: 6px 2px 8px;
	}
	.thumbbtn {
		position: relative;
		flex: 0 0 auto;
		padding: 0;
		border: 2px solid transparent;
		border-radius: 5px;
		background: none;
		cursor: pointer;
		line-height: 0;
	}
	.thumbbtn img {
		height: 84px;
		width: auto;
		border-radius: 3px;
		display: block;
	}
	.thumbbtn.sel {
		border-color: #e0a23a;
	}
	.thumbbtn .idx {
		position: absolute;
		left: 3px;
		bottom: 3px;
		font-size: 10px;
		line-height: 1;
		padding: 1px 4px;
		border-radius: 3px;
		background: rgba(0, 0, 0, 0.6);
		color: #eee;
	}
	.mapchk {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-size: 12px;
		margin-left: 10px;
	}
	.seg button {
		font-size: 12px;
		padding: 2px 9px;
	}
	.seg button.on {
		font-weight: 700;
	}
	.seglbl {
		font-size: 11px;
		opacity: 0.6;
	}
	table.pairs {
		margin-top: 8px;
	}
	table.pairs tr {
		cursor: pointer;
	}
	.tblwrap {
		max-height: 340px;
		overflow: auto;
	}
	.tblwrap tr {
		cursor: pointer;
	}
	.small {
		font-size: 12px;
	}
	.arts {
		display: flex;
		gap: 12px;
		flex-wrap: wrap;
	}
	figure {
		margin: 0;
		flex: 1 1 300px;
	}
	figure img {
		width: 100%;
		border-radius: 6px;
	}
	.err {
		color: #e06c6c;
	}
	.loadcloud {
		width: 100%;
		height: 120px;
		font-size: 13px;
		opacity: 0.7;
	}
	.errbox {
		font-size: 12px;
		white-space: pre-wrap;
		overflow-x: auto;
		margin: 0;
		color: #e06c6c;
	}
	.bar {
		display: flex;
		align-items: center;
		gap: 10px;
		margin-bottom: 12px;
	}
	.st {
		text-transform: uppercase;
		letter-spacing: 0.04em;
		font-size: 10px;
		opacity: 0.85;
	}
	.st.bad {
		color: #e06c6c;
		opacity: 1;
	}
	.newrun {
		margin-bottom: 14px;
	}
	.newrun .grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
		gap: 8px 12px;
		margin: 10px 0;
	}
	.newrun label {
		display: flex;
		flex-direction: column;
		gap: 2px;
		font-size: 11px;
		opacity: 0.8;
	}
	.newrun label.wide {
		grid-column: span 2;
	}
	.newrun input {
		font-size: 13px;
		width: 100%;
	}
	.newrun .flags {
		display: flex;
		gap: 16px;
		flex-wrap: wrap;
		font-size: 12px;
	}
	.newrun .flags label {
		flex-direction: row;
		align-items: center;
		gap: 5px;
		font-size: 12px;
		opacity: 1;
	}
	.newrun .flags input {
		width: auto;
	}
	.newrun .actions {
		display: flex;
		align-items: center;
		gap: 10px;
		margin-top: 12px;
	}
	@media (max-width: 900px) {
		.cols {
			flex-direction: column;
		}
		.runlist {
			flex: 1 1 auto;
			width: 100%;
		}
		.detail {
			min-width: 0;
			width: 100%;
		}
		.head .stats {
			grid-template-columns: repeat(2, 1fr);
		}
	}
</style>
