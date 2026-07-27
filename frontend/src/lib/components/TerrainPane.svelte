<script lang="ts">
	// Terrain mode's pane (docs/terrain-mode.md): shows the spatially
	// selected render — the range circle keeps its job — as status text
	// while queued/rendering/failed (in-progress renders are first-class
	// citizens) and as the shared depth-pano viewer once artifacts exist.
	// Owns the render-list polling for the mode's lifetime.
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import TerrainViewer from '$terrain/TerrainViewer.svelte';
	import { artifactVersion, attributionOf, gridMetaOf, isViewable, markerStateOf, progressOf } from '$lib/terrainModel';
	import {
		enqueueTerrainRender,
		pendingTerrainRect,
		selectedTerrainRender,
		startTerrainPolling,
		stopTerrainPolling,
		terrainDepthUrl,
		terrainError,
		terrainPeaksFor,
		terrainPick,
		terrainPreviewUrl,
		terrainQueue,
		terrainViewRect
	} from '$lib/terrain.svelte';
	import { spatialState } from '$lib/mapState';
	import type { Peak } from '$terrain/peakLabels';

	let visibilityKm = $state(80);
	let showPeakLabels = $state(true);
	// display-only vertical stretch (1 = true angles) — far relief is
	// sub-degree at real scale, exaggeration makes it readable
	let exaggeration = $state(1);
	// relative depth tolerance of the peak↔render match: looser → more labels
	// (and more risk of labeling a peak actually hidden behind a similar-depth
	// ridge); 0.06 mirrors peakLabels.PEAK_DEPTH_REL_TOL
	let peakTolerance = $state(0.06);
	let peaks = $state<Peak[]>([]);

	// Empty-state escape hatch: enqueue at the map center. The new render is
	// by construction the nearest-in-range selection, so the pane flips to
	// "queued…" through the normal selection path — no local mode to unwind.
	let creating = $state(false);
	let createError = $state<string | null>(null);

	// DEM source (worker-side named stacks via the dsm_stack param) and grid
	// resolution (az/elev step). 'auto' / 0.05° = worker defaults, sent as no
	// param at all so the server-side defaults stay the single source of truth.
	let dsmStack = $state<'auto' | 'glo30' | 'cuzk'>('auto');
	let stepDeg = $state(0.025); // worker default (2x the renderer's 0.05)
	// 0.005° is sector-only (a full 360° sweep at ×10 would be a 72k-column
	// texture — beyond every GPU limit); the sector is centered here, ±18°
	let sectorAz = $state(0);
	// metres above the bare ground the eye stands (worker default 2). In a
	// built-up viewpoint the SURFACE model's roofline is the horizon — ~25 m
	// sees over it (the "what would a tower here see" knob).
	let eyeHeight = $state(2);

	function createParams(): Record<string, unknown> {
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
		return p;
	}

	async function createAtCenter() {
		const { lat, lng } = get(spatialState).center;
		creating = true;
		createError = null;
		try {
			await enqueueTerrainRender(lat, lng, createParams());
		} catch (e) {
			createError = e instanceof Error ? e.message : String(e);
		} finally {
			creating = false;
		}
	}

	// A tx1..ty2 deep link applies to the first render this pane loads, then
	// dies with it — re-entering the mode later must not resurrect it.
	const initialRect = get(pendingTerrainRect);
	pendingTerrainRect.set(null);

	onMount(() => {
		startTerrainPolling();
		return stopTerrainPolling;
	});

	const sel = $derived($selectedTerrainRender);
	const pick = $derived($terrainPick);
	// consumers === 0 means enqueued jobs sit in RabbitMQ forever — the worker
	// is a host process (enrich/terrain/run_worker.sh), so this is the only
	// place the user can learn it isn't running.
	const noWorker = $derived($terrainQueue !== null && $terrainQueue.consumers === 0);

	// peak candidates follow the selection; failures degrade to no labels
	$effect(() => {
		const s = sel;
		peaks = [];
		if (!s || !isViewable(s)) return;
		terrainPeaksFor(s)
			.then((p) => {
				if ($selectedTerrainRender?.id === s.id) peaks = p;
			})
			.catch(() => {});
	});
</script>

<div class="terrain-pane" data-testid="terrain-pane">
	{#if $terrainError}
		<div class="notice error">terrain API unreachable: {$terrainError}</div>
	{:else if !sel}
		<div class="notice" data-testid="terrain-pane-empty">
			<p>No terrain render in range.</p>
			<div class="create-row">
				<select
					class="create-opt"
					data-testid="terrain-dsm-stack"
					title="elevation data source"
					bind:value={dsmStack}
				>
					<option value="auto">DEM: auto</option>
					<option value="glo30">GLO-30 (30 m)</option>
					<option value="cuzk">ČÚZK (fine)</option>
				</select>
				<select
					class="create-opt"
					data-testid="terrain-step-deg"
					title="angular resolution of the panorama grid"
					bind:value={stepDeg}
				>
					<option value={0.1}>0.1° fast</option>
					<option value={0.05}>0.05°</option>
					<option value={0.025}>0.025° (default)</option>
					<option value={0.005}>0.005° ×10 sector</option>
					<option value={0.0025}>0.0025° ×20 sector</option>
				</select>
				{#if stepDeg <= 0.005}
					<label
						class="create-opt eye"
						title="sector center azimuth in degrees (0 = north; ×10 renders ±18°, ×20 renders ±9°)"
					>
						az
						<input
							type="number"
							min="0"
							max="360"
							step="1"
							bind:value={sectorAz}
							data-testid="terrain-sector-az"
						/>
						°
					</label>
				{/if}
				<label
					class="create-opt eye"
					title="eye height above ground in metres (default 2) — raise it to see over the local roofline/canopy, e.g. 25 for a tower's view"
				>
					eye
					<input
						type="number"
						min="1"
						max="500"
						step="1"
						bind:value={eyeHeight}
						data-testid="terrain-eye-height"
					/>
					m
				</label>
				<button
					class="create-btn"
					data-testid="terrain-pane-create"
					disabled={creating}
					onclick={createAtCenter}
				>
					{creating ? 'enqueuing…' : 'Render terrain view here'}
				</button>
			</div>
			<p class="sub">
				from the map center — or long-press the map to pick a spot, or tap an existing marker
			</p>
			<div class="source-info" data-testid="terrain-source-info">
				{#if dsmStack === 'auto'}
					<strong>auto</strong> — the render worker's default stack, which is the
					best it has: the ČÚZK composite where it's built (2 m near / 10 m mid /
					GLO-30 far, bare-earth observer grounding), plain GLO-30 elsewhere. The
					right choice unless you're deliberately comparing sources.
				{:else if dsmStack === 'glo30'}
					<strong>Copernicus GLO-30</strong> — global ~30 m surface model derived
					from the TanDEM-X radar mission (WorldDEM, acquired 2010–2015), EU/ESA
					open data. "Surface" means treetops and buildings are part of the
					terrain — which is what real skylines are made of — but the observer
					also stands on that surface (no bare-earth correction, so eye height
					can sit on canopy). 30 m cells resolve ridgelines from a few km out;
					the near foreground looks smoothed. Auto-downloaded here for Czechia
					plus ~100 km of margin.
				{:else}
					<strong>ČÚZK lidar</strong> (Czechia only, CC BY 4.0) — the national
					survey's aerial-lidar models: DMP 1G (~1 m surface, canopy and
					buildings) drives the skyline rays, while DMR 5G (bare earth) grounds
					the <em>observer</em>, so eye height stays correct even under trees.
					Rasterized to a 10 m near ring used out to 15 km, blending into GLO-30
					beyond that and across the border. Only covers the pre-built area
					(currently a Prague bbox) — elsewhere the render fails with "not
					configured" instead of silently substituting coarser data.
				{/if}
			</div>
			{#if noWorker}
				<p class="worker-warning" data-testid="terrain-no-worker">
					⚠ no render worker is connected — jobs will queue until one starts
					(enrich/terrain/run_worker.sh)
				</p>
			{/if}
			{#if createError}
				<p class="create-error" data-testid="terrain-pane-create-error">
					enqueue failed: {createError}
				</p>
			{/if}
		</div>
	{:else if isViewable(sel)}
		<TerrainViewer
			previewUrl={terrainPreviewUrl(sel.id, artifactVersion(sel))}
			depthUrl={terrainDepthUrl(sel.id, artifactVersion(sel))}
			meta={gridMetaOf(sel)!}
			bind:visibilityKm
			onpick={(p) => terrainPick.set(p)}
			onviewchange={(r) => terrainViewRect.set(r)}
			{initialRect}
			{peaks}
			bind:showPeakLabels
			bind:peakTolerance
			bind:exaggeration
		/>
		<div class="statusbar">
			<label class="labels-toggle">
				<input type="checkbox" bind:checked={showPeakLabels} />
				peaks
			</label>
			{#if showPeakLabels}
				<label
					class="peak-tol"
					title="depth-match tolerance: looser shows more labels, but may label peaks actually hidden behind a similar-depth ridge"
				>
					±{Math.round(peakTolerance * 100)}%
					<input
						type="range"
						min="0.01"
						max="0.25"
						step="0.005"
						bind:value={peakTolerance}
						data-testid="terrain-peak-tol"
					/>
				</label>
			{/if}
			<label class="fog">
				fog
				<input type="range" min="5" max="200" step="5" bind:value={visibilityKm} />
				{visibilityKm} km
			</label>
			<label
				class="fog"
				title="vertical exaggeration — display-only stretch, depths and picks unchanged"
			>
				exag
				<input
					type="range"
					min="1"
					max="8"
					step="0.25"
					bind:value={exaggeration}
					data-testid="terrain-exaggeration"
				/>
				×{exaggeration}
			</label>
			{#if markerStateOf(sel) === 'rendering'}
				<span class="rendering" data-testid="terrain-pane-rendering">
					rendering…{#if progressOf(sel) !== null}&nbsp;{progressOf(sel)} %{/if}
				</span>
			{/if}
			{#if pick}
				<span class="pick" data-testid="terrain-pick">
					{pick.label ? `${pick.label} · ` : ''}{pick.lat.toFixed(5)}, {pick.lon.toFixed(5)}
					· {(pick.distance_m / 1000).toFixed(1)} km · az {pick.azimuth_deg.toFixed(1)}°
				</span>
			{:else}
				<span class="hint">tap a mountain for its coordinates</span>
			{/if}
			{#if attributionOf(sel) || peaks.length}
				<span class="attribution" data-testid="terrain-attribution">
					{attributionOf(sel) ?? ''}{attributionOf(sel) && peaks.length ? ' · ' : ''}{peaks.length
						? 'peaks © OpenStreetMap contributors'
						: ''}
				</span>
			{/if}
		</div>
	{:else}
		<div class="notice" data-testid="terrain-pane-status">
			{#if markerStateOf(sel) === 'failed'}
				render failed{sel.error ? `: ${sel.error}` : ''}
			{:else if markerStateOf(sel) === 'rendering'}
				rendering…{#if progressOf(sel) !== null}&nbsp;{progressOf(sel)} %{/if}
			{:else}
				queued…
			{/if}
			{#if noWorker && markerStateOf(sel) !== 'failed'}
				<p class="worker-warning" data-testid="terrain-no-worker">
					⚠ no render worker is connected — this job is waiting in the queue.
					Start one: enrich/terrain/run_worker.sh
				</p>
			{/if}
		</div>
	{/if}
</div>

<style>
	.terrain-pane {
		height: 100%;
		overflow: auto;
		background: #16181c;
		color: #ddd;
		display: flex;
		flex-direction: column;
		justify-content: center;
	}
	.notice {
		padding: 1rem;
		text-align: center;
		font-size: 0.9rem;
		color: #aaa;
	}
	.notice.error {
		color: #e77;
	}
	.notice p {
		margin: 0.4rem 0;
	}
	.create-row {
		display: flex;
		gap: 0.4rem;
		justify-content: center;
		align-items: center;
		flex-wrap: wrap;
	}
	.create-opt {
		background: #23262c;
		color: #ccc;
		border: 1px solid #3a3e46;
		border-radius: 6px;
		padding: 7px 6px;
		font-size: 0.8rem;
	}
	.create-opt.eye {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		white-space: nowrap;
	}
	.create-opt.eye input {
		width: 3.2rem;
		background: transparent;
		color: inherit;
		border: none;
		font-size: inherit;
		text-align: right;
	}
	/* same look as .terrain-create-popup button (Map.svelte) — one action, one style */
	.create-btn {
		background: #3a7d44;
		color: white;
		border: none;
		border-radius: 6px;
		padding: 8px 14px;
		cursor: pointer;
		font-size: 0.9rem;
	}
	.create-btn:disabled {
		opacity: 0.6;
		cursor: default;
	}
	.sub {
		font-size: 0.8rem;
		color: #777;
	}
	/* per-source explainer — follows the DEM dropdown selection */
	.source-info {
		max-width: 34rem;
		margin: 0.5rem auto 0;
		padding: 0.5rem 0.7rem;
		text-align: left;
		font-size: 0.75rem;
		line-height: 1.45;
		color: #999;
		background: #1c1f24;
		border: 1px solid #2b2f36;
		border-radius: 6px;
	}
	.source-info strong {
		color: #bbb;
	}
	.create-error {
		color: #e77;
	}
	.worker-warning {
		font-size: 0.8rem;
		color: #d9a441;
	}
	/* licence-required credit line — its own wrapped row at the statusbar's end */
	.attribution {
		flex-basis: 100%;
		font-size: 0.65rem;
		color: #777;
	}
	.statusbar {
		display: flex;
		align-items: center;
		gap: 0.8rem;
		padding: 0.3rem 0.6rem;
		font-size: 0.8rem;
		flex-wrap: wrap;
	}
	.labels-toggle {
		display: flex;
		align-items: center;
		gap: 0.3rem;
		white-space: nowrap;
	}
	.peak-tol {
		display: flex;
		align-items: center;
		gap: 0.3rem;
		white-space: nowrap;
		font-variant-numeric: tabular-nums;
	}
	.peak-tol input {
		width: 70px;
	}
	.fog {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		white-space: nowrap;
	}
	.fog input {
		width: 90px;
	}
	.pick {
		font-variant-numeric: tabular-nums;
	}
	.hint {
		color: #888;
	}
	.rendering {
		color: #7fb88a;
	}
</style>
