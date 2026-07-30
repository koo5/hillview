<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { buildTileSource, type DziPyramid } from '$zoomview/tileSource';
	import { OSD_VIEWER_DEFAULTS, initialSourceFor, swapInMainSource } from '$zoomview/viewerInit';
	import '@annotorious/openseadragon/annotorious-openseadragon.css';
	import {
		buildLabelCommands,
		resolveOverlaps,
		LABEL_PAD,
		LABEL_PILL_H,
		LABEL_GAP,
		type LabelInput
	} from '$zoomview/labelLayout';
	import { paintLabels } from '$zoomview/labelPaint';

	export interface OsdRect {
		id: string;
		x: number; // normalized 0..1 of image width
		y: number;
		w: number;
		h: number;
		label?: string;
		kind?: 'current' | 'other';
	}
	/** Full-height vertical marker at a normalized x (proto-annotations, POI
	 *  previews) — drawn on the label canvas, optionally with an error band. */
	export interface OsdMark {
		id: string;
		x: number; // normalized 0..1 of image width
		color: string;
		label?: string;
		band?: [number, number]; // normalized x range, translucent fill
	}

	let {
		pyramid = null,
		url,
		fallbackUrl = null,
		width,
		height,
		rects = [],
		marks = [],
		focus = null,
		viewHeight = 380,
		onrectclick
	}: {
		pyramid?: DziPyramid | null;
		url: string;
		// small likely-browser-cached variant shown instantly while the main
		// source loads (the production viewer's progressive path, shared glue)
		fallbackUrl?: string | null;
		width: number;
		height: number;
		rects?: OsdRect[];
		marks?: OsdMark[];
		focus?: OsdRect | null; // zoom to this rect after open
		viewHeight?: number;
		onrectclick?: (id: string) => void;
	} = $props();

	let el: HTMLDivElement;
	let labelCanvas: HTMLCanvasElement;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let viewer: any = null;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let OSD: any = null;
	let resizeObserver: ResizeObserver | null = null;
	let labelRaf = 0;
	let lastFingerprint = '';

	// edge-label style (same base values as the frontend viewer, fixed scale 1)
	const LABEL_STYLE = {
		labelFont: 'bold 12px system-ui,sans-serif',
		labelPad: LABEL_PAD,
		leaderWidth: 1.5,
		leaderDash: 15,
		pillRadius: 4,
		textBaselineOffset: 5
	};
	const LABEL_MARGIN = 14;

	function scheduleLabels() {
		if (!labelRaf) {
			labelRaf = requestAnimationFrame(() => {
				labelRaf = 0;
				drawLabels();
			});
		}
	}

	// screen x of a normalized image x at the current viewport
	function screenX(x: number): number {
		return viewer.viewport.viewportToViewerElementCoordinates(new OSD.Point(x, 0)).x;
	}

	function drawLabels() {
		if (!labelCanvas || !viewer?.viewport) return;
		const W = labelCanvas.width;
		const H = labelCanvas.height;
		const ctx = labelCanvas.getContext('2d');
		if (!ctx) return;
		ctx.font = LABEL_STYLE.labelFont;

		const inputs: LabelInput[] = [];
		for (const r of rects) {
			if (!r.label) continue;
			const vp = vpRect(r);
			const sc = viewer.viewport.viewportToViewerElementCoordinates(
				new OSD.Point(vp.x + vp.width / 2, vp.y + vp.height / 2)
			);
			const pillW = ctx.measureText(r.label).width + LABEL_PAD * 2;
			inputs.push({ label: r.label, cx: Math.round(sc.x), cy: Math.round(sc.y), pillW, id: r.id });
		}
		const { cmds, fingerprint } = buildLabelCommands(inputs, W, H, LABEL_MARGIN, {
			pillH: LABEL_PILL_H
		});
		// marks move with the viewport too — fold their projected xs into the
		// skip fingerprint so pure pans still repaint them
		const markFp = marks.map((m) => `${m.id}@${Math.round(screenX(m.x))}`).join(';');
		if (fingerprint + '|' + markFp === lastFingerprint) return;
		lastFingerprint = fingerprint + '|' + markFp;
		resolveOverlaps(cmds, W, H, { gap: LABEL_GAP });
		paintLabels(ctx, W, H, cmds, LABEL_STYLE);
		paintMarks(ctx, W, H);
	}

	function paintMarks(ctx: CanvasRenderingContext2D, W: number, H: number) {
		for (const m of marks) {
			if (m.band) {
				const bx0 = screenX(m.band[0]);
				const bx1 = screenX(m.band[1]);
				if (bx1 >= 0 && bx0 <= W) {
					ctx.fillStyle = m.color;
					ctx.globalAlpha = 0.15;
					ctx.fillRect(bx0, 0, bx1 - bx0, H);
					ctx.globalAlpha = 1;
				}
			}
			const sx = screenX(m.x);
			if (sx < -2 || sx > W + 2) continue;
			ctx.fillStyle = m.color;
			ctx.fillRect(sx - 1, 0, 2, H);
			if (m.label) {
				const tw = ctx.measureText(m.label).width;
				const tx = Math.min(Math.max(sx + 4, 2), W - tw - 10);
				ctx.fillStyle = 'rgba(0,0,0,0.65)';
				ctx.fillRect(tx - 3, 2, tw + 8, 16);
				ctx.fillStyle = m.color;
				ctx.fillText(m.label, tx, 14);
			}
		}
	}

	// normalized image rect → OSD viewport rect (viewport width ≡ 1, y scaled by aspect)
	const aspect = () => height / width;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	function vpRect(r: { x: number; y: number; w: number; h: number }): any {
		return new OSD.Rect(r.x, r.y * aspect(), r.w, r.h * aspect());
	}

	function fitRect(r: OsdRect, pad = 1.0) {
		if (!viewer) return;
		const v = vpRect(r);
		// pad around the rect; for sliver rects keep a sensible minimum height
		const grown = new OSD.Rect(
			v.x - v.width * pad * 0.5,
			v.y - v.height * pad * 0.5,
			v.width * (1 + pad),
			v.height * (1 + pad)
		);
		viewer.viewport.fitBounds(grown, true);
	}
	function fitAll() {
		viewer?.viewport.goHome(true);
	}

	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let annotator: any = null;
	const kindById = () => new Map(rects.map((r) => [r.id, r.kind ?? 'other']));

	// rects → annotorious annotations. NB: annotorious's internal format REQUIRES
	// pixel-space `geometry.bounds` (its spatial index reads it directly) — the
	// main app's DB targets carry bounds because annotorious wrote them at
	// creation; synthetic targets must compute them or the rect silently never
	// renders (labels fine, rect invisible — debugged the hard way).
	function syncRects() {
		if (!annotator) return;
		const anns = rects.map((r) => {
			const px = { x: r.x * width, y: r.y * height, w: r.w * width, h: r.h * height };
			return {
				'@context': 'http://www.w3.org/ns/anno.jsonld',
				id: r.id,
				type: 'Annotation',
				body: r.label ? [{ type: 'TextualBody', value: r.label, purpose: 'commenting' }] : [],
				target: {
					selector: {
						type: 'RECTANGLE',
						geometry: {
							...px,
							bounds: { minX: px.x, minY: px.y, maxX: px.x + px.w, maxY: px.y + px.h }
						}
					}
				}
			};
		});
		try {
			annotator.setAnnotations(anns);
		} catch (e) {
			console.warn('[OsdViewer] could not sync annotations:', e);
		}
	}

	onMount(async () => {
		const [osdMod, annoMod] = await Promise.all([
			import('openseadragon'),
			import('@annotorious/openseadragon')
		]);
		OSD = osdMod.default;
		const { createOSDAnnotator } = annoMod;
		const initial = initialSourceFor(fallbackUrl, pyramid, url);
		viewer = new OSD.Viewer({
			...OSD_VIEWER_DEFAULTS,
			element: el,
			tileSources: initial.source,
			// workbench overrides: keep the little navigator strip, load harder
			showNavigator: true,
			navigatorPosition: 'BOTTOM_RIGHT',
			navigatorHeight: 40,
			navigatorWidth: 220,
			imageLoaderLimit: 2
		});
		// read-only annotorious mount: rect rendering + selection, no drawing
		annotator = createOSDAnnotator(viewer, {
			style: (a: { id?: string }) =>
				kindById().get(a?.id ?? '') === 'current'
					? { fill: '#6ca4ff', fillOpacity: 0.08, stroke: '#6ca4ff', strokeWidth: 2, strokeOpacity: 0.9 }
					: { fill: '#e0a23a', fillOpacity: 0.05, stroke: '#e0a23a', strokeWidth: 1.5, strokeOpacity: 0.7 }
		});
		if (onrectclick) {
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			annotator.on('clickAnnotation', (a: any) => onrectclick(String(a.id)));
		}

		viewer.addHandler('open', () => {
			syncRects();
			if (focus) fitRect(focus);
			scheduleLabels();
			if (initial.usingFallback) {
				// after the main source joins the world, re-sync so annotorious
				// rects are anchored against the full-size image space
				viewer.world.addHandler('add-item', () => setTimeout(syncRects, 0));
				swapInMainSource(viewer, buildTileSource(pyramid, url));
			}
		});
		viewer.addHandler('viewport-change', scheduleLabels);
		viewer.addHandler('update-viewport', scheduleLabels);

		resizeObserver = new ResizeObserver(() => {
			if (!labelCanvas) return;
			labelCanvas.width = el.offsetWidth;
			labelCanvas.height = el.offsetHeight;
			lastFingerprint = '';
			scheduleLabels();
		});
		resizeObserver.observe(el);
	});
	// rects/marks can change after mount (async loads, live previews) — re-sync
	// annotorious and force a canvas repaint when they do
	$effect(() => {
		void rects;
		void marks;
		if (viewer) {
			syncRects();
			lastFingerprint = '';
			scheduleLabels();
		}
	});

	onDestroy(() => {
		if (labelRaf) cancelAnimationFrame(labelRaf);
		resizeObserver?.disconnect();
		annotator?.destroy();
		viewer?.destroy();
	});
</script>

<div style="position:relative">
	<div bind:this={el} style="height:{viewHeight}px; background:#000; border-radius:8px"></div>
	<canvas
		bind:this={labelCanvas}
		style="position:absolute; inset:0; pointer-events:none; z-index:5; border-radius:8px"
	></canvas>
	<div class="osd-btns">
		{#if focus}
			<button onclick={() => focus && fitRect(focus)} title="zoom to the annotation rect">rect</button>
		{/if}
		<button onclick={fitAll} title="fit whole image">fit</button>
	</div>
</div>

<style>
	.osd-btns {
		position: absolute;
		top: 8px;
		right: 8px;
		display: flex;
		gap: 6px;
		z-index: 10;
	}
	.osd-btns button {
		font-size: 11px;
		padding: 2px 10px;
		background: rgba(0, 0, 0, 0.6);
		border: 1px solid var(--border, rgba(255, 255, 255, 0.4));
		color: var(--fg, #fff);
		border-radius: 6px;
		cursor: pointer;
	}
</style>
