<script lang="ts">
	// SHARED Svelte wrapper around the depth-panorama viewer core — consumed
	// by BOTH apps ($terrain alias): the main frontend's TerrainPane and the
	// enrichment workbench's terrain bench. Like the rest of shared/terrain
	// it imports only 'svelte' + $terrain/$zoomview aliases, never $lib.
	// Renders a synthetic terrain view for a viewpoint with live Koschmieder
	// fog and OSM peak labels; clicks come back as geo coordinates via
	// onpick (sky clicks snap to the horizon in the core).
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
		compassTicks,
		DepthPanoViewer,
		destinationPoint,
		normalizeRect,
		type TerrainMeta,
		type TerrainPick,
		type ViewRect
	} from '$terrain/depthPanoViewer';
	import {
		hitSkyLabel,
		layoutSkyLabels,
		projectPeaks,
		texToCanvas,
		type Peak,
		type PeakMark,
		type SkyLabel
	} from '$terrain/peakLabels';
	import { LABEL_PAD } from '$zoomview/labelLayout';
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
		showPeakLabels = $bindable(true),
		peakTolerance = $bindable(0.06),
		exaggeration = $bindable(1),
		canvasTestId = undefined,
		onviewer = undefined
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
		/** relative depth tolerance for the peak-visibility match — looser
		 * shows more labels (see peakLabels.PEAK_DEPTH_REL_TOL) */
		peakTolerance?: number;
		/** vertical exaggeration (display-only stretch; 1 = true angles).
		 * Depths/picks/occlusion are untouched — see core setExaggeration. */
		exaggeration?: number;
		/** optional data-testid for the GL canvas (the bench e2e suite
		 * addresses it as terrain-canvas) */
		canvasTestId?: string;
		/** called with the live core instance after construction — e2e
		 * instrumentation handle (readPixel/getRect), nothing app-facing */
		onviewer?: (v: DepthPanoViewer) => void;
	} = $props();

	let canvas: HTMLCanvasElement;
	let labelCanvas: HTMLCanvasElement;
	let viewer: DepthPanoViewer | null = null;
	let error = $state<string | null>(null);
	let loading = $state(true);
	let marks: PeakMark[] = [];
	// pills currently on screen, with their marks — labels are CLICKABLE:
	// a tap on a pill picks that exact feature (geodesic distance, name)
	let placedLabels: { pill: SkyLabel; mark: PeakMark }[] = [];
	let tapX = 0;
	let tapY = 0;

	// zoomview label PAINTER, same style as the photo zoom view; placement
	// is the terrain-specific sky layouter (layoutSkyLabels)
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
		marks = m && d && peaks.length ? projectPeaks(m, d, peaks, peakTolerance) : [];
	}

	function repaintLabels(): void {
		if (!labelCanvas) return;
		const m = viewer?.getMetaData();
		const rect = viewer?.getRect();
		const W = canvas.clientWidth;
		const H = canvas.clientHeight;
		// backing store at devicePixelRatio: a CSS-resolution overlay is
		// blurry on phones and its 1px compass ticks shimmer ("jump")
		// between physical pixels while panning
		const dpr = globalThis.devicePixelRatio ?? 1;
		const bw = Math.round(W * dpr);
		const bh = Math.round(H * dpr);
		if (labelCanvas.width !== bw || labelCanvas.height !== bh) {
			labelCanvas.width = bw;
			labelCanvas.height = bh;
		}
		const ctx = labelCanvas.getContext('2d');
		if (!ctx) return;
		ctx.setTransform(dpr, 0, 0, dpr, 0, 0); // draw in CSS units
		if (!m || !rect || !W || !H) {
			ctx.clearRect(0, 0, labelCanvas.width, labelCanvas.height);
			return;
		}
		if (showPeakLabels && marks.length) {
			ctx.font = LABEL_STYLE.labelFont;
			const inputs = [];
			const visible: PeakMark[] = [];
			// generous cap: the layouter's per-neighborhood thinning is the
			// real display limit — a hard slice-40 under a saturated pool made
			// tolerance trade near labels for far ones instead of adding
			for (const mark of marks.slice(0, 150)) {
				const p = texToCanvas(m, rect, mark.u, mark.v, W, H);
				if (!p) continue;
				const label = mark.ele ? `${mark.name} ${Math.round(mark.ele)}` : mark.name;
				inputs.push({
					label,
					cx: p.cx,
					cy: p.cy,
					pillW: ctx.measureText(label).width + LABEL_PAD * 2,
					id: String(visible.length)
				});
				visible.push(mark);
			}
			// vista-board placement: pills in the sky above their summits (never
			// covering them), stacked upward on crowding; the painter's
			// edge:'bottom' case is exactly leader-up-to-pill-bottom geometry
			const placed = layoutSkyLabels(inputs, W, H);
			placedLabels = placed.map((pill) => ({ pill, mark: visible[Number(pill.id)] }));
			paintLabels(
				ctx,
				W,
				H,
				placed.map((c) => ({ ...c, lx: c.cx, ly: c.cy, edge: 'bottom' as const })),
				LABEL_STYLE
			);
		} else {
			placedLabels = [];
			ctx.clearRect(0, 0, W, H); // paintLabels clears when it runs
		}
		paintCompass(ctx, m, rect, W, H);
	}

	/** Azimuth ruler along the canvas bottom — cardinals at 45°, adaptive
	 * minor ticks, degree labels when zoomed in. Painted over the labels
	 * layer so it rides every view change for free. */
	function paintCompass(
		ctx: CanvasRenderingContext2D,
		m: TerrainMeta,
		rect: ViewRect,
		W: number,
		H: number
	): void {
		ctx.save();
		ctx.setLineDash([]);
		ctx.font = 'bold 10px system-ui,sans-serif';
		ctx.textAlign = 'center';
		for (const t of compassTicks(m, rect, W)) {
			const x = Math.round(t.x) + 0.5; // pixel-snap: unsnapped 1px lines shimmer
			const h = t.major ? 10 : 5;
			for (const [width, color] of [
				[3, 'rgba(0,0,0,0.7)'],
				[1.2, 'rgba(255,255,255,0.9)']
			] as const) {
				ctx.beginPath();
				ctx.moveTo(x, H);
				ctx.lineTo(x, H - h);
				ctx.lineWidth = width;
				ctx.strokeStyle = color;
				ctx.stroke();
			}
			if (t.label) {
				ctx.lineWidth = 3;
				ctx.strokeStyle = 'rgba(0,0,0,0.8)';
				ctx.strokeText(t.label, Math.round(t.x), H - h - 3);
				ctx.fillStyle = t.major ? '#fff' : 'rgba(255,255,255,0.85)';
				ctx.fillText(t.label, Math.round(t.x), H - h - 3);
			}
		}
		ctx.restore();
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
			onviewer?.(viewer);
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

	// live fog re-shade — no re-render, just a uniform update. Read the params
	// BEFORE the null-check: `viewer?.` short-circuiting on the first run
	// would leave the effect with zero tracked dependencies, so the sliders
	// would never re-trigger it (viewer itself is deliberately non-reactive).
	$effect(() => {
		const fog = { visibilityKm, skyColor };
		viewer?.setFog(fog);
	});

	// live vertical exaggeration — same read-before-null-check rule
	$effect(() => {
		const e = exaggeration;
		viewer?.setExaggeration(e);
	});

	// peaks / toggle / tolerance changes: re-project against the loaded
	// depth + repaint (projection is a cheap per-candidate column scan)
	$effect(() => {
		void peaks;
		void showPeakLabels;
		void peakTolerance;
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

	// Label taps: the overlay canvas is pointer-events:none, so clicks reach
	// the GL canvas and bubble here. The core's own (depth-based) pick fires
	// first on pointerup; when the tap actually hit a pill, this click
	// handler follows up with the EXACT pick for that feature — geodesic
	// distance and name, immune to label stacking. Movement guard keeps
	// drags from picking.
	function onWrapPointerDown(e: PointerEvent): void {
		tapX = e.clientX;
		tapY = e.clientY;
	}

	function onWrapClick(e: MouseEvent): void {
		if (Math.hypot(e.clientX - tapX, e.clientY - tapY) > 5) return;
		const m = viewer?.getMetaData();
		if (!m || !placedLabels.length || !onpick) return;
		const r = canvas.getBoundingClientRect();
		const hitPill = hitSkyLabel(
			placedLabels.map((p) => p.pill),
			e.clientX - r.left,
			e.clientY - r.top
		);
		if (!hitPill) return;
		const mark = placedLabels.find((p) => p.pill === hitPill)!.mark;
		const geo = destinationPoint(m.lat, m.lon, mark.azimuth_deg, mark.distance_m);
		onpick({
			lat: geo.lat,
			lon: geo.lon,
			distance_m: mark.distance_m,
			azimuth_deg: mark.azimuth_deg,
			col: Math.min(m.width - 1, Math.floor(mark.u * m.width)),
			row: Math.min(m.height - 1, Math.floor(mark.v * m.height)),
			label: mark.name
		});
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions, a11y_click_events_have_key_events -->
<div class="terrain-viewer" onpointerdown={onWrapPointerDown} onclick={onWrapClick}>
	<canvas data-testid={canvasTestId} bind:this={canvas}></canvas>
	<canvas class="labels" bind:this={labelCanvas}></canvas>
	{#if loading && !error}<div class="overlay">loading render…</div>{/if}
	{#if error}<div class="overlay error">{error}</div>{/if}
</div>

<style>
	.terrain-viewer {
		position: relative;
		width: 100%;
		/* fill the pane (flex column): the canvas box is what decides the
		   viewer's vertical FOV — the core no longer locks it to the texture
		   aspect, so zoom can grow the strip into this space */
		flex: 1;
		min-height: 0;
	}
	canvas {
		width: 100%;
		height: 100%;
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
