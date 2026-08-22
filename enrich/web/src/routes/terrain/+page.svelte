<script lang="ts">
	// Terrain bench: view synthetic depth panoramas rendered from photo
	// viewpoints. The viewer — WebGL fog, zoom/pan/pinch, click-back geodesy,
	// peak labels — is the SHARED $terrain/TerrainViewer.svelte, the exact
	// component the main app's TerrainPane mounts. This page is just the
	// bench chrome, laid out viewer-first: a full-bleed stage with a
	// translucent toolbar + corner chips OVERLAYED on the canvas (they steal
	// no height), and a compact sidebar (enqueue / search / list) that the
	// fullscreen toggle collapses.
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api';
	import { apiBase } from '$lib/config';
	import TerrainViewer from '$terrain/TerrainViewer.svelte';
	import type { PeakExplanation, PeakMark, PeakVerdict } from '$terrain/peakLabels';
	import Help from '$lib/components/Help.svelte';
	import type { DepthPanoViewer, TerrainMeta, TerrainPick } from '$terrain/depthPanoViewer';
	import type { Peak } from '$terrain/peakLabels';

	interface RenderRow {
		id: string;
		photo_id: string | null;
		photo_title: string | null;
		lat: number;
		lon: number;
		status: string;
		error: string | null;
		meta:
			| (TerrainMeta & {
					attribution?: string;
					max_distance_m?: number;
					eye_elevation_m?: number;
					eye_source?: string;
					ground_m?: number;
					progress_pct?: number;
					stage?: string | null;
			  })
			| null;
		has_depth: boolean;
		has_preview: boolean;
		enqueued_at: string;
	}

	let renders = $state<RenderRow[]>([]);
	let sel = $state<RenderRow | null>(null);
	let err = $state<string | null>(null);
	let busy = $state(false);

	// enqueue form
	let photoId = $state('');
	let adhocLat = $state('');
	let adhocLon = $state('');
	// render params (parity with the main app's create row): defaults send
	// no param at all, so worker defaults stay the single source of truth
	let dsmStack = $state<'auto' | 'glo30' | 'cuzk'>('auto');
	let stepDeg = $state(0.025); // worker default (2x the renderer's 0.05)
	let eyeHeight = $state(2);
	// renderer default 100 km; uint16 depth at 4 m steps caps out at 262 km.
	// Beyond ~100 km also mind DEM coverage: the auto GLO-30 bbox is CZ +
	// margin (TERRAIN_AUTO_DEM_BBOX) — terrain outside it renders as sky.
	let maxKm = $state(100);
	// 0.005° is sector-only (full 360° at ×10 = 72k columns, beyond GPU
	// texture limits); rendered ±18° around this center azimuth
	let sectorAz = $state(0);

	function renderParams(): Record<string, unknown> {
		const p: Record<string, unknown> = {};
		if (dsmStack !== 'auto') p.dsm_stack = dsmStack;
		if (stepDeg <= 0.005) {
			// sector rungs: constant 7200-column artifact over a narrower slice
			const half = stepDeg === 0.005 ? 18 : 9;
			p.az_step_deg = stepDeg;
			p.elev_step_deg = stepDeg;
			p.az_start = sectorAz - half;
			p.az_end = sectorAz + half;
		} else if (stepDeg !== 0.025) {
			p.az_step_deg = stepDeg;
			p.elev_step_deg = stepDeg;
		}
		if (eyeHeight !== 2 && Number.isFinite(eyeHeight)) p.observer_height_m = eyeHeight;
		if (maxKm !== 100 && Number.isFinite(maxKm))
			p.max_distance_m = Math.round(Math.min(260, Math.max(1, maxKm)) * 1000);
		return p;
	}

	// viewer controls (parity with the main app's TerrainPane statusbar)
	let visibilityKm = $state(80); // meteorological visibility

	// ---- label pool listing: every candidate with its verdict + reason, and
	// whether its slat is on screen right now (why a name makes it or doesn't)
	let viewerRef = $state<TerrainViewer | null>(null);
	let poolOpen = $state(false);
	let poolFilter = $state('');
	let poolRows = $state<(PeakExplanation & { kept: boolean })[]>([]);
	let placedKeys = $state<Set<string>>(new Set());
	const markKey = (m: { name: string; azimuth_deg: number }) => `${m.name}@${m.azimuth_deg.toFixed(3)}`;
	function refreshPool(): void {
		poolRows = poolOpen && viewerRef ? viewerRef.explainPool() : [];
	}
	// re-list when the inputs the labels are drawn from change
	$effect(() => {
		void sel; void peaks; void showPlaces; void peakTolerance; void poolOpen;
		refreshPool();
	});
	const VERDICT_LABEL: Record<PeakVerdict, string> = {
		summit: 'summit', mass: 'mass', direction: 'direction', hidden: 'hidden',
		'not-notable': 'hidden · not notable', 'too-close': 'too close',
		'out-of-range': 'out of range', 'outside-sweep': 'outside sweep', 'no-terrain': 'no terrain'
	};
	const poolShown = $derived.by(() => {
		const q = poolFilter.trim().toLowerCase();
		const rows = q ? poolRows.filter((r) => r.peak.name.toLowerCase().includes(q)) : poolRows;
		return rows.slice(0, 400);
	});
	const poolCounts = $derived.by(() => {
		const c: Record<string, number> = {};
		for (const r of poolRows) {
			const k = r.mark && !r.kept ? 'shares pixel' : r.verdict;
			c[k] = (c[k] ?? 0) + 1;
		}
		return c;
	});
	function poolStatus(r: PeakExplanation & { kept: boolean }): string {
		if (!r.mark) return '';
		if (!r.kept) return 'pixel taken';
		if (r.distance_m > visibilityKm * 1000) return 'beyond fog';
		return placedKeys.has(markKey(r.mark)) ? 'on screen' : 'thinned';
	}
	let skyColor = $state('#a7cdf0');
	let showPeakLabels = $state(true);
	let showPlaces = $state(true);
	let peakTolerance = $state(0.06);
	let exaggeration = $state(1); // display-only vertical stretch
	// fullscreen: collapse the sidebar and the workbench nav; Esc exits
	let full = $state(false);

	let picked = $state<TerrainPick | null>(null);
	let peaks = $state<Peak[]>([]);
	const peaksCache = new Map<string, Peak[]>();

	// data credits, collapsed to a tiny ⓘ chip by default (the full
	// Copernicus notice is a paragraph — expanded it obscures the render)
	let creditsOpen = $state(false);

	// render-list search: photo title / photo id / render id / coords substring
	let filter = $state('');
	const filtered = $derived.by(() => {
		const q = filter.trim().toLowerCase();
		if (!q) return renders;
		return renders.filter(
			(r) =>
				(r.photo_title ?? '').toLowerCase().includes(q) ||
				(r.photo_id ?? '').toLowerCase().includes(q) ||
				r.id.toLowerCase().includes(q) ||
				`${r.lat.toFixed(4)}, ${r.lon.toFixed(4)}`.includes(q)
		);
	});

	// a render is viewable once real grid meta + artifacts exist
	const viewable = $derived(
		sel && sel.status === 'done' && sel.meta && 'width' in sel.meta ? sel : null
	);

	async function load() {
		try {
			renders = (await api.get<{ renders: RenderRow[] }>('/terrain/renders')).renders;
			err = null;
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		}
	}

	async function enqueue() {
		busy = true;
		try {
			const body = {
				...(photoId
					? { photo_id: photoId }
					: { lat: parseFloat(adhocLat), lon: parseFloat(adhocLon) }),
				params: renderParams()
			};
			await api.post('/terrain/enqueue', body);
			await load();
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			busy = false;
		}
	}

	async function select(r: RenderRow) {
		sel = r;
		picked = null;
		peaks = peaksCache.get(r.id) ?? [];
		if (r.status !== 'done' || !r.meta) return;
		if (!peaksCache.has(r.id)) {
			// label candidates; failures degrade to an unlabeled view
			try {
				const radius = Math.min(200_000, r.meta.max_distance_m ?? 100_000);
				const resp = await api.get<{ peaks: Peak[] }>(
					`/terrain/peaks?lat=${r.lat}&lon=${r.lon}&radius_m=${radius}`
				);
				const got = resp.peaks ?? [];
				peaksCache.set(r.id, got);
				if (sel?.id === r.id) peaks = got;
			} catch {
				/* no labels beats no viewer */
			}
		}
	}

	onMount(async () => {
		await load();
		// deep links: /terrain?render=<id> selects that render (a prefix of
		// the uuid is enough — the rows show the first 8 chars); /terrain?
		// photo=<id> pre-fills the enqueue form and selects that photo's
		// newest render if one exists
		const rid = page.url.searchParams.get('render');
		const pid = page.url.searchParams.get('photo');
		const byId = rid ? renders.find((x) => x.id.startsWith(rid)) : undefined;
		if (byId) {
			if (byId.photo_id) photoId = byId.photo_id;
			select(byId);
		} else if (pid) {
			photoId = pid;
			const r = renders.find((x) => x.photo_id === pid); // newest-first
			if (r) select(r);
		}
	});
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && (full = false)} />

<div class="terrain-page" class:full>
	<aside class="side">
		<div class="head">
			<h1>Terrain</h1>
			<Help>
				<h4>what this page does</h4>
				<p>
					Renders a synthetic depth panorama — what the terrain <i>should</i> look like —
					from a chosen viewpoint, out to 100 km, and views it with live fog, peak labels,
					and click-to-coordinates (a click on sky snaps to the horizon).
				</p>
				<h4>viewpoint</h4>
				<dl>
					<dt>photo id</dt>
					<dd>
						render from that photo's GPS position (its EXIF altitude becomes an eye-height
						hint). Photos render their view wedge — bearing ± half the FOV ± 5°, using the
						calibrated FOV when one exists (assumed 90° otherwise); only wedges covering
						the full circle fall back to 360°.
					</dd>
					<dt>lat, lon</dt>
					<dd>ad-hoc viewpoint anywhere (used when photo id is empty)</dd>
				</dl>
				<h4>render options</h4>
				<dl>
					<dt>DEM source</dt>
					<dd>
						<b>auto</b> = the worker's best available (the ČÚZK composite where built,
						GLO-30 elsewhere) — the normal choice. <b>GLO-30</b>: force the global 30 m
						radar surface model alone, for source comparison. <b>ČÚZK</b>: name the
						Czech lidar composite explicitly (2 m near / 10 m mid rings, bare-earth
						observer grounding, GLO-30 beyond) — same as auto where it's built.
					</dd>
					<dt>resolution</dt>
					<dd>
						angular grid step; 0.025° is the default (7200×~N for 180°). <b>0.005° ×10
						sector</b> renders a 36° slice at ten times the detail — a full 360° at ×10
						would exceed GPU texture limits, hence the sector.
					</dd>
					<dt>sector center</dt>
					<dd>azimuth the ×10 sector is centered on: 0 = north, 90 = east… renders ±18°</dd>
					<dt>eye height</dt>
					<dd>
						metres above bare ground; 2 ≈ standing person. In built-up spots the surface
						model's roofline IS the horizon — try 25 for a tower's view.
					</dd>
				</dl>
				<p>
					The vertical window auto-fits to the measured horizon (+1.5° margin), so pixels
					aren't wasted on empty sky. Viewer controls float on the image: fog visibility,
					sky color, vertical exaggeration (display-only), peak labels + their depth-match
					tolerance, ⛶ fullscreen.
				</p>
			</Help>
		</div>
		{#if err}<p class="err">{err}</p>{/if}
		<div class="enqueue">
			<label class="field">
				<span>photo id</span>
				<input placeholder="viewpoint from a photo" bind:value={photoId} />
			</label>
			<div class="field">
				<span>or lat, lon</span>
				<span class="pair">
					<input placeholder="lat" data-testid="terrain-lat" bind:value={adhocLat} />
					<input placeholder="lon" data-testid="terrain-lon" bind:value={adhocLon} />
				</span>
			</div>
			<label class="field">
				<span>DEM source</span>
				<select data-testid="terrain-dsm-stack" bind:value={dsmStack}>
					<option value="auto">auto (worker default)</option>
					<option value="glo30">GLO-30 · 30 m global</option>
					<option value="cuzk">ČÚZK · 1 m lidar (CZ)</option>
				</select>
			</label>
			<label class="field">
				<span>resolution</span>
				<select data-testid="terrain-step-deg" bind:value={stepDeg}>
					<option value={0.1}>0.1° · fast preview</option>
					<option value={0.05}>0.05° · coarse</option>
					<option value={0.025}>0.025° · default</option>
					<option value={0.005}>0.005° · ×10, 36° sector</option>
					<option value={0.0025}>0.0025° · ×20, 18° sector</option>
				</select>
			</label>
			{#if stepDeg <= 0.005}
				<label class="field">
					<span>sector center</span>
					<span class="pair">
						<input
							type="number"
							min="0"
							max="360"
							step="1"
							data-testid="terrain-sector-az"
							bind:value={sectorAz}
						/>
						<em>° (0 = N), ±18°</em>
					</span>
				</label>
			{/if}
			<label class="field">
				<span>eye height</span>
				<span class="pair">
					<input
						type="number"
						min="1"
						max="500"
						step="1"
						data-testid="terrain-eye-height"
						bind:value={eyeHeight}
					/>
					<em>m above ground</em>
				</span>
			</label>
			<label class="field">
				<span>max distance</span>
				<span class="pair">
					<input
						type="number"
						min="5"
						max="260"
						step="5"
						data-testid="terrain-max-km"
						bind:value={maxKm}
						title="how far the horizon march goes. Depth encoding caps at 262 km; beyond ~100 km check the DEM bbox covers that far (TERRAIN_AUTO_DEM_BBOX) — terrain outside it renders as sky"
					/>
					<em>km · ≤ 262</em>
				</span>
			</label>
			<div class="row">
				<button data-testid="terrain-enqueue" onclick={enqueue} disabled={busy}>
					Enqueue render
				</button>
				<button data-testid="terrain-refresh" onclick={load} title="refresh list">↻</button>
			</div>
		</div>
		<input
			class="filter"
			placeholder="filter by title / photo / id / coords…"
			data-testid="terrain-filter"
			bind:value={filter}
		/>
		<ul class="renders">
			{#each filtered as r (r.id)}
				<li class:active={sel?.id === r.id}>
					<button data-testid="terrain-row" data-status={r.status} data-render-id={r.id} onclick={() => select(r)}>
						<b>{r.status}</b>
						{r.photo_title ??
							(r.photo_id ? r.photo_id.slice(0, 8) : `${r.lat.toFixed(4)}, ${r.lon.toFixed(4)}`)}
						<small
							>{new Date(r.enqueued_at).toLocaleString()} · <code class="rid" title={r.id}>{r.id.slice(0, 8)}</code>{#if r.meta?.max_distance_m}
								{' · '}{Math.round(r.meta.max_distance_m / 1000)} km{/if}{#if r.meta?.eye_elevation_m}
								{' · '}<span
									title={`eye ${r.meta.eye_elevation_m.toFixed(1)} m — ${r.meta.eye_source ?? '?'}` +
										(r.meta.ground_m != null ? ` (ground ${r.meta.ground_m} m)` : '')}
									>eye {Math.round(r.meta.eye_elevation_m)} m</span
								>{/if}</small
						>
						{#if r.error}<small class="err">{r.error}</small>{/if}
					</button>
				</li>
			{/each}
		</ul>
	</aside>

	<div class="stage">
		{#if viewable}
			<TerrainViewer
				bind:this={viewerRef}
				onlabels={(placed) => (placedKeys = new Set(placed.map(markKey)))}
				previewUrl={`${apiBase}/terrain/renders/${viewable.id}/preview`}
				depthUrl={`${apiBase}/terrain/renders/${viewable.id}/depth`}
				meta={viewable.meta!}
				bind:visibilityKm
				bind:skyColor
				onpick={(p) => (picked = p)}
				{peaks}
				bind:showPeakLabels
				bind:showPlaces
				bind:peakTolerance
				bind:exaggeration
				canvasTestId="terrain-canvas"
				onviewer={(v) =>
					((window as unknown as { __hvTerrainViewer?: DepthPanoViewer }).__hvTerrainViewer = v)}
			/>
		{:else}
			<div class="placeholder">
				{#if !sel}select a render{:else if sel.meta?.stage}{sel.meta.stage}…{:else}
					render is {sel.status}{#if sel.status === 'rendering' && sel.meta?.progress_pct != null}
						&nbsp;— {sel.meta.progress_pct} %{/if}
				{/if}
			</div>
		{/if}

		<!-- overlay toolbar: steals no height from the viewer -->
		<div class="bar">
			<button
				class="tool"
				data-testid="terrain-fullscreen"
				title={full ? 'exit fullscreen (Esc)' : 'fullscreen — hide sidebar and nav'}
				onclick={() => (full = !full)}
			>
				{full ? '✕' : '⛶'}
			</button>
			<label title="meteorological visibility: haze on the terrain AND the label cutoff — nothing farther than this gets a label (the overlay bench saves the same cutoff into the fit)">
				fog
				<input
					type="range"
					min="2"
					max="300"
					data-testid="terrain-visibility"
					bind:value={visibilityKm}
				/>
				{visibilityKm} km
			</label>
			<label>sky <input type="color" bind:value={skyColor} /></label>
			<label
				title="vertical exaggeration — display-only stretch, depths and picks unchanged"
			>
				exag
				<input
					type="range"
					min="1"
					max="8"
					step="0.25"
					data-testid="terrain-exaggeration"
					bind:value={exaggeration}
				/>
				×{exaggeration}
			</label>
			<label><input type="checkbox" bind:checked={showPeakLabels} /> peaks</label>
			{#if showPeakLabels}
				<label title="include settlement names (city/town/village/district) among the labels">
					<input type="checkbox" bind:checked={showPlaces} /> places
				</label>
				<label title="depth match window — the ? explains what it changes">
					window ±{Math.round(peakTolerance * 100)}%
					<input
						type="range"
						min="0.01"
						max="0.10"
						step="0.005"
						data-testid="terrain-peak-tol"
						bind:value={peakTolerance}
					/>
				</label>
				<Help align="right" title="what does the window change?">
					<h4>depth match window</h4>
					<p>
						A candidate (peak, tower, settlement) gets a label when the column of the depth
						buffer under its bearing sees terrain at about its distance. "About" is this
						window: <b>±{Math.round(peakTolerance * 100)} % of the candidate's distance, + 8 m</b>.
						At 60 km that is ±{(peakTolerance * 60).toFixed(1)} km.
					</p>
					<dl>
						<dt>tighter</dt>
						<dd>
							fewer labels — and the ones that drop out are mostly <i>visible</i> summits
							whose exact distance fell between two sampled rows: one 0.025° row moves the
							ground hit-point by kilometres at grazing angles, and the render's own march
							steps 0.5 % of distance. Below ~3 % you are rejecting real summits.
						</dd>
						<dt>wider</dt>
						<dd>
							more labels — but the extra ones are mostly ridges <i>in front of hidden
							places</i> being counted as them (the famous valley towns appear on the
							horizon line, at the right bearing, and are not visible). Above ~10 % this
							stops being a visibility test, which is why the slider ends there.
						</dd>
						<dt>default 6 %</dt>
						<dd>the render's own depth precision — measured: 98 % of what it rejects sits
							more than two rows below the ridge by the candidate's own elevation.</dd>
					</dl>
					<h4>what it does not change</h4>
					<ul>
						<li>
							<b>summit vs mass</b> — whether a label prints its elevation is a separate,
							tighter test (300 m + 3 % of distance, plus the candidate's own elevation
							angle agreeing with the pixel to within ~100 m).
						</li>
						<li>
							<b>direction labels</b> — hidden but notable settlements are the dim, dashed
							ones, decided by hiddenness, not by this window.
						</li>
						<li>
							<b>what graduates</b> — the overlay bench and the export are pinned at 6 %.
							This slider is a lens for exploring the pool on this page.
						</li>
					</ul>
					<p>Tap any label to see what it claims and the numbers behind it.</p>
				</Help>
				<button
					class:on={poolOpen}
					data-testid="terrain-pool-toggle"
					title="list every candidate in this render's sweep with its verdict — why a name makes it or doesn't"
					onclick={() => (poolOpen = !poolOpen)}>pool</button
				>
			{/if}
		</div>

		{#if poolOpen}
			<div class="pool" data-testid="terrain-pool">
				<div class="pool-head">
					<input placeholder="filter by name…" bind:value={poolFilter} data-testid="terrain-pool-filter" />
					<span class="counts">
						{#each Object.entries(poolCounts) as [v, n] (v)}<span title={VERDICT_LABEL[v as PeakVerdict] ?? v}>{v} {n}</span>{/each}
					</span>
					<button class="linkish" onclick={() => (poolOpen = false)} aria-label="close">×</button>
				</div>
				<div class="pool-body">
					{#if !poolRows.length}
						<p class="muted">no render / pool loaded yet</p>
					{:else}
						<table>
							<thead><tr><th>name</th><th>km</th><th>az</th><th>verdict</th><th>now</th><th>why</th></tr></thead>
							<tbody>
								{#each poolShown as r (`${r.peak.name}@${r.azimuth_deg.toFixed(3)}`)}
									<tr
										class:label={!!r.mark}
										class:dim={r.mark?.class === 'direction'}
										class:on={!!r.mark && placedKeys.has(markKey(r.mark))}
										title="click to centre the view on it"
										onclick={() => viewerRef?.centerOnAzimuth(r.azimuth_deg)}
									>
										<td class="name">{r.peak.name}{#if r.peak.kind && r.peak.kind !== 'peak'}<small> {r.peak.kind}</small>{/if}</td>
										<td class="num">{(r.distance_m / 1000).toFixed(r.distance_m < 10000 ? 1 : 0)}</td>
										<td class="num">{r.azimuth_deg.toFixed(1)}°</td>
										<td class="verdict v-{r.verdict}">{VERDICT_LABEL[r.verdict]}</td>
										<td class="now">{poolStatus(r)}</td>
										<td class="why">{r.reason}</td>
									</tr>
								{/each}
							</tbody>
						</table>
						{#if poolShown.length < poolRows.length && !poolFilter}<p class="muted">first 400 of {poolRows.length} — filter to see the rest</p>{/if}
					{/if}
				</div>
			</div>
		{/if}

		{#if picked}
			<div class="chip picked" data-testid="terrain-picked">
				📍 {picked.label ? `${picked.label} · ` : ''}{picked.lat.toFixed(5)}, {picked.lon.toFixed(5)}
				· {(picked.distance_m / 1000).toFixed(1)} km @ {picked.azimuth_deg.toFixed(1)}°
				{#if picked.evidence}<span class="evidence" data-testid="terrain-picked-evidence"> · {picked.evidence}</span>{/if}
				<a href={`https://hillview.cz/?lat=${picked.lat}&lon=${picked.lon}&zoom=14`} target="_blank"
					>open on map</a
				>
				<button onclick={() => navigator.clipboard.writeText(`${picked!.lat}, ${picked!.lon}`)}
					>copy</button
				>
			</div>
		{:else if viewable}
			<div class="chip hint">drag = pan · scroll/pinch = zoom · click = geo coords (sky → horizon)</div>
		{/if}
		{#if viewable?.meta?.attribution || peaks.length}
			{@const credits = [
				viewable?.meta?.attribution,
				peaks.length ? 'labels © OpenStreetMap contributors' : null
			]
				.filter(Boolean)
				.join(' · ')}
			<button
				class="chip attribution"
				class:open={creditsOpen}
				title={creditsOpen ? 'hide credits' : credits}
				onclick={() => (creditsOpen = !creditsOpen)}
			>
				{creditsOpen ? credits : 'ⓘ ©'}
			</button>
		{/if}
	</div>
</div>

<style>
	/* The page owns the viewport: body becomes a 100dvh column (nav keeps its
	   natural height), main flexes to the remainder, full-bleed.
	   DESCENDANT combinators on purpose: app.html wraps %sveltekit.body% in a
	   display:contents div, so `body > main` never matches — nav/main still
	   participate in body's flex layout, but child selectors skip them. */
	:global(body:has(.terrain-page)) {
		height: 100dvh;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	:global(body:has(.terrain-page) main) {
		flex: 1;
		min-height: 0;
		max-width: none;
		padding: 0;
		margin: 0;
		display: flex;
	}
	:global(body:has(.terrain-page.full) nav.top) {
		display: none;
	}

	.terrain-page {
		flex: 1;
		min-width: 0;
		display: flex;
	}

	/* ---- sidebar: enqueue / search / list ---- */
	.side {
		width: 330px;
		flex: none;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		padding: 10px;
		border-right: 1px solid #2b2f36;
		min-height: 0;
	}
	.terrain-page.full .side {
		display: none;
	}
	.head {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.side h1 {
		font-size: 15px;
		margin: 0;
	}
	.enqueue {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}
	/* labeled rows: name column left, control right — no mystery fields */
	.field {
		display: grid;
		grid-template-columns: 92px 1fr;
		gap: 0.45rem;
		align-items: center;
		font-size: 12px;
	}
	.field > span:first-child {
		text-align: right;
		color: #99a;
	}
	.field select,
	.field > input {
		width: 100%;
		box-sizing: border-box;
		min-width: 0;
	}
	.pair {
		display: flex;
		flex-wrap: wrap; /* long unit hints drop below, never squeeze the input */
		gap: 0.35rem;
		align-items: center;
		min-width: 0;
	}
	.pair input {
		flex: 1 1 5em;
		min-width: 5em; /* digits stay visible no matter the hint length */
		box-sizing: border-box;
	}
	.pair em {
		font-style: normal;
		color: #778;
		font-size: 11px;
		white-space: nowrap;
	}
	.enqueue .row {
		display: flex;
		gap: 0.35rem;
	}
	.enqueue .row > * {
		flex: 1;
		min-width: 0;
	}
	.filter {
		width: 100%;
		box-sizing: border-box;
		min-width: 0;
	}
	.renders {
		list-style: none;
		padding: 0;
		margin: 0;
		overflow-y: auto;
		min-height: 0;
		flex: 1;
	}
	.renders li button {
		width: 100%;
		text-align: left;
		display: flex;
		flex-direction: column;
	}
	.renders li.active button {
		outline: 2px solid var(--accent, #4a90e2);
	}
	.renders .rid {
		font-family: ui-monospace, Menlo, Consolas, monospace;
		font-size: 0.95em;
		opacity: 0.85;
	}

	/* ---- stage: the viewer fills it; controls float on top ---- */
	.stage {
		flex: 1;
		min-width: 0;
		min-height: 0;
		position: relative;
		display: flex;
		flex-direction: column;
		background: #16181c;
	}
	.placeholder {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #889;
	}
	.bar {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		z-index: 5;
		display: flex;
		gap: 1rem;
		align-items: center;
		flex-wrap: wrap;
		padding: 6px 10px;
		background: rgba(13, 15, 18, 0.72);
		backdrop-filter: blur(3px);
		font-size: 12px;
	}
	.bar label {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		white-space: nowrap;
	}
	.bar input[type='range'] {
		width: 90px;
	}
	.tool {
		font-size: 13px;
		padding: 2px 8px;
	}
	.chip {
		position: absolute;
		z-index: 5;
		background: rgba(13, 15, 18, 0.78);
		border-radius: 6px;
		padding: 5px 9px;
		font-size: 12px;
	}
	.chip.picked {
		left: 10px;
		bottom: 10px;
		font-variant-numeric: tabular-nums;
		max-width: calc(100% - 20px);
	}
	.chip.picked .evidence {
		opacity: 0.8;
	}
	/* ---- label pool listing: a docked panel over the right of the stage ---- */
	.pool {
		position: absolute;
		top: 44px;
		right: 8px;
		bottom: 40px;
		width: min(560px, 60%);
		z-index: 6;
		display: flex;
		flex-direction: column;
		background: rgba(13, 15, 18, 0.9);
		backdrop-filter: blur(3px);
		border-radius: 8px;
		font-size: 12px;
	}
	.pool-head {
		display: flex;
		gap: 8px;
		align-items: center;
		padding: 6px 8px;
		border-bottom: 1px solid rgba(255, 255, 255, 0.12);
	}
	.pool-head input {
		flex: 0 0 160px;
	}
	.pool-head .counts {
		flex: 1;
		display: flex;
		flex-wrap: wrap;
		gap: 4px 10px;
		opacity: 0.8;
		font-variant-numeric: tabular-nums;
	}
	.pool-body {
		overflow: auto;
		min-height: 0;
	}
	.pool table {
		border-collapse: collapse;
		width: 100%;
	}
	.pool th {
		position: sticky;
		top: 0;
		background: rgba(13, 15, 18, 0.95);
		text-align: left;
		font-weight: 600;
		padding: 4px 6px;
		font-size: 11px;
		opacity: 0.75;
	}
	.pool td {
		padding: 3px 6px;
		border-top: 1px solid rgba(255, 255, 255, 0.06);
		vertical-align: top;
	}
	.pool tr {
		cursor: pointer;
	}
	.pool tr:hover td {
		background: rgba(255, 255, 255, 0.05);
	}
	.pool tr:not(.label) td {
		opacity: 0.6;
	}
	.pool tr.dim td.name {
		font-style: italic;
	}
	.pool tr.on td.name {
		color: var(--accent, #4a90e2);
	}
	.pool td.num {
		font-variant-numeric: tabular-nums;
		text-align: right;
		white-space: nowrap;
	}
	.pool td.verdict {
		white-space: nowrap;
	}
	.pool td.v-summit { color: #f2d55c; }
	.pool td.v-mass { color: #d9c48a; }
	.pool td.v-direction { color: #8fb4d9; }
	.pool td.why {
		opacity: 0.85;
		min-width: 14em;
	}
	.pool .muted {
		opacity: 0.6;
		padding: 8px;
	}
	.linkish {
		background: none;
		border: 0;
		color: inherit;
		cursor: pointer;
		padding: 0 4px;
		font: inherit;
	}
	.chip.hint {
		left: 10px;
		bottom: 10px;
		opacity: 0.75;
	}
	.chip.attribution {
		right: 10px;
		bottom: 10px;
		opacity: 0.6;
		font-size: 10.5px;
		border: none;
		color: inherit;
		cursor: pointer;
	}
	.chip.attribution.open {
		max-width: 60%;
		text-align: left;
		opacity: 0.9;
	}
	.err {
		color: #d33;
		margin: 0;
	}

	/* ---- mobile: stack sidebar above the stage, one-line scrollable bar ---- */
	@media (max-width: 760px) {
		.terrain-page {
			flex-direction: column;
		}
		.side {
			width: auto;
			max-height: 42dvh;
			overflow-y: auto;
			border-right: none;
			border-bottom: 1px solid #2b2f36;
		}
		/* the render list must NOT be a flex-remainder here: inside the
		   height-capped scrollable sidebar the form eats the cap and flex
		   would shrink the list to 0 (= "there's no list"). Fixed height,
		   scrolls internally; the sidebar scrolls to reach it. */
		.renders {
			flex: none;
			height: 24dvh;
		}
		.stage {
			min-height: 0;
		}
		/* toolbar: a single swipeable strip instead of rows stacked over the
		   canvas; range inputs shrink so more fits per screen */
		.bar {
			flex-wrap: nowrap;
			overflow-x: auto;
			gap: 0.8rem;
			padding: 5px 8px;
			-webkit-overflow-scrolling: touch;
			scrollbar-width: none;
		}
		.bar::-webkit-scrollbar {
			display: none;
		}
		.bar input[type='range'] {
			width: 64px;
		}
		.chip {
			font-size: 11px;
		}
		.chip.hint {
			display: none; /* gestures are self-evident on touch; save the space */
		}
		.field {
			grid-template-columns: 80px 1fr;
		}
	}
</style>
