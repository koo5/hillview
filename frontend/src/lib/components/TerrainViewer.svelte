<script lang="ts">
	// Thin Svelte wrapper around the shared depth-panorama viewer core
	// ($terrain/depthPanoViewer — same code the enrichment workbench bench
	// uses). Renders a synthetic terrain view for a photo's viewpoint with
	// live Koschmieder fog; clicks on terrain come back as geo coordinates
	// via onpick, ready to fly the map (see MapView's flyTo / photo pane).
	//
	// Touch-ready: the core handles wheel zoom, drag pan, and two-finger
	// pinch through Pointer Events, so this works in the Tauri Android app.
	//
	// Data contract (renderer.py artifacts): previewUrl (shaded JPEG,
	// no fog baked in), depthUrl (raw little-endian uint16, 0 = sky),
	// meta (grid geometry + viewpoint). Today these come from the
	// enrichment workbench API; the graduation path is the main backend
	// serving them next to the photo pyramids.
	import { onMount, untrack } from 'svelte';
	import {
		DepthPanoViewer,
		normalizeRect,
		type TerrainMeta,
		type TerrainPick,
		type ViewRect
	} from '$terrain/depthPanoViewer';

	let {
		previewUrl,
		depthUrl,
		meta,
		visibilityKm = $bindable(80),
		skyColor = $bindable('#a7cdf0'),
		onpick,
		initialRect,
		onviewchange
	}: {
		previewUrl: string;
		depthUrl: string;
		meta: TerrainMeta;
		visibilityKm?: number;
		skyColor?: string;
		onpick?: (pick: TerrainPick | null) => void;
		/** viewport rect to restore (zoom view's x1..y2 convention, e.g. from
		 * URL params); normalized here, so seam-straddling x is fine */
		initialRect?: ViewRect | null;
		/** user-driven viewport changes, for URL sync — never echoes setRect */
		onviewchange?: (rect: ViewRect) => void;
	} = $props();

	let canvas: HTMLCanvasElement;
	let viewer: DepthPanoViewer | null = null;
	let error = $state<string | null>(null);
	let loading = $state(true);

	onMount(() => {
		try {
			viewer = new DepthPanoViewer(canvas, {
				onPick: (p) => onpick?.(p),
				onViewChange: (r) => onviewchange?.(r)
			});
			if (initialRect) viewer.setRect(normalizeRect(initialRect)); // applied on load
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			return;
		}
		return () => {
			viewer?.destroy();
			viewer = null;
		};
	});

	// (re)load when the artifact sources change. Only the URLS are tracked:
	// meta arrives as a fresh object identity on every renders poll, and
	// tracking it would re-download MBs per tick — the pane versions the
	// URLs (artifactVersion) precisely when new bytes exist.
	$effect(() => {
		const v = viewer;
		const src = { previewUrl, depthUrl, meta: untrack(() => meta) };
		if (!v || !src.previewUrl || !src.depthUrl || !src.meta) return;
		loading = true;
		error = null;
		v.load(src)
			.then(() => {
				loading = false;
				v.setFog({ visibilityKm, skyColor });
			})
			.catch((e) => {
				loading = false;
				error = e instanceof Error ? e.message : String(e);
			});
	});

	// live fog re-shade — no re-render, just a uniform update
	$effect(() => {
		viewer?.setFog({ visibilityKm, skyColor });
	});

	export function resetView(): void {
		viewer?.resetView();
	}

	export function setRect(rect: ViewRect): void {
		viewer?.setRect(normalizeRect(rect));
	}

	export function getRect(): ViewRect | null {
		return viewer?.getRect() ?? null;
	}
</script>

<div class="terrain-viewer">
	<canvas bind:this={canvas}></canvas>
	{#if loading && !error}<div class="overlay">rendering terrain…</div>{/if}
	{#if error}<div class="overlay error">{error}</div>{/if}
</div>

<style>
	.terrain-viewer {
		position: relative;
		width: 100%;
	}
	canvas {
		width: 100%;
		display: block;
		background: #16181c;
		cursor: crosshair;
	}
	.overlay {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #ccc;
		font-size: 0.9rem;
		pointer-events: none;
	}
	.overlay.error {
		color: #e77;
	}
</style>
