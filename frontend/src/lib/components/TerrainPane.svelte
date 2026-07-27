<script lang="ts">
	// Terrain mode's pane (docs/terrain-mode.md): shows the spatially
	// selected render — the range circle keeps its job — as status text
	// while queued/rendering/failed (in-progress renders are first-class
	// citizens) and as the shared depth-pano viewer once artifacts exist.
	// Owns the render-list polling for the mode's lifetime.
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import TerrainViewer from './TerrainViewer.svelte';
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
	let peaks = $state<Peak[]>([]);

	// Empty-state escape hatch: enqueue at the map center. The new render is
	// by construction the nearest-in-range selection, so the pane flips to
	// "queued…" through the normal selection path — no local mode to unwind.
	let creating = $state(false);
	let createError = $state<string | null>(null);

	async function createAtCenter() {
		const { lat, lng } = get(spatialState).center;
		creating = true;
		createError = null;
		try {
			await enqueueTerrainRender(lat, lng);
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
			<button
				class="create-btn"
				data-testid="terrain-pane-create"
				disabled={creating}
				onclick={createAtCenter}
			>
				{creating ? 'enqueuing…' : 'Render terrain view here'}
			</button>
			<p class="sub">
				from the map center — or long-press the map to pick a spot, or tap an existing marker
			</p>
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
		/>
		<div class="statusbar">
			<label class="labels-toggle">
				<input type="checkbox" bind:checked={showPeakLabels} />
				peaks
			</label>
			<label class="fog">
				fog
				<input type="range" min="5" max="200" step="5" bind:value={visibilityKm} />
				{visibilityKm} km
			</label>
			{#if markerStateOf(sel) === 'rendering'}
				<span class="rendering" data-testid="terrain-pane-rendering">
					rendering…{#if progressOf(sel) !== null}&nbsp;{progressOf(sel)} %{/if}
				</span>
			{/if}
			{#if pick}
				<span class="pick" data-testid="terrain-pick">
					{pick.lat.toFixed(5)}, {pick.lon.toFixed(5)} · {(pick.distance_m / 1000).toFixed(1)} km
					· az {pick.azimuth_deg.toFixed(1)}°
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
