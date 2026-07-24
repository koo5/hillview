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
	import { projectPeaks, texToCanvas, type Peak, type PeakMark } from '$terrain/peakLabels';
	import {
		buildLabelCommands,
		resolveOverlaps,
		LABEL_PAD
	} from '$zoomview/labelLayout';
	import { paintLabels } from '$zoomview/labelPaint';

	let {
		previewUrl,
		depthUrl,
		meta,
		visibilityKm = $bindable(80),
		skyColor = $bindable('#a7cdf0'),
		onpick,
		initialRect,
		onviewchange,
		peaks = [],
		showPeakLabels = $bindable(true)
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
		/** OSM natural=peak candidates near the viewpoint; visibility is
		 * decided here against the depth buffer (terrain-mode v2) */
		peaks?: Peak[];
		showPeakLabels?: boolean;
	} = $props();

	let canvas: HTMLCanvasElement;
	let labelCanvas: HTMLCanvasElement;
	let viewer: DepthPanoViewer | null = null;
	let error = $state<string | null>(null);
	let loading = $state(true);
	let marks: PeakMark[] = [];

	// zoomview label pipeline, same style as the photo zoom view
	const LABEL_MARGIN = 14;
	const LABEL_STYLE = {
		labelFont: 'bold 12px system-ui,sans-serif',
		labelPad: LABEL_PAD,
		leaderWidth: 1.5,
		leaderDash: 4,
		pillRadius: 4,
		textBaselineOffset: 4
	};

	function recomputeMarks(): void {
		const m = viewer?.getMetaData();
		const d = viewer?.getDepthData();
		marks = m && d && peaks.length ? projectPeaks(m, d, peaks) : [];
	}

	function repaintLabels(): void {
		if (!labelCanvas) return;
		const m = viewer?.getMetaData();
		const rect = viewer?.getRect();
		const W = canvas.clientWidth;
		const H = canvas.clientHeight;
		if (labelCanvas.width !== W || labelCanvas.height !== H) {
			labelCanvas.width = W;
			labelCanvas.height = H;
		}
		const ctx = labelCanvas.getContext('2d');
		if (!ctx) return;
		if (!m || !rect || !showPeakLabels || !marks.length || !W || !H) {
			ctx.clearRect(0, 0, labelCanvas.width, labelCanvas.height);
			return;
		}
		ctx.font = LABEL_STYLE.labelFont;
		const inputs = [];
		for (const mark of marks.slice(0, 40)) {
			const p = texToCanvas(m, rect, mark.u, mark.v, W, H);
			if (!p) continue;
			const label = mark.ele ? `${mark.name} ${Math.round(mark.ele)}` : mark.name;
			inputs.push({
				label,
				cx: p.cx,
				cy: p.cy,
				pillW: ctx.measureText(label).width + LABEL_PAD * 2,
				id: mark.name
			});
		}
		const { cmds } = buildLabelCommands(inputs, W, H, LABEL_MARGIN);
		resolveOverlaps(cmds, W, H);
		paintLabels(ctx, W, H, cmds, LABEL_STYLE);
	}

	onMount(() => {
		try {
			viewer = new DepthPanoViewer(canvas, {
				onPick: (p) => onpick?.(p),
				onViewChange: (r) => {
					onviewchange?.(r);
					repaintLabels(); // labels ride the viewport
				}
			});
			if (initialRect) viewer.setRect(normalizeRect(initialRect)); // applied on load
			const ro = new ResizeObserver(() => repaintLabels());
			ro.observe(canvas);
			resizeObserver = ro;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			return;
		}
		return () => {
			resizeObserver?.disconnect();
			viewer?.destroy();
			viewer = null;
		};
	});
	let resizeObserver: ResizeObserver | null = null;

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
				recomputeMarks();
				repaintLabels();
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

	// peaks / toggle changes: re-project against the loaded depth + repaint
	$effect(() => {
		void peaks;
		void showPeakLabels;
		recomputeMarks();
		repaintLabels();
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
	<canvas class="labels" bind:this={labelCanvas}></canvas>
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
	canvas.labels {
		position: absolute;
		inset: 0;
		height: 100%;
		background: transparent;
		pointer-events: none;
		cursor: default;
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
