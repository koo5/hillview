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
		// deep link from the photo page: /terrain?photo=<id> pre-fills the
		// enqueue form and selects that photo's newest render if one exists
		const pid = page.url.searchParams.get('photo');
		if (pid) {
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
					<button data-testid="terrain-row" data-status={r.status} onclick={() => select(r)}>
						<b>{r.status}</b>
						{r.photo_title ??
							(r.photo_id ? r.photo_id.slice(0, 8) : `${r.lat.toFixed(4)}, ${r.lon.toFixed(4)}`)}
						<small>{new Date(r.enqueued_at).toLocaleString()}</small>
						{#if r.error}<small class="err">{r.error}</small>{/if}
					</button>
				</li>
			{/each}
		</ul>
	</aside>

	<div class="stage">
		{#if viewable}
			<TerrainViewer
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
			<label>
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
				<label
					title="depth-match tolerance: looser shows more labels, but may label peaks actually hidden behind a similar-depth ridge"
				>
					±{Math.round(peakTolerance * 100)}%
					<input
						type="range"
						min="0.01"
						max="0.25"
						step="0.005"
						data-testid="terrain-peak-tol"
						bind:value={peakTolerance}
					/>
				</label>
			{/if}
		</div>

		{#if picked}
			<div class="chip picked" data-testid="terrain-picked">
				📍 {picked.label ? `${picked.label} · ` : ''}{picked.lat.toFixed(5)}, {picked.lon.toFixed(5)}
				· {(picked.distance_m / 1000).toFixed(1)} km @ {picked.azimuth_deg.toFixed(1)}°
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
