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
	import { openExternalUrl } from '$lib/urlUtils';
	import { sharePhoto as sharePhotoUtil } from '$lib/shareUtils';
	import { photoInFront } from '$lib/mapState';
	import { onMount, onDestroy } from 'svelte';
	import OpenSeadragon from 'openseadragon';
	import { createOSDAnnotator } from '@annotorious/openseadragon';
	import { auth } from '$lib/auth.svelte.js';
	import {
		fetchAnnotations,
		createAnnotation,
		updateAnnotation,
		deleteAnnotation,
		targetToPixels,
		targetToNormalized,
		type AnnotationData,
	} from '$lib/annotationApi';
	import { Origin, UserSelectAction } from '@annotorious/core';
	import type { ZoomViewData } from '$lib/zoomView.svelte';
	import { zoomViewportBounds, type ZoomViewInitialBounds } from '$lib/zoomView.svelte';
	import { parseAnnotationBody, type BodyItem } from '$lib/utils/annotationBody';
	import {
		showDropdownMenu,
		closeDropdownMenu,
		type DropdownMenuItem,
	} from '$lib/components/dropdown-menu/dropdownMenu.svelte';
	import { constructUserProfileUrl } from '$lib/urlUtilsServer';
	import { myGoto } from '$lib/navigation.svelte';

	export let data: ZoomViewData;
	export let onClose: () => void;
	export let initialBounds: ZoomViewInitialBounds | null = null;

	let container: HTMLDivElement;
	let viewer: any = null;
	let annotator: any = null;
	let annotations: AnnotationData[] = [];
	type AnnotationMode = 'view' | 'draw' | 'edit';
	let annotationMode: AnnotationMode = 'view';
	let selectedAnnotation: AnnotationData | null = null;
	let editingAnnotation: AnnotationData | null = null;
	let editBody = '';
	let errorMessage = '';
	let errorTimeout: ReturnType<typeof setTimeout> | null = null;

	// Share state
	let shareMessage = '';
	let shareMessageError = false;
	let shareMessageTimeout: ReturnType<typeof setTimeout> | null = null;

	async function handleShare() {
		const photo = $photoInFront;
		if (!photo) return;
		const bounds = viewer?.viewport?.getBounds();
		const zoomViewBounds = bounds ? { x1: bounds.x, y1: bounds.y, x2: bounds.x + bounds.width, y2: bounds.y + bounds.height } : undefined;
		const result = await sharePhotoUtil(photo, zoomViewBounds);
		if (result.message) {
			shareMessage = result.message;
			shareMessageError = result.error;
			if (shareMessageTimeout) clearTimeout(shareMessageTimeout);
			shareMessageTimeout = setTimeout(() => {
				shareMessage = '';
				shareMessageError = false;
			}, result.error ? 3000 : 4000);
		}
	}

	// Track the mobile keyboard height via the Visual Viewport API so the
	// edit panel stays visible above it.
	let keyboardOffset = 0;

	// Edit session state — captured when edit panel opens, used for revert on Cancel
	let originalW3cSnapshot: any = null;
	let originalDbId: string | null = null;

	// When a new shape is drawn, we hold the Annotorious annotation here until
	// the user confirms via the edit panel (Save) or discards (Cancel/Escape).
	let pendingNewAnnotation: any = null;

	// View-mode annotation context menu state
	let viewSelectedAnnotation: AnnotationData | null = null;
	let viewSelectedGeometry: { x: number; y: number; w: number; h: number } | null = null;
	let menuBtnX = 0;
	let menuBtnY = 0;
	let menuBtnEl: HTMLButtonElement | null = null;
	let textModalContent: string | null = null;

	/** Deep clone that preserves Date objects (structuredClone works here). */
	function deepClone<T>(obj: T): T {
		return structuredClone(obj);
	}

	// UI IDs whose next updateAnnotation event should be swallowed.
	// Populated by save/cancel before calling setSelected(), consumed
	// (one-shot) by the updateAnnotation handler.  Deterministic — no
	// timing assumptions about when Annotorious flushes the editor commit.
	const suppressedUiIds = new Set<string>();

	// Bidirectional mapping: Annotorious UI IDs ↔ server DB IDs
	const uiToDb = new Map<string, string>();
	const dbToUi = new Map<string, string>();

	/** Get the authoritative image dimensions for annotation coordinate conversion. */
	function getImageDims(): { w: number; h: number } {
		const p = data.pyramid;
		if (p?.width && p?.height) return { w: p.width, h: p.height };
		if (data.width && data.height) return { w: data.width, h: data.height };
		return { w: 1, h: 1 }; // fallback — annotations will pass through unchanged
	}
	function showError(msg: string) {
		errorMessage = msg;
		if (errorTimeout) clearTimeout(errorTimeout);
		errorTimeout = setTimeout(() => { errorMessage = ''; }, 5000);
	}
	/** Get the main (topmost) TiledImage — avoids multi-image viewport warnings. */
	function getMainTiledImage(): any | null {
		if (!viewer?.world) return null;
		const count = viewer.world.getItemCount();
		return count > 0 ? viewer.world.getItemAt(count - 1) : null;
	}

	/** Recompute the "..." button position from the annotation's image-space geometry. */
	function updateMenuBtnPosition() {
		if (!viewSelectedGeometry || !viewer?.viewport) return;
		const item = getMainTiledImage();
		if (!item) return;
		const g = viewSelectedGeometry;
		const imgX = g.x + g.w / 2;
		const imgY = g.y + g.h; // bottom edge
		const vpPt = item.imageToViewportCoordinates(imgX, imgY);
		const scPt = viewer.viewport.viewportToViewerElementCoordinates(vpPt);
		menuBtnX = scPt.x;
		menuBtnY = scPt.y + 4; // slight offset below shape
	}

	/** Clear view-mode selection state and close any open menu. */
	function clearViewSelection() {
		viewSelectedAnnotation = null;
		viewSelectedGeometry = null;
		textModalContent = null;
		closeDropdownMenu();
	}

	/** Build dropdown menu items for the selected annotation. */
	function buildAnnotationMenuItems(ann: AnnotationData): DropdownMenuItem[] {
		const items: DropdownMenuItem[] = [];

		// @username link
		if (ann.owner_username) {
			items.push({
				id: 'annotation-menu-user',
				label: `@${ann.owner_username}`,
				onclick: () => {
					closeDropdownMenu();
					myGoto(constructUserProfileUrl(ann.user_id));
				},
				testId: 'annotation-menu-user',
			});
		}

		// Parse body into structured items
		const bodyItems = ann.body ? parseAnnotationBody(ann.body) : [];
		if (bodyItems.length > 0 && ann.owner_username) {
			items.push({ type: 'divider' });
		}

		for (let i = 0; i < bodyItems.length; i++) {
			const item = bodyItems[i];
			if (item.type === 'url') {
				items.push({
					id: `annotation-menu-body-${i}`,
					label: item.display,
					onclick: () => {
						closeDropdownMenu();
						openExternalUrl(item.value);
					},
					testId: `annotation-menu-body-${i}`,
				});
			} else {
				const text = item.value;
				items.push({
					id: `annotation-menu-body-${i}`,
					label: text.length > 30 ? text.slice(0, 30) + '\u2026' : text,
					onclick: () => {
						closeDropdownMenu();
						textModalContent = text;
					},
					testId: `annotation-menu-body-${i}`,
				});
			}
		}

		return items;
	}

	/** Toggle the annotation context menu from the "..." button. */
	function toggleAnnotationMenu() {
		if (!viewSelectedAnnotation || !menuBtnEl) return;
		const items = buildAnnotationMenuItems(viewSelectedAnnotation);
		showDropdownMenu(items, menuBtnEl, {
			placement: 'below-left',
			testId: 'annotation-context-menu',
		});
	}

	let isLoading = true;
	let labelCanvas: HTMLCanvasElement | null = null;
	let resizeObserver: ResizeObserver | null = null;

	$: isAuthenticated = $auth.is_authenticated;

	async function loadAnnotations() {
		if (!data.photo_id) return;
		//console.log('[OSD] Loading annotations for photo:', data.photo_id);
		try {
			annotations = await fetchAnnotations(data.photo_id);
			//console.log('[OSD] Fetched annotations:', annotations.length, annotations);
			syncAnnotationsToViewer();
		} catch (e) {
			console.error('[OSD] Failed to load annotations:', e);
			showError('Failed to load annotations');
		}
	}

	function syncAnnotationsToViewer() {
		if (!annotator) {
			console.warn('[OSD] syncAnnotationsToViewer: annotator not ready');
			return;
		}
		const dims = getImageDims();
		const w3cAnnotations = annotations
			.filter((a) => a.target)
			.map((a) => ({
				'@context': 'http://www.w3.org/ns/anno.jsonld',
				id: a.id,
				type: 'Annotation',
				body: a.body
					? [{ type: 'TextualBody', value: a.body, purpose: 'commenting' }]
					: [],
				target: targetToPixels(a.target, dims.w, dims.h),
			}));
		//console.log('[OSD] Syncing annotations to viewer:', w3cAnnotations.length, w3cAnnotations);
		try {
			annotator.setAnnotations(w3cAnnotations);
		} catch (e) {
			console.warn('[OSD] Could not sync annotations to viewer:', e);
		}
		// On initial load, UI IDs = DB IDs (1:1)
		uiToDb.clear();
		dbToUi.clear();
		for (const a of annotations) {
			if (!a.target) continue;
			uiToDb.set(a.id, a.id);
			dbToUi.set(a.id, a.id);
		}
		rebuildParsedAnnotations();
		scheduleDrawLabels();
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
				// crossOriginPolicy: 'Anonymous', // only needed for WebGL; causes CORS cache poisoning with fallback images
			};
		}
		// Fallback: single full-size image
		console.warn('[OSD] No DZI pyramid available, falling back to single-image source: ', JSON.stringify(p));
		return {
			type: 'image',
			url: data.url,
		};
	}

	// Pre-parsed annotation data for drawLabels — rebuilt only when annotations change
	interface ParsedAnnotation {
		dbId: string;
		label: string;
		// Image-space centroid
		imgCx: number;
		imgCy: number;
	}
	let parsedAnnotations: ParsedAnnotation[] = [];

	function rebuildParsedAnnotations() {
		const dims = getImageDims();
		parsedAnnotations = [];
		for (const ann of annotations) {
			if (!ann.body) continue;
			const firstItem = parseAnnotationBody(ann.body)[0];
			const label = firstItem ? firstItem.value : ann.body;
			if (!label) continue;

			const raw = ann.target as any;
			const selector = Array.isArray(raw?.selector) ? raw.selector[0] : raw?.selector;

			// Coords are [0,1] normalized — multiply by image dims for OSD pixel space
			let sx: number, sy: number, sw: number, sh: number;
			if (selector?.type === 'RECTANGLE' && selector.geometry) {
				const g = selector.geometry;
				sx = g.x * dims.w; sy = g.y * dims.h; sw = g.w * dims.w; sh = g.h * dims.h;
			} else if (typeof selector?.value === 'string') {
				const match = selector.value.match(/xywh=pixel:([\d.e+-]+),([\d.e+-]+),([\d.e+-]+),([\d.e+-]+)/);
				if (!match) continue;
				[, sx, sy, sw, sh] = match.map((v: string) => Number(v));
				sx *= dims.w; sy *= dims.h; sw *= dims.w; sh *= dims.h;
			} else {
				continue;
			}
			parsedAnnotations.push({ dbId: ann.id, label, imgCx: sx + sw / 2, imgCy: sy + sh / 2 });
		}
		lastDrawFingerprint = '';
		console.log('[OSD] rebuildParsedAnnotations:', parsedAnnotations.length, 'labels');
	}

	let drawLabelsRaf = 0;

	function scheduleDrawLabels() {
		if (!drawLabelsRaf) {
			drawLabelsRaf = requestAnimationFrame(() => {
				drawLabelsRaf = 0;
				drawLabelsNow();
				if (viewSelectedAnnotation) updateMenuBtnPosition();
			});
		}
	}

	// Debounced viewport bounds emission for URL sync
	let viewportBoundsTimeout: ReturnType<typeof setTimeout> | null = null;
	let initialBoundsApplied = false;

	function emitViewportBounds() {
		if (viewportBoundsTimeout) clearTimeout(viewportBoundsTimeout);
		viewportBoundsTimeout = setTimeout(() => {
			viewportBoundsTimeout = null;
			if (!viewer?.viewport) return;
			const bounds = viewer.viewport.getBounds();
			zoomViewportBounds.set({
				x1: bounds.x,
				y1: bounds.y,
				x2: bounds.x + bounds.width,
				y2: bounds.y + bounds.height
			});
		}, 500);
	}

	function applyInitialBounds() {
		if (initialBoundsApplied || !initialBounds || !viewer?.viewport) return;
		initialBoundsApplied = true;
		const rect = new OpenSeadragon.Rect(
			initialBounds.x1,
			initialBounds.y1,
			initialBounds.x2 - initialBounds.x1,
			initialBounds.y2 - initialBounds.y1
		);
		viewer.viewport.fitBounds(rect, true);
		console.log('[OSD] Applied initial viewport bounds from URL:', initialBounds);
	}

	// Whether the initial tileSources used the fallback thumbnail
	let usingFallback = false;

	/**
	 * Animate a TiledImage's opacity from 0 → 1 over `duration` ms.
	 * Resolves when the animation completes.
	 */
	function fadeInItem(item: any, duration = 300): Promise<void> {
		return new Promise((resolve) => {
			const start = performance.now();
			item.setOpacity(0);
			function step(now: number) {
				const t = Math.min((now - start) / duration, 1);
				item.setOpacity(t);
				if (t < 1) {
					requestAnimationFrame(step);
				} else {
					resolve();
				}
			}
			requestAnimationFrame(step);
		});
	}

	// Fingerprint of last drawn state — skip redraw if nothing changed
	let lastDrawFingerprint = '';

	import { buildLabelCommands, resolveOverlaps, LABEL_PAD, type LabelInput } from '$lib/utils/labelLayout';

	const LABEL_FONT = 'bold 12px system-ui,sans-serif';

	function drawLabelsNow() {
		if (!labelCanvas || !viewer?.viewport) return;
		const W = labelCanvas.width;
		const H = labelCanvas.height;

		const ctx = labelCanvas.getContext('2d');
		if (!ctx) return;
		ctx.font = LABEL_FONT;

		// Convert image-space annotations to screen-space inputs
		const item = getMainTiledImage();
		if (!item) return;
		const inputs: LabelInput[] = [];
		for (const { label, imgCx, imgCy } of parsedAnnotations) {
			const vpPt = item.imageToViewportCoordinates(imgCx, imgCy);
			const scPt = viewer.viewport.viewportToViewerElementCoordinates(vpPt);
			const cx = Math.round(scPt.x);
			const cy = Math.round(scPt.y);
			const tw = ctx.measureText(label).width;
			const pillW = tw + LABEL_PAD * 2;
			inputs.push({ label, cx, cy, pillW });
		}

		const { cmds, fingerprint: fp } = buildLabelCommands(inputs, W, H, 14);
		if (fp === lastDrawFingerprint) return;
		lastDrawFingerprint = fp;

		resolveOverlaps(cmds, W, H);

		// Expose resolved label state for Playwright tests
		if (typeof window !== 'undefined') {
			(window as any).__labelDebugCmds = cmds;
		}

		ctx.clearRect(0, 0, W, H);

		for (const { label, cx, cy, edge, tx, ty, pillW, pillH } of cmds) {
			// Leader line from centroid to pill center (after overlap resolution)
			const pillCx = tx + pillW / 2;
			const pillCy = ty + pillH / 2;
			ctx.beginPath();
			ctx.moveTo(cx, cy);
			ctx.lineTo(edge === 'left' || edge === 'right' ? tx + (edge === 'left' ? 0 : pillW) : pillCx,
			           edge === 'top' || edge === 'bottom' ? ty + (edge === 'top' ? 0 : pillH) : pillCy);
			ctx.strokeStyle = 'rgba(255,230,50,0.9)';
			ctx.lineWidth = 1.5;
			ctx.stroke();

			// Label pill
			ctx.font = LABEL_FONT;
			ctx.fillStyle = 'rgba(0,0,0,0.75)';
			ctx.beginPath();
			if (typeof (ctx as any).roundRect === 'function') {
				(ctx as any).roundRect(tx, ty, pillW, pillH, 4);
			} else {
				ctx.rect(tx, ty, pillW, pillH);
			}
			ctx.fill();
			ctx.fillStyle = '#fff';
			ctx.fillText(label, tx + LABEL_PAD, ty + pillH - 5);
		}
	}

	onMount(async () => {
		/*const [OSD, { createOSDAnnotator }] = await Promise.all([
			import('openseadragon'),
			import('@annotorious/openseadragon'),
		]);
		const OpenSeadragon = OSD.default ?? OSD;*/


		// If we have a fallback thumbnail (likely browser-cached), show it
		// immediately while the main source (DZI or full-size) loads.
		console.log('[OSD] fallback_url:', JSON.stringify(data.fallback_url), 'main url:', JSON.stringify(data.url));
		usingFallback = !!data.fallback_url;
		const initialSource = usingFallback
			? { type: 'image', url: data.fallback_url }
			: buildTileSource();

		const options = {
			element: container,
			drawer: 'canvas' as const,
			tileSources: initialSource,
			// Disable default controls – we supply our own close button
			showNavigationControl: false,
			showNavigator: false,
			animationTime: 0.3,
			// Allow dragging even without a button press (touch-friendly)
			gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true },
			gestureSettingsTouch: { clickToZoom: false, dblClickToZoom: true },
			immediateRender: false,
			imageLoaderLimit: 1,
			// Allow zooming well beyond native resolution (default is 1.1)
			maxZoomPixelRatio: 4,
			// Note: crossOriginPolicy is set per-source (on DZI tile sources), NOT here.
			// Setting it on the viewer would apply to fallback images too, which share
			// URLs with regular <img> tags. If the browser cached a non-CORS response,
			// loading with crossOrigin='anonymous' would fail (CORS cache poisoning).
			//debugMode: true
		}

		viewer = new OpenSeadragon.Viewer(options);

		viewer.addHandler('open', () => {
			console.log('[OSD] open event fired, usingFallback:', usingFallback, 'itemCount:', viewer.world.getItemCount());
			if (!usingFallback) {
				// No fallback path — the real source loaded directly
				isLoading = false;
				applyInitialBounds();
				return;
			}
			// Fallback thumbnail loaded (from browser cache) — dismiss spinner
			isLoading = false;
			applyInitialBounds();
			console.log('[OSD] Fallback loaded, spinner dismissed. Adding main source...');

			// Now add the real source on top — it renders over the fallback
			// as tiles arrive, then we remove the fallback once fully loaded.
			const mainSource = buildTileSource();
			viewer.addTiledImage({
				tileSource: mainSource,
				success: (event: any) => {
					const mainItem = event.item;
					const removeFallback = () => {
						const fallbackItem = viewer.world.getItemAt(0);
						if (fallbackItem && fallbackItem !== mainItem && viewer.world.getItemCount() > 1) {
							viewer.world.removeItem(fallbackItem);
							console.log('[OSD] Fallback image removed');
						}
					};
					// Listen on the TiledImage itself for fully-loaded-change,
					// which fires reliably for DZI sources (unlike world metrics-change).
					if (mainItem.getFullyLoaded()) {
						removeFallback();
					} else {
						const onLoaded = (e: any) => {
							if (!e.fullyLoaded) return;
							mainItem.removeHandler('fully-loaded-change', onLoaded);
							removeFallback();
						};
						mainItem.addHandler('fully-loaded-change', onLoaded);
					}
				},
				error: (event: any) => {
					// Main source failed — keep the fallback visible
					console.warn('[OSD] Main tile source failed to load, keeping fallback');
					throw new Error(`[OSD] addTiledImage error: ${event?.message || event?.source || JSON.stringify(event)}`);
				},
			});
		});

		viewer.addHandler('open-failed', (event: any) => {
			console.error('[OSD] open-failed event:', event);
			isLoading = false;
			errorMessage = 'Failed to load image';
			throw new Error(`[OSD] open-failed: ${event?.message || event?.source || JSON.stringify(event)}`);
		});

		// Mount Annotorious on the OSD viewer
		// Drawing starts disabled; the toolbar toggle enables it for authenticated users.
		annotator = createOSDAnnotator(viewer, {
			drawingEnabled: false,
			userSelectAction: UserSelectAction.SELECT,
			style: {
				fill: '#00ff00',
				fillOpacity: 0.06,
				stroke: '#00ff00',
				strokeWidth: 1.5,
				strokeOpacity: 0.6,
			},drawingMode: 'drag'
		});

		// Direct store observer: catches geometry changes during drag (the
		// updateAnnotation event only fires for body changes or on deselect).
		// This keeps edge labels tracking the shape in real time.
		annotator.state.store.observe(({ changes }: any) => {
			const updated = changes.updated;
			if (!updated?.length) return;
			let changed = false;
			for (const { newValue } of updated) {
				const sel = newValue.target?.selector;
				if (sel?.type !== 'RECTANGLE' || !sel.geometry) continue;
				const dbId = uiToDb.get(newValue.id);
				if (!dbId) continue;
				const idx = parsedAnnotations.findIndex((p) => p.dbId === dbId);
				if (idx < 0) continue;
				const g = sel.geometry;
				parsedAnnotations[idx] = {
					...parsedAnnotations[idx],
					imgCx: g.x + g.w / 2,
					imgCy: g.y + g.h / 2,
				};
				changed = true;
			}
			if (changed) {
				lastDrawFingerprint = '';
				scheduleDrawLabels();
			}
		});

		// When the user finishes drawing a shape, open the edit panel for labelling.
		annotator.on('createAnnotation', (annotation: any) => {
			console.log('[OSD] createAnnotation event — uiId:', annotation.id, 'target:', annotation.target);
			const textBody =
				(annotation.body?.find((b: any) => b.purpose === 'commenting')?.value) ?? '';
			// Park the annotation and open the edit panel so the user can type a label.
			pendingNewAnnotation = annotation;
			editBody = textBody || '?';
			// Synthesize an editingAnnotation so the panel renders.  It has no real
			// DB id yet — saveEditBody checks pendingNewAnnotation to decide the path.
			editingAnnotation = {
				id: '__pending__',
				photo_id: data.photo_id!,
				user_id: '',
				body: textBody,
				target: annotation.target,
				is_current: true,
				superseded_by: null,
				created_at: null,
				event_type: 'created',
				owner_username: null,
			};
			originalW3cSnapshot = deepClone(annotation);
			originalDbId = null;
			// Pause drawing while the panel is open so accidental drags
			// don't create more shapes.  Mode stays as 'draw'.
			annotator.setDrawingEnabled(false);
		});

		annotator.on('updateAnnotation', async (annotation: any, previous: any) => {
			console.log('[OSD] updateAnnotation event — uiId:', previous.id, '→ annotation:', annotation.id);
			// After our own save/cancel, setSelected() may trigger a shape commit — ignore it.
			if (suppressedUiIds.delete(previous.id)) {
				console.log('[OSD] updateAnnotation — suppressed (post-save/cancel) for', previous.id);
				return;
			}
			// When the edit panel is open, defer persistence — the Save button commits everything.
			// This avoids saving intermediate shape drags to the server.
			if (editingAnnotation) {
				console.log('[OSD] updateAnnotation — edit panel open, deferring persistence');
				return;
			}
			const body =
				annotation.body?.find((b: any) => b.purpose === 'commenting')?.value ?? '';
			const dbId = uiToDb.get(previous.id);
			if (!dbId) {
				console.warn('[OSD] updateAnnotation: no DB ID for UI ID', previous.id, '— map contents:', [...uiToDb.entries()]);
				showError('Failed to update — annotation mapping lost');
				return;
			}
			console.log('[OSD] updateAnnotation — uiId:', previous.id, '→ dbId:', dbId, ', body:', body);
			try {
				const dims = getImageDims();
				const saved = await updateAnnotation(dbId, {
					body,
					target: targetToNormalized(annotation.target, dims.w, dims.h),
				});
				console.log('[OSD] updateAnnotation — saved, old dbId:', dbId, '→ new dbId:', saved.id);
				// Update maps: UI ID now points to new DB row
				uiToDb.set(previous.id, saved.id);
				dbToUi.delete(dbId);           // old DB ID no longer valid
				dbToUi.set(saved.id, previous.id);
				// Update local annotations array
				annotations = annotations.filter((a) => a.id !== dbId).concat(saved);
				rebuildParsedAnnotations();
				scheduleDrawLabels();
			} catch (e) {
				console.error('[OSD] Failed to update annotation:', e);
				showError('Failed to update annotation');
			}
		});

		annotator.on('deleteAnnotation', async (annotation: any) => {
			console.log('[OSD] deleteAnnotation event — uiId:', annotation.id);
			const dbId = uiToDb.get(annotation.id);
			if (!dbId) {
				console.warn('[OSD] deleteAnnotation: no DB ID for UI ID', annotation.id, '— ignoring (map contents:', [...uiToDb.entries()], ')');
				return;  // programmatic remove or unknown — ignore
			}
			console.log('[OSD] deleteAnnotation — uiId:', annotation.id, '→ dbId:', dbId, ', deleting on server');
			try {
				await deleteAnnotation(dbId);
				console.log('[OSD] deleteAnnotation — deleted dbId:', dbId, ', cleaning up maps');
				uiToDb.delete(annotation.id);
				dbToUi.delete(dbId);
				annotations = annotations.filter((a) => a.id !== dbId);
				rebuildParsedAnnotations();
				scheduleDrawLabels();
			} catch (e) {
				console.error('[OSD] Failed to delete annotation:', e);
				showError('Failed to delete annotation');
			}
		});

		annotator.on('clickAnnotation', (annotation: any, originalEvent: PointerEvent) => {
			console.log('[OSD] clickAnnotation event — uiId:', annotation.id, 'mode:', annotationMode);
		});

		// Open the edit panel when Annotorious actually selects an annotation,
		// not on click (which can fire without selection happening).
		// Also auto-save on deselect so there's no silent data loss.
		annotator.on('selectionChanged', (selected: any[]) => {
			console.log('[OSD] selectionChanged — count:', selected.length, 'mode:', annotationMode,
				selected.length > 0 ? 'uiId:' + selected[0].id : '');
			if (selected.length > 0 && annotationMode === 'edit') {
				const annotation = selected[0];
				const uiId = annotation.id;
				const dbId = uiToDb.get(uiId);
				if (!dbId) {
					console.warn('[OSD] selectionChanged: no DB ID for UI ID', uiId);
					return;
				}
				// If we're already editing this annotation, don't reset the text input
				if (editingAnnotation && editingAnnotation.id === dbId) return;
				const match = annotations.find((a) => a.id === dbId);
				editingAnnotation = match ?? null;
				editBody = match?.body ?? '';
				// Capture snapshot for Cancel revert — must use store.getAnnotation
				// (internal format) not getAnnotationById (W3C-serialized), because
				// the deselect comparison uses internal format.
				originalDbId = dbId;
				const internal = annotator.state.store.getAnnotation(uiId);
				originalW3cSnapshot = internal ? deepClone(internal) : null;
				console.log('[OSD] selectionChanged — editing dbId:', dbId, 'body:', editBody);
			} else if (selected.length > 0 && annotationMode !== 'edit') {
				// View-mode selection: show the "..." context menu button
				const annotation = selected[0];
				const uiId = annotation.id;
				const dbId = uiToDb.get(uiId);
				if (!dbId) { clearViewSelection(); return; }
				const match = annotations.find((a) => a.id === dbId);
				if (!match) { clearViewSelection(); return; }

				// Extract geometry for positioning
				const sel = annotation.target?.selector;
				const rawSel = Array.isArray(sel) ? sel[0] : sel;
				const g = rawSel?.type === 'RECTANGLE' ? rawSel.geometry : null;
				if (!g) { clearViewSelection(); return; }

				viewSelectedAnnotation = match;
				viewSelectedGeometry = { x: g.x, y: g.y, w: g.w, h: g.h };
				updateMenuBtnPosition();
				console.log('[OSD] selectionChanged — view-selected dbId:', dbId);
			} else if (selected.length === 0 && editingAnnotation) {
				saveEditBody();
			} else if (selected.length === 0) {
				clearViewSelection();
			}
		});

		// The canvas is created imperatively so it can't use Svelte scoped styles;
		// inline style is intentional here.
		labelCanvas = document.createElement('canvas');
		labelCanvas.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:2';
		labelCanvas.dataset.testid = 'osd-label-canvas';
		container.appendChild(labelCanvas);

		resizeObserver = new ResizeObserver(() => {
			if (!labelCanvas) return;
			labelCanvas.width  = container.offsetWidth;
			labelCanvas.height = container.offsetHeight;
			scheduleDrawLabels();
		});
		resizeObserver.observe(container);

		viewer.addHandler('viewport-change', scheduleDrawLabels);
		viewer.addHandler('update-viewport',  scheduleDrawLabels);
		viewer.addHandler('viewport-change', emitViewportBounds);
		viewer.addHandler('update-viewport',  emitViewportBounds);

		// Close the viewer when the user clicks/taps the black background
		// outside the image bounds (mirrors original ZoomView behaviour).
		// event.quick distinguishes a tap/click from a pan/zoom drag — OSD sets
		// quick=false when the pointer moved significantly before release.
		viewer.addHandler('canvas-click', (event: any) => {
			if (!event.quick || annotationMode !== 'view') return;
			const itemCount = viewer.world.getItemCount();
			const item = itemCount > 0 ? viewer.world.getItemAt(itemCount - 1) : null;
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
				event.preventDefaultAction = true;
				event.originalEvent?.stopPropagation?.();
				event.originalEvent?.preventDefault?.();
				// Delay close so the overlay stays in the DOM long enough to
				// absorb the browser's touch→click synthesis (~300ms on mobile).
				// Without this, the overlay unmounts and the synthesized click
				// falls through to the map underneath.
				setTimeout(onClose, 50);
			}
		});

		// Load annotations after viewer is ready
		if (data.photo_id) {
			loadAnnotations();
		}
	});

	// Track mobile keyboard via Visual Viewport API
	function onViewportResize() {
		const vv = window.visualViewport;
		if (vv) {
			keyboardOffset = window.innerHeight - vv.height;
		}
	}
	if (typeof window !== 'undefined' && window.visualViewport) {
		window.visualViewport.addEventListener('resize', onViewportResize);
	}

	onDestroy(() => {
		clearViewSelection();
		window.visualViewport?.removeEventListener('resize', onViewportResize);
		resizeObserver?.disconnect();
		viewer?.removeHandler('viewport-change', scheduleDrawLabels);
		viewer?.removeHandler('update-viewport',  scheduleDrawLabels);
		viewer?.removeHandler('viewport-change', emitViewportBounds);
		viewer?.removeHandler('update-viewport',  emitViewportBounds);
		if (viewportBoundsTimeout) { clearTimeout(viewportBoundsTimeout); viewportBoundsTimeout = null; }
		zoomViewportBounds.set(null);
		if (drawLabelsRaf) { cancelAnimationFrame(drawLabelsRaf); drawLabelsRaf = 0; }
		annotator?.destroy?.();
		viewer?.destroy?.();
	});

	function setAnnotationMode(mode: AnnotationMode) {
		if (!annotator) return;
		annotationMode = mode;
		clearViewSelection();
		annotator.setDrawingEnabled(mode === 'draw');
		const selectAction = mode === 'edit' ? UserSelectAction.EDIT
			: mode === 'view' ? UserSelectAction.SELECT
			: UserSelectAction.NONE;
		annotator.setUserSelectAction(selectAction);
		if (mode !== 'edit') {
			annotator.setSelected();
			cancelEditBody();
		}
		if (mode === 'draw') {
			annotator.setDrawingTool('rectangle');
		}
	}

	function cancelEditBody() {
		const snapshot = originalW3cSnapshot;
		const wasCreate = !!pendingNewAnnotation;

		if (pendingNewAnnotation && annotator) {
			// Create path: discard the unpersisted shape entirely
			console.log('[OSD] cancelEditBody — removing unpersisted shape:', pendingNewAnnotation.id);
			try { annotator.removeAnnotation(pendingNewAnnotation); } catch (_) {}
			pendingNewAnnotation = null;
		}

		// Clear panel state before deselecting so the selectionChanged handler
		// doesn't re-enter via saveEditBody.
		editingAnnotation = null;
		editBody = '';
		originalW3cSnapshot = null;
		originalDbId = null;

		// Suppress the lifecycle event that the revert will trigger.
		// Must be set BEFORE the store update so the handler sees it.
		if (snapshot) suppressedUiIds.add(snapshot.id);

		// Revert the store to the internal-format snapshot captured at selection
		// time.  Do NOT use Origin.SILENT — that skips the rendering observer,
		// leaving the annotation visually in the moved position.  The default
		// origin (LOCAL) triggers both the rendering layer and the lifecycle
		// bridge; the latter is suppressed by suppressedUiIds above.
		if (snapshot && annotator && !wasCreate) {
			try {
				annotator.state.store.updateAnnotation(
					snapshot.id,
					snapshot
				);
				console.log('[OSD] cancelEditBody — reverted shape to original snapshot');
			} catch (e) {
				console.warn('[OSD] cancelEditBody — could not revert shape:', e);
			}
		}
		annotator?.setSelected?.();

		// After cancel on a new shape, return to view mode (one-shot draw).
		if (wasCreate && annotationMode === 'draw') {
			setAnnotationMode('view');
		}
	}

	async function saveEditBody() {
		if (!editingAnnotation || !annotator) return;

		// ── Create path: new shape not yet persisted ──
		if (pendingNewAnnotation) {
			const ann = pendingNewAnnotation;
			const body = editBody;
			console.log('[OSD] saveEditBody (create) — uiId:', ann.id, 'body:', body);
			try {
				const dims = getImageDims();
				const saved = await createAnnotation(data.photo_id!, {
					body,
					target: targetToNormalized(ann.target, dims.w, dims.h),
				});
				console.log('[OSD] saveEditBody (create) — saved, uiId:', ann.id, '→ dbId:', saved.id);
				annotations = [...annotations, saved];
				uiToDb.set(ann.id, saved.id);
				dbToUi.set(saved.id, ann.id);
				// Sync the body into Annotorious so subsequent edits carry it.
				annotator.state.store.updateAnnotation(ann.id, {
					...ann,
					body: [{ type: 'TextualBody', value: body, purpose: 'commenting' }],
				}, Origin.SILENT);
				rebuildParsedAnnotations();
				scheduleDrawLabels();
			} catch (e) {
				console.error('[OSD] saveEditBody (create) — failed:', e);
				annotator.removeAnnotation(ann);
				showError('Failed to save annotation');
			}
			// Clean up panel state
			suppressedUiIds.add(ann.id);
			annotator.setSelected();
			pendingNewAnnotation = null;
			editingAnnotation = null;
			editBody = '';
			originalW3cSnapshot = null;
			originalDbId = null;
			// After saving a new shape, return to view mode (one-shot draw).
			if (annotationMode === 'draw') {
				setAnnotationMode('view');
			}
			return;
		}

		// ── Update path: existing annotation ──
		const dbId = editingAnnotation.id;
		const uiId = dbToUi.get(dbId);
		if (!uiId) {
			console.warn('[OSD] saveEditBody: no UI ID for DB ID', dbId);
			showError('Could not save — annotation mapping lost');
			cancelEditBody();
			return;
		}
		console.log('[OSD] saveEditBody — uiId:', uiId, 'dbId:', dbId, 'newBody:', editBody);
		// Get the current W3C annotation (with any shape changes the user made)
		const w3c = annotator.getAnnotationById(uiId);
		if (!w3c) {
			console.warn('[OSD] saveEditBody: annotation not found in Annotorious, uiId:', uiId);
			showError('Could not save — annotation not found in viewer');
			cancelEditBody();
			return;
		}
		try {
			// Persist body + target (possibly moved shape) to server
			const dims = getImageDims();
			const saved = await updateAnnotation(dbId, {
				body: editBody,
				target: targetToNormalized(w3c.target, dims.w, dims.h),
			});
			console.log('[OSD] saveEditBody — saved, old dbId:', dbId, '→ new dbId:', saved.id);
			// Update ID maps (supersede chain)
			uiToDb.set(uiId, saved.id);
			dbToUi.delete(dbId);
			dbToUi.set(saved.id, uiId);
			// Update local annotations array
			annotations = annotations.filter((a) => a.id !== dbId).concat(saved);
			// Sync the body into Annotorious silently (so it reflects the new label)
			annotator.state.store.updateAnnotation(uiId, {
				...w3c,
				body: [{ type: 'TextualBody', value: editBody, purpose: 'commenting' }],
			}, Origin.SILENT);
			rebuildParsedAnnotations();
			scheduleDrawLabels();
			// Deselect — mark this annotation so the editor's deselect-commit
			// doesn't trigger a redundant server persist.
			suppressedUiIds.add(uiId);
			annotator.setSelected();
			// Close panel state
			editingAnnotation = null;
			editBody = '';
			originalW3cSnapshot = null;
			originalDbId = null;
		} catch (e) {
			console.error('[OSD] saveEditBody — failed:', e);
			showError('Failed to update annotation');
			// Revert shape and close panel so the user isn't stuck
			cancelEditBody();
		}
	}

	async function deleteEditingAnnotation() {
		if (!editingAnnotation || !annotator) return;

		// Create path: shape isn't persisted yet — just discard it
		if (pendingNewAnnotation) {
			cancelEditBody();
			return;
		}

		const dbId = editingAnnotation.id;
		const uiId = dbToUi.get(dbId);
		console.log('[OSD] deleteEditingAnnotation — dbId:', dbId, 'uiId:', uiId);
		try {
			await deleteAnnotation(dbId);
			// Clean up maps
			if (uiId) {
				uiToDb.delete(uiId);
				// Remove from Annotorious silently (avoid triggering the deleteAnnotation handler again)
				try { annotator.removeAnnotation(uiId); } catch (_) {}
			}
			dbToUi.delete(dbId);
			annotations = annotations.filter((a) => a.id !== dbId);
			rebuildParsedAnnotations();
			scheduleDrawLabels();
			// Close panel
			editingAnnotation = null;
			editBody = '';
			originalW3cSnapshot = null;
			originalDbId = null;
		} catch (e) {
			console.error('[OSD] deleteEditingAnnotation — failed:', e);
			showError('Failed to delete annotation');
			// Close panel so the user isn't stuck — annotation remains on canvas
			editingAnnotation = null;
			editBody = '';
			originalW3cSnapshot = null;
			originalDbId = null;
		}
	}

	function autofocus(node: HTMLElement) { node.focus(); (node as HTMLInputElement).select?.(); }

	function handleKeydown(e: KeyboardEvent) {
		// Don't handle shortcuts while typing in the edit panel input
		const tag = (e.target as HTMLElement)?.tagName;
		if (tag === 'INPUT' || tag === 'TEXTAREA') {
			if (e.key === 'Escape') {
				cancelEditBody();
			}
			return;
		}
		if (e.key === 'Escape') {
			if (textModalContent) {
				textModalContent = null;
			} else if (editingAnnotation) {
				cancelEditBody();
			} else if (viewSelectedAnnotation) {
				clearViewSelection();
				annotator?.setSelected?.();
			} else {
				onClose();
			}
		} else if (e.key === 'd' && isAuthenticated) {
			setAnnotationMode(annotationMode === 'draw' ? 'view' : 'draw');
		} else if (e.key === 'e' && isAuthenticated) {
			setAnnotationMode(annotationMode === 'edit' ? 'view' : 'edit');
		}
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

	<!-- Toolbar -->
	<div class="annotation-toolbar">
		{#if isAuthenticated}
			<button
				class="toolbar-btn toolbar-btn-draw"
				class:active={annotationMode === 'draw'}
				onclick={() => setAnnotationMode(annotationMode === 'draw' ? 'view' : 'draw')}
				title={annotationMode === 'draw' ? 'Stop drawing' : 'Draw annotation'}
				data-testid="osd-annotate-draw"
			>
				✏️ Draw
			</button>
			<button
				class="toolbar-btn toolbar-btn-edit"
				class:active={annotationMode === 'edit'}
				onclick={() => setAnnotationMode(annotationMode === 'edit' ? 'view' : 'edit')}
				title={annotationMode === 'edit' ? 'Stop editing' : 'Edit annotations'}
				data-testid="osd-annotate-edit"
			>
				🔧 Edit
			</button>
		{/if}
		{#if $photoInFront}
			<button
				class="toolbar-btn toolbar-btn-share"
				onclick={handleShare}
				title="Share photo"
				data-testid="osd-share"
			>
				🔗 Share
			</button>
		{/if}
	</div>

	<!-- Share status message -->
	{#if shareMessage}
		<div class="share-message" class:error={shareMessageError}>{shareMessage}</div>
	{/if}

	<!-- Loading indicator -->
	{#if isLoading}
		<div class="loading-overlay">
			<div class="spinner"></div>
		</div>
	{/if}

	<!-- Annotation body edit panel -->
	{#if editingAnnotation}
		<div class="edit-body-panel" data-testid="osd-edit-body-panel"
			style:bottom="{Math.max(16, keyboardOffset + 16)}px">
			<label class="edit-body-label" for="edit-body-input">Label</label>
			<input
				id="edit-body-input"
				class="edit-body-input"
				type="text"
				bind:value={editBody}
				onkeydown={(e) => { if (e.key === 'Enter') saveEditBody(); }}
				use:autofocus
				data-testid="osd-edit-body-input"
			/>
			<div class="edit-body-actions">
				<button class="edit-body-btn delete" onclick={deleteEditingAnnotation} data-testid="osd-edit-body-delete">Delete</button>
				<div style="flex:1"></div>
				<button class="edit-body-btn cancel" onclick={cancelEditBody} data-testid="osd-edit-body-cancel">Cancel</button>
				<button class="edit-body-btn save" onclick={saveEditBody} data-testid="osd-edit-body-save">Save</button>
			</div>
		</div>
	{/if}

	<!-- View-mode annotation context menu button -->
	{#if viewSelectedAnnotation}
		<button
			class="annotation-menu-btn"
			style:left="{menuBtnX}px"
			style:top="{menuBtnY}px"
			bind:this={menuBtnEl}
			data-testid="annotation-menu-btn"
			onclick={toggleAnnotationMenu}
			aria-label="Annotation menu"
		>⋯</button>
	{/if}

	<!-- Annotation text detail modal -->
	{#if textModalContent}
		<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
		<div class="text-modal-overlay" data-testid="annotation-text-modal" onclick={() => textModalContent = null}>
			<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
			<div class="text-modal" onclick={(e) => e.stopPropagation()}>
				<p class="text-modal-body">{textModalContent}</p>
				<button class="text-modal-close" onclick={() => textModalContent = null} data-testid="annotation-text-modal-close">Close</button>
			</div>
		</div>
	{/if}

	<!-- Error message -->
	{#if errorMessage}
		<div class="error-banner">{errorMessage}</div>
	{/if}

	<!-- OpenSeadragon container -->
	<div bind:this={container} class="osd-container"></div>

	<!-- Filename bar -->
	{#if annotationMode === 'view'}
		<div class="filename-bar">{data.description || data.filename}</div>
	{/if}
</div>

<style>
	.osd-overlay {
		position: fixed;
		inset: 0;
		background: #000;
		z-index: 999999;
		display: flex;
		flex-direction: column;
		/* Use dynamic viewport height so the overlay shrinks when the
		   mobile keyboard is visible (supported in modern browsers). */
		height: 100dvh;
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
		color: #222;
	}

	.toolbar-btn:hover {
		background: rgba(255,255,255,1);
	}

	.toolbar-btn-draw.active {
		border-color: #e2904a;
		background: rgba(226,144,74,0.75);
		color: #fff;
	}

	.toolbar-btn-draw.active:hover {
		background: rgba(226,144,74,0.9);
	}

	.toolbar-btn-edit.active {
		border-color: #4a90e2;
		background: rgba(74,144,226,0.75);
		color: #fff;
	}

	.toolbar-btn-edit.active:hover {
		background: rgba(74,144,226,0.9);
	}

	.share-message {
		position: absolute;
		top: calc(56px + var(--safe-area-inset-top, 0px));
		left: calc(12px + var(--safe-area-inset-left, 0px));
		z-index: 10;
		background: rgba(40, 167, 69, 0.9);
		color: white;
		padding: 8px 12px;
		border-radius: 4px;
		font-size: 14px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
		animation: fadeIn 0.3s ease;
	}

	.share-message.error {
		background: rgba(220, 53, 69, 0.9);
	}

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
	@keyframes fadeIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }

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

	.edit-body-panel {
		position: absolute;
		/* bottom is set via inline style (keyboardOffset-aware) */
		left: 50%;
		transform: translateX(-50%);
		z-index: 10;
		background: rgba(30,30,30,0.95);
		border: 1px solid rgba(255,255,255,0.2);
		border-radius: 10px;
		padding: 12px 16px;
		display: flex;
		flex-direction: column;
		gap: 8px;
		min-width: 260px;
		max-width: 90vw;
	}

	.edit-body-label {
		color: rgba(255,255,255,0.7);
		font-size: 12px;
		font-weight: 500;
	}

	.edit-body-input {
		background: rgba(255,255,255,0.1);
		border: 1px solid rgba(255,255,255,0.3);
		border-radius: 6px;
		color: #fff;
		padding: 8px 10px;
		font-size: 14px;
		outline: none;
	}

	.edit-body-input:focus {
		border-color: #4a90e2;
	}

	.edit-body-actions {
		display: flex;
		gap: 8px;
		justify-content: flex-end;
	}

	.edit-body-btn {
		border: none;
		border-radius: 6px;
		padding: 6px 14px;
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
	}

	.edit-body-btn.save {
		background: #4a90e2;
		color: #fff;
	}

	.edit-body-btn.save:hover { background: #357abd; }

	.edit-body-btn.cancel {
		background: rgba(255,255,255,0.15);
		color: #fff;
	}

	.edit-body-btn.cancel:hover { background: rgba(255,255,255,0.25); }

	.edit-body-btn.delete {
		background: #dc3545;
		color: #fff;
	}

	.edit-body-btn.delete:hover { background: #c82333; }

	.annotation-menu-btn {
		position: absolute;
		z-index: 10;
		transform: translateX(-50%);
		background: rgba(255,255,255,0.9);
		border: none;
		border-radius: 50%;
		width: 32px;
		height: 32px;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		font-size: 18px;
		font-weight: bold;
		color: #333;
		box-shadow: 0 2px 6px rgba(0,0,0,0.3);
		line-height: 1;
		padding: 0;
	}

	.annotation-menu-btn:hover {
		background: rgba(255,255,255,1);
	}

	.text-modal-overlay {
		position: absolute;
		inset: 0;
		z-index: 20;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(0,0,0,0.5);
	}

	.text-modal {
		background: rgba(30,30,30,0.95);
		border: 1px solid rgba(255,255,255,0.2);
		border-radius: 10px;
		padding: 20px 24px;
		max-width: 80vw;
		max-height: 60vh;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.text-modal-body {
		color: #fff;
		font-size: 15px;
		line-height: 1.6;
		margin: 0;
		white-space: pre-wrap;
		word-break: break-word;
	}

	.text-modal-close {
		align-self: flex-end;
		background: rgba(255,255,255,0.15);
		border: none;
		border-radius: 6px;
		color: #fff;
		padding: 6px 16px;
		font-size: 13px;
		cursor: pointer;
	}

	.text-modal-close:hover {
		background: rgba(255,255,255,0.25);
	}

	.filename-bar {
		position: absolute;
		bottom: 20px;
		left: 50%;
		transform: translateX(-50%);
		background: rgba(0,0,0,0.2);
		color: #fff;
		padding: 6px 16px;
		border-radius: 20px;
		font-size: 13px;
		max-width: 80vw;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		z-index: 1;
		pointer-events: none;
	}


</style>
