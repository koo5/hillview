<script lang="ts">
	/**
	 * OpenSeadragonViewer.svelte
	 *
	 * Full-screen deep-zoom viewer powered by OpenSeadragon.
	 * When the photo has a DZI pyramid (sizes.full.pyramid), it is used for
	 * tile-based deep zoom so the viewer can show the image progressively
	 * without waiting for the full file to download.
	 *
	 * When no pyramid is available, the viewer falls back to a single full-size
	 * image as a Simple Image source so OpenSeadragon still provides pan/zoom.
	 *
	 * Annotorious is mounted on top of the viewer to allow users to create,
	 * view, and edit annotations.  Each edit supersedes the old annotation
	 * (creates a new DB row, marks the old one is_current=false) to preserve
	 * edit history.
	 *
	 * Edge labels: a transparent <canvas> overlays the OSD container and is
	 * redrawn on every viewport-change event.  For each annotation the centroid
	 * is projected from image→screen space; the label is drawn near the nearest
	 * screen edge, connected to the centroid by a leader line.
	 *
	 * Background close: clicking/tapping the black area outside the image
	 * closes the viewer (mirroring the original ZoomView behaviour).
	 */
	import { onMount, onDestroy } from 'svelte';
	import { auth } from '$lib/auth.svelte.js';
	import {
		fetchAnnotations,
		createAnnotation,
		updateAnnotation,
		deleteAnnotation,
		type AnnotationData,
	} from '$lib/annotationApi';
	import type { ZoomViewData } from '$lib/zoomView.svelte';

	export let data: ZoomViewData;
	export let onClose: () => void;

	let container: HTMLDivElement;
	let viewer: any = null;
	let annotator: any = null;
	let annotations: AnnotationData[] = [];
	let annotatingEnabled = false;
	let selectedAnnotation: AnnotationData | null = null;
	let editingAnnotation: AnnotationData | null = null;
	let editBody = '';
	let errorMessage = '';
	let isLoading = true;
	let labelCanvas: HTMLCanvasElement | null = null;
	let resizeObserver: ResizeObserver | null = null;

	$: isAuthenticated = $auth.is_authenticated;

	async function loadAnnotations() {
		if (!data.photo_id) return;
		try {
			annotations = await fetchAnnotations(data.photo_id);
			syncAnnotationsToViewer();
		} catch (e) {
			console.error('[OSD] Failed to load annotations:', e);
		}
	}

	function syncAnnotationsToViewer() {
		if (!annotator) return;
		try {
			// Clear existing and re-add from server state
			annotator.setAnnotations(
				annotations
					.filter((a) => a.target)
					.map((a) => ({
						'@context': 'http://www.w3.org/ns/anno.jsonld',
						id: a.id,
						type: 'Annotation',
						body: a.body
							? [{ type: 'TextualBody', value: a.body, purpose: 'commenting' }]
							: [],
						target: a.target,
					}))
			);
		} catch (e) {
			console.warn('[OSD] Could not sync annotations to viewer:', e);
		}
		drawLabels();
	}

	/**
	 * Compute the lowest DZI level whose image is at least tile_size pixels
	 * on its longest side.  Levels below this are single sub-tile images —
	 * fetching them is wasteful (one HTTP request each for a tiny image that
	 * OSD never even displays at normal zoom).
	 */
	function computeMinLevel(width: number, height: number, tileSize: number): number {
		const maxDim = Math.max(width, height);
		const maxLevel = Math.ceil(Math.log2(maxDim));
		// Walk from the top level down; the first level where the image fits
		// in a single tile is the last one we want.  Everything below is waste.
		for (let level = maxLevel; level >= 0; level--) {
			const levelDim = Math.ceil(maxDim / Math.pow(2, maxLevel - level));
			if (levelDim <= tileSize) return level;
		}
		return 0;
	}

	function buildTileSource() {
		const p = data.pyramid;
		if (p && p.type === 'dzi') {
			const minLevel = computeMinLevel(p.width, p.height, p.tile_size);
			console.log('[OSD] Using DZI pyramid for tile source:', p, '| minLevel:', minLevel);
			return {
				Image: {
					xmlns: 'http://schemas.microsoft.com/deepzoom/2008',
					Url: p.tiles_url + '/',
					Format: p.format,
					Overlap: String(p.overlap),
					TileSize: String(p.tile_size),
					Size: {
						Width: String(p.width),
						Height: String(p.height),
					},
				},
				minLevel,
			};
		}
		// Fallback: single full-size image
		console.warn('[OSD] No DZI pyramid available, falling back to single-image source: ', JSON.stringify(p));
		return {
			type: 'image',
			url: data.url,
		};
	}

	/**
	 * Draw edge-label callouts for all current annotations onto the label canvas.
	 * Each annotation's centroid is projected from image→screen space.  The label
	 * is placed near the nearest screen edge and connected to the centroid with a
	 * leader line.  Safe to call when viewer or canvas is not yet ready.
	 */
	function drawLabels() {
		if (!labelCanvas || !viewer?.viewport) return;
		const ctx = labelCanvas.getContext('2d');
		if (!ctx) return;
		const W = labelCanvas.width;
		const H = labelCanvas.height;
		ctx.clearRect(0, 0, W, H);

		for (const ann of annotations) {
			const label = ann.body;
			if (!label) continue;

			// Support both a single selector object and an array of selectors;
			// find the first fragment selector in case of mixed-type arrays
			const raw = ann.target as any;
			const selectorList: any[] = Array.isArray(raw?.selector)
				? raw.selector
				: raw?.selector
					? [raw.selector]
					: [];
			const selector = selectorList.find(
				(s: any) => typeof s?.value === 'string' && s.value.includes('xywh=pixel:')
			);
			if (!selector) continue;

			// Only handle the fragment selector produced by Annotorious rectangles
			const match = (selector.value as string).match(
				/xywh=pixel:([\d.]+),([\d.]+),([\d.]+),([\d.]+)/
			);
			if (!match) continue;
			const [, sx, sy, sw, sh] = match.map(Number);

			// Project centroid: image pixels → viewport fraction → screen pixels
			const vpPt = viewer.viewport.imageToViewportCoordinates(sx + sw / 2, sy + sh / 2);
			const scPt = viewer.viewport.viewportToViewerElementCoordinates(vpPt);
			const cx = scPt.x;
			const cy = scPt.y;
			// Skip if the centroid is off-screen
			if (cx < 0 || cx > W || cy < 0 || cy > H) continue;

			// Find the nearest edge and set the label anchor point
			const margin = 14;
			const dLeft = cx;
			const dRight = W - cx;
			const dTop = cy;
			const dBottom = H - cy;
			const nearest = Math.min(dLeft, dRight, dTop, dBottom);
			let lx = cx;
			let ly = cy;
			if (nearest === dLeft)       lx = margin;
			else if (nearest === dRight) lx = W - margin;
			else if (nearest === dTop)   ly = margin;
			else                         ly = H - margin;

			// Leader line from centroid to label anchor
			ctx.beginPath();
			ctx.moveTo(cx, cy);
			ctx.lineTo(lx, ly);
			ctx.strokeStyle = 'rgba(255,230,50,0.9)';
			ctx.lineWidth = 1.5;
			ctx.stroke();

			// Label pill: pill is drawn to the left of the anchor on right-edge labels
			ctx.font = 'bold 12px system-ui,sans-serif';
			const tw = ctx.measureText(label).width;
			const pad = 6;
			const pillW = tw + pad * 2;
			const pillH = 20;
			const tx = lx > W / 2 ? lx - pillW : lx;
			const ty = ly > H / 2 ? ly - pillH : ly;
			ctx.fillStyle = 'rgba(0,0,0,0.75)';
			ctx.beginPath();
			if (typeof (ctx as any).roundRect === 'function') {
				(ctx as any).roundRect(tx, ty, pillW, pillH, 4);
			} else {
				ctx.rect(tx, ty, pillW, pillH);
			}
			ctx.fill();
			ctx.fillStyle = '#fff';
			ctx.fillText(label, tx + pad, ty + pillH - 5);
		}
	}

	onMount(async () => {
		const [OSD, { createOSDAnnotator }] = await Promise.all([
			import('openseadragon'),
			import('@annotorious/openseadragon'),
		]);
		const OpenSeadragon = OSD.default ?? OSD;

		viewer = new OpenSeadragon.Viewer({
			element: container,
			tileSources: buildTileSource(),
			// Disable default controls – we supply our own close button
			showNavigationControl: false,
			showNavigator: false,
			animationTime: 0.3,
			// Allow dragging even without a button press (touch-friendly)
			gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true },
			gestureSettingsTouch: { clickToZoom: false, dblClickToZoom: true },
			immediateRender: false,
			imageLoaderLimit: 1,
			debugMode: true
		});

		viewer.addHandler('open', () => {
			isLoading = false;
		});

		viewer.addHandler('open-failed', () => {
			isLoading = false;
			errorMessage = 'Failed to load image';
		});

		// Mount Annotorious on the OSD viewer
		// Drawing starts disabled; the toolbar toggle enables it for authenticated users.
		annotator = createOSDAnnotator(viewer, {
			drawingEnabled: false,
		});

		// When the user finishes drawing a shape, open the text-entry dialog
		annotator.on('createAnnotation', async (annotation: any) => {
			const textBody =
				(annotation.body?.find((b: any) => b.purpose === 'commenting')?.value) ?? '';
			// If the annotation already carries a body (e.g. from a tool), use it;
			// otherwise prompt the user.  Pressing Cancel returns null → discard the shape.
			const prompted = textBody || window.prompt('Add a label for this annotation:');
			if (prompted === null) {
				// User cancelled – remove the shape
				annotator.removeAnnotation(annotation);
				return;
			}
			const body = prompted;
			try {
				const saved = await createAnnotation(data.photo_id!, {
					body,
					target: annotation.target,
				});
				annotations = [...annotations, saved];
				// Replace the temporary client-side id with the server-assigned id
				annotator.removeAnnotation(annotation);
				annotator.addAnnotation({
					...annotation,
					id: saved.id,
					body: [{ type: 'TextualBody', value: body, purpose: 'commenting' }],
				});
				drawLabels();
			} catch (e) {
				console.error('[OSD] Failed to save annotation:', e);
				annotator.removeAnnotation(annotation);
			}
		});

		annotator.on('updateAnnotation', async (annotation: any, previous: any) => {
			const body =
				annotation.body?.find((b: any) => b.purpose === 'commenting')?.value ?? '';
			try {
				const saved = await updateAnnotation(previous.id, {
					body,
					target: annotation.target,
				});
				annotations = annotations
					.filter((a) => a.id !== previous.id)
					.concat(saved);
				drawLabels();
			} catch (e) {
				console.error('[OSD] Failed to update annotation:', e);
			}
		});

		annotator.on('deleteAnnotation', async (annotation: any) => {
			try {
				await deleteAnnotation(annotation.id);
				annotations = annotations.filter((a) => a.id !== annotation.id);
				drawLabels();
			} catch (e) {
				console.error('[OSD] Failed to delete annotation:', e);
			}
		});

		// The canvas is created imperatively so it can't use Svelte scoped styles;
		// inline style is intentional here.
		labelCanvas = document.createElement('canvas');
		labelCanvas.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:2';
		container.appendChild(labelCanvas);

		resizeObserver = new ResizeObserver(() => {
			if (!labelCanvas) return;
			labelCanvas.width  = container.offsetWidth;
			labelCanvas.height = container.offsetHeight;
			drawLabels();
		});
		resizeObserver.observe(container);

		viewer.addHandler('viewport-change', drawLabels);
		viewer.addHandler('update-viewport',  drawLabels);

		// Close the viewer when the user clicks/taps the black background
		// outside the image bounds (mirrors original ZoomView behaviour).
		// event.quick distinguishes a tap/click from a pan/zoom drag — OSD sets
		// quick=false when the pointer moved significantly before release.
		viewer.addHandler('canvas-click', (event: any) => {
			if (!event.quick || annotatingEnabled) return;
			const item = viewer.world.getItemAt(0);
			if (!item) { onClose(); return; }
			const imgBounds = item.getBounds(); // viewport coordinates
			const scrBounds = viewer.viewport.viewportToViewerElementRectangle(imgBounds);
			const pt = event.position; // viewer-element coordinates
			if (
				pt.x < scrBounds.x ||
				pt.x > scrBounds.x + scrBounds.width ||
				pt.y < scrBounds.y ||
				pt.y > scrBounds.y + scrBounds.height
			) {
				onClose();
			}
		});

		// Load annotations after viewer is ready
		if (data.photo_id) {
			loadAnnotations();
		}
	});

	onDestroy(() => {
		resizeObserver?.disconnect();
		viewer?.removeHandler('viewport-change', drawLabels);
		viewer?.removeHandler('update-viewport',  drawLabels);
		annotator?.destroy?.();
		viewer?.destroy?.();
	});

	function toggleAnnotating() {
		if (!annotator) return;
		annotatingEnabled = !annotatingEnabled;
		annotator.setDrawingEnabled(annotatingEnabled);
		if (annotatingEnabled) {
			annotator.setDrawingTool('rectangle');
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="osd-overlay" data-testid="osd-viewer-overlay">
	<!-- Close button -->
	<button class="close-btn" onclick={onClose} aria-label="Close zoom view" data-testid="osd-viewer-close">
		<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
			<path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
		</svg>
	</button>

	<!-- Annotation toolbar (authenticated users only) -->
	{#if isAuthenticated}
		<div class="annotation-toolbar">
			<button
				class="toolbar-btn"
				class:active={annotatingEnabled}
				onclick={toggleAnnotating}
				title={annotatingEnabled ? 'Stop annotating' : 'Draw annotation'}
				data-testid="osd-annotate-toggle"
			>
				✏️ {annotatingEnabled ? 'Cancel' : 'Annotate'}
			</button>
		</div>
	{/if}

	<!-- Loading indicator -->
	{#if isLoading}
		<div class="loading-overlay">
			<div class="spinner"></div>
		</div>
	{/if}

	<!-- Error message -->
	{#if errorMessage}
		<div class="error-banner">{errorMessage}</div>
	{/if}

	<!-- OpenSeadragon container -->
	<div bind:this={container} class="osd-container"></div>

	<!-- Filename bar -->
	<div class="filename-bar">{data.filename}</div>
</div>

<style>
	.osd-overlay {
		position: fixed;
		inset: 0;
		background: #000;
		z-index: 999999;
		display: flex;
		flex-direction: column;
	}

	.osd-container {
		flex: 1;
		width: 100%;
		height: 100%;
		position: relative;
	}

	/* Annotorious CSS is imported in the parent component */

	.close-btn {
		position: absolute;
		top: calc(12px + var(--safe-area-inset-top, 0px));
		right: calc(12px + var(--safe-area-inset-right, 0px));
		z-index: 10;
		background: rgba(255,255,255,0.85);
		border: none;
		border-radius: 50%;
		width: 44px;
		height: 44px;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		color: #333;
	}

	.close-btn:hover { background: rgba(255,255,255,1); }

	.annotation-toolbar {
		position: absolute;
		top: calc(12px + var(--safe-area-inset-top, 0px));
		left: calc(12px + var(--safe-area-inset-left, 0px));
		z-index: 10;
		display: flex;
		gap: 8px;
	}

	.toolbar-btn {
		background: rgba(255,255,255,0.85);
		border: 2px solid transparent;
		border-radius: 8px;
		padding: 8px 12px;
		cursor: pointer;
		font-size: 14px;
		font-weight: 500;
	}

	.toolbar-btn.active {
		border-color: #4a90e2;
		background: rgba(74,144,226,0.15);
	}

	.toolbar-btn:hover { background: rgba(255,255,255,1); }

	.loading-overlay {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(0,0,0,0.6);
		z-index: 5;
	}

	.spinner {
		width: 48px;
		height: 48px;
		border: 4px solid rgba(255,255,255,0.3);
		border-top-color: #fff;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin { to { transform: rotate(360deg); } }

	.error-banner {
		position: absolute;
		bottom: 60px;
		left: 50%;
		transform: translateX(-50%);
		background: rgba(220,53,69,0.9);
		color: #fff;
		padding: 8px 16px;
		border-radius: 8px;
		font-size: 14px;
		z-index: 10;
	}

	.filename-bar {
		position: absolute;
		bottom: 20px;
		left: 50%;
		transform: translateX(-50%);
		background: rgba(0,0,0,0.7);
		color: #fff;
		padding: 6px 16px;
		border-radius: 20px;
		font-size: 13px;
		max-width: 80vw;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		z-index: 10;
		pointer-events: none;
	}
</style>
