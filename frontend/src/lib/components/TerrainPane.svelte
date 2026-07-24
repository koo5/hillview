<script lang="ts">
	// Terrain mode's pane (docs/terrain-mode.md): shows the spatially
	// selected render — the range circle keeps its job — as status text
	// while queued/rendering/failed (in-progress renders are first-class
	// citizens) and as the shared depth-pano viewer once artifacts exist.
	// Owns the render-list polling for the mode's lifetime.
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import TerrainViewer from './TerrainViewer.svelte';
	import { artifactVersion, gridMetaOf, isViewable, markerStateOf, progressOf } from '$lib/terrainModel';
	import {
		pendingTerrainRect,
		selectedTerrainRender,
		startTerrainPolling,
		stopTerrainPolling,
		terrainDepthUrl,
		terrainError,
		terrainPick,
		terrainPreviewUrl,
		terrainViewRect
	} from '$lib/terrain.svelte';

	let visibilityKm = $state(80);

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
</script>

<div class="terrain-pane" data-testid="terrain-pane">
	{#if $terrainError}
		<div class="notice error">terrain API unreachable: {$terrainError}</div>
	{:else if !sel}
		<div class="notice" data-testid="terrain-pane-empty">
			No terrain render in range — tap a marker on the map, or long-press to create one.
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
		/>
		<div class="statusbar">
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
	.statusbar {
		display: flex;
		align-items: center;
		gap: 0.8rem;
		padding: 0.3rem 0.6rem;
		font-size: 0.8rem;
		flex-wrap: wrap;
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
