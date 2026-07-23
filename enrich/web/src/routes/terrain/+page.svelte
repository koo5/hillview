<script lang="ts">
	// Terrain bench: view synthetic depth panoramas rendered from photo
	// viewpoints. All viewer logic (WebGL fog, zoom/pan/pinch, click-back
	// geodesy) lives in the SHARED core, $terrain/depthPanoViewer — the same
	// module the main app's TerrainViewer.svelte wraps. This page is just
	// the bench chrome: enqueue form, render list, fog controls, pick panel.
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import { apiBase } from '$lib/config';
	import {
		DepthPanoViewer,
		type TerrainMeta,
		type TerrainPick
	} from '$terrain/depthPanoViewer';

	interface RenderRow {
		id: string;
		photo_id: string | null;
		lat: number;
		lon: number;
		status: string;
		error: string | null;
		meta: TerrainMeta | null;
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

	// fog controls
	let visibilityKm = $state(80); // meteorological visibility
	let skyColor = $state('#a7cdf0');

	let picked = $state<TerrainPick | null>(null);

	let canvas: HTMLCanvasElement;
	let viewer: DepthPanoViewer | null = null;

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
			const body = photoId
				? { photo_id: photoId }
				: { lat: parseFloat(adhocLat), lon: parseFloat(adhocLon) };
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
		if (r.status !== 'done' || !r.meta) return;
		try {
			viewer ??= new DepthPanoViewer(canvas, { onPick: (p: TerrainPick | null) => (picked = p) });
			await viewer.load({
				previewUrl: `${apiBase}/terrain/renders/${r.id}/preview`,
				depthUrl: `${apiBase}/terrain/renders/${r.id}/depth`,
				meta: r.meta
			});
			viewer.setFog({ visibilityKm, skyColor });
		} catch (e) {
			err = e instanceof Error ? e.message : String(e);
		}
	}

	$effect(() => {
		viewer?.setFog({ visibilityKm, skyColor });
	});

	onMount(() => {
		load();
		return () => viewer?.destroy();
	});
</script>

<h1>Terrain — synthetic depth panoramas</h1>
{#if err}<p class="err">{err}</p>{/if}

<section class="enqueue">
	<input placeholder="photo id (viewpoint from photo_mirror)" bind:value={photoId} />
	<span>or</span>
	<input placeholder="lat" size="9" bind:value={adhocLat} />
	<input placeholder="lon" size="9" bind:value={adhocLon} />
	<button onclick={enqueue} disabled={busy}>Enqueue render</button>
	<button onclick={load}>↻</button>
</section>

<section class="split">
	<ul class="renders">
		{#each renders as r (r.id)}
			<li class:active={sel?.id === r.id}>
				<button onclick={() => select(r)}>
					<b>{r.status}</b>
					{r.photo_id ?? `${r.lat.toFixed(4)}, ${r.lon.toFixed(4)}`}
					<small>{new Date(r.enqueued_at).toLocaleString()}</small>
					{#if r.error}<small class="err">{r.error}</small>{/if}
				</button>
			</li>
		{/each}
	</ul>

	<div class="viewer">
		<canvas bind:this={canvas}></canvas>
		<div class="controls">
			<label>
				Visibility {visibilityKm} km
				<input type="range" min="2" max="300" bind:value={visibilityKm} />
			</label>
			<label>Sky / fog <input type="color" bind:value={skyColor} /></label>
			{#if picked}
				<div class="picked">
					📍 {picked.lat.toFixed(5)}, {picked.lon.toFixed(5)}
					· {(picked.distance_m / 1000).toFixed(1)} km @ {picked.azimuth_deg.toFixed(1)}°
					<a
						href={`https://hillview.cz/?lat=${picked.lat}&lon=${picked.lon}&zoom=14`}
						target="_blank">open on map</a
					>
					<button
						onclick={() =>
							navigator.clipboard.writeText(`${picked!.lat}, ${picked!.lon}`)}
						>copy</button
					>
				</div>
			{:else if sel?.status === 'done'}
				<div class="hint">scroll/pinch = zoom · drag = pan · click terrain = geo coords</div>
			{/if}
		</div>
	</div>
</section>

<style>
	.enqueue { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 1rem; }
	.split { display: grid; grid-template-columns: 320px 1fr; gap: 1rem; }
	.renders { list-style: none; padding: 0; margin: 0; overflow-y: auto; max-height: 70vh; }
	.renders li button { width: 100%; text-align: left; display: flex; flex-direction: column; }
	.renders li.active button { outline: 2px solid var(--accent, #4a90e2); }
	canvas { width: 100%; display: block; background: #16181c; cursor: crosshair; }
	.controls { display: flex; gap: 1.2rem; align-items: center; flex-wrap: wrap; padding: 0.5rem 0; }
	.picked { font-variant-numeric: tabular-nums; }
	.hint { opacity: 0.6; }
	.err { color: #d33; }
</style>
