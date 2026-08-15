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
	import { openExternalUrl, constructMapUrl, externalBaseUrl } from '$lib/urlUtils';
	import { sharePhoto as sharePhotoUtil } from '$lib/shareUtils';
	import { togglePhotoRating, fetchPhotoRating, ratingShortcutFor, type Rating } from '$lib/photoActions';
	import type { PhotoData } from '$lib/sources';
	import { photoInFront } from '$lib/mapState';
	import { track } from '$lib/analytics';
	import { onMount, onDestroy, type Snippet } from 'svelte';
	import OpenSeadragon from 'openseadragon';
	import { createOSDAnnotator } from '@annotorious/openseadragon';
	import {
		fetchAnnotations,
		createAnnotation,
		updateAnnotation,
		deleteAnnotation,
		targetToPixels,
		targetToNormalized,
		type AnnotationData,
	} from '$lib/annotationApi';
	import { Origin, UserSelectAction, type DrawingStyle } from '@annotorious/core';
	import { fetchDetections, type DetectedObject } from '$lib/detectionApi';
	import { showDetections, showPhotoInfoWindow, showTerrainOverlay } from '$lib/data.svelte.js';
	import {
		createOverlayProjector,
		effectiveFit,
		pickFromOverlay,
		skylinePolylines,
		type TerrainOverlay
	} from '$terrain/overlayFit';
	import { layoutSkyLabels, PLACE_KINDS } from '$terrain/peakLabels';
	import {
		fetchTerrainOverlay,
		loadOverlayDepth,
		overlayDepthReady,
		releaseOverlayDepth
	} from '$lib/terrainOverlayApi';
	import PhotoInfoWindow from './PhotoInfoWindow.svelte';
	import type { ZoomViewData } from '$lib/zoomView.svelte';
	import { zoomViewportBounds, type ZoomViewInitialBounds } from '$lib/zoomView.svelte';
	import { parseAnnotationBody, type BodyItem } from '$lib/utils/annotationBody';
	import { firstCoords, splitOnCoords } from '$lib/utils/coordParser';
	import { requireAuth } from './signInModal.svelte';
	import {
		showDropdownMenu,
		showDropdownMenuAt,
		closeDropdownMenu,
		toggleDropdownMenu,
		dropdownMenuState,
		type DropdownMenuItem,
	} from '$lib/components/dropdown-menu/dropdownMenu.svelte';
	import { MapPin, MoreVertical, Share } from 'lucide-svelte';
	import { constructUserProfileUrl } from '$lib/urlUtilsServer';
	import { myGoto } from '$lib/navigation.svelte';
	import { buildTileSource } from '$zoomview/tileSource';

	export let data: ZoomViewData;
	export let onClose: () => void;
	export let initialBounds: ZoomViewInitialBounds | null = null;

	let container: HTMLDivElement;
	let viewer: any = null;
	let annotator: any = null;
	let annotations: AnnotationData[] = [];

	// Anonymization detections (debug overlay toggle) — rendered as read-only
	// Annotorious annotations with ids prefixed so they never collide with
	// (or get persisted as) user annotations.
	const DETECTION_ID_PREFIX = 'hv-detection:';
	const isDetectionId = (id: unknown) => typeof id === 'string' && id.startsWith(DETECTION_ID_PREFIX);
	let detectionObjects: DetectedObject[] = [];
	let detectionsFetched = false;
	// Dimensions of the image the detector ran on (original full resolution).
	// The displayed image space (getImageDims) can be smaller — the 'full' web
	// variant is capped (8192px wide) — so detection coords must be rescaled.
	let detectionDims: { w: number; h: number } | null = null;
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

	// Rating state for the zoomed photo. There are no on-screen like/dislike
	// buttons here, so '*' (like) / '&' (dislike) are confirmed with a toast.
	let userRating: Rating | null = null;
	let ratingPhotoId: string | null = null;
	let isRating = false;
	let ratingMessage = '';
	let ratingMessageTimeout: ReturnType<typeof setTimeout> | null = null;
	// Bumped on every photo change and rating action so a slow rating fetch
	// knows it has been superseded and won't clobber a fresher value.
	let ratingGen = 0;

	async function handleShare() {
		track('share');
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

	function showRatingFeedback(message: string) {
		ratingMessage = message;
		if (ratingMessageTimeout) clearTimeout(ratingMessageTimeout);
		ratingMessageTimeout = setTimeout(() => { ratingMessage = ''; }, 2000);
	}

	// Keep the user's current rating in sync with the photo on display so the
	// first '*'/'&' toggles correctly instead of re-setting an existing rating.
	function syncRating(photo: PhotoData | null) {
		if (!photo) { userRating = null; ratingPhotoId = null; return; }
		if (photo.id === ratingPhotoId) return;
		ratingPhotoId = photo.id;
		userRating = null;
		const gen = ++ratingGen;
		fetchPhotoRating(photo).then((state) => {
			if (gen === ratingGen) userRating = state.userRating;
		});
	}
	$: syncRating($photoInFront);

	async function handleRatingKey(rating: Rating) {
		const photo = $photoInFront;
		if (!photo || isRating) return;
		if (!requireAuth()) return;
		isRating = true;
		const gen = ++ratingGen; // supersede any in-flight rating fetch
		try {
			const state = await togglePhotoRating(photo, rating, userRating);
			if (gen === ratingGen) userRating = state.userRating;
			showRatingFeedback(
				state.userRating === 'thumbs_up' ? 'Liked'
				: state.userRating === 'thumbs_down' ? 'Disliked'
				: rating === 'thumbs_up' ? 'Like removed'
				: 'Dislike removed'
			);
		} catch (err) {
			console.error('🢄 Error updating rating:', err);
			showRatingFeedback('Rating error');
		} finally {
			isRating = false;
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

	// View-mode annotation context menu state. The menu opens on the shape
	// itself; menuAnchor is where it hangs from (bottom-centre of the shape).
	let viewSelectedAnnotation: AnnotationData | null = null;
	let viewSelectedGeometry: { x: number; y: number; w: number; h: number } | null = null;
	let menuAnchorX = 0;
	let menuAnchorY = 0;
	let textModalContent: string | null = null;
	let textModalOpenedAt = 0;

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

	/** Recompute the menu anchor from the annotation's image-space geometry. */
	function updateMenuAnchor() {
		if (!viewSelectedGeometry || !viewer?.viewport) return;
		const item = getMainTiledImage();
		if (!item) return;
		const g = viewSelectedGeometry;
		const imgX = g.x + g.w / 2;
		const imgY = g.y + g.h; // bottom edge
		const vpPt = item.imageToViewportCoordinates(imgX, imgY);
		const scPt = viewer.viewport.viewportToViewerElementCoordinates(vpPt);
		menuAnchorX = scPt.x;
		menuAnchorY = scPt.y + 4; // slight offset below shape
	}

	/** Clear view-mode selection state and close any open menu. */
	function clearViewSelection() {
		viewSelectedAnnotation = null;
		viewSelectedGeometry = null;
		textModalContent = null;
		closeDropdownMenu();
	}

	/** Map URL for a coordinate pair from an annotation body (see
	 *  $lib/utils/coordParser for the accepted formats). Absolute, because it is
	 *  always opened outside this view. Fixed zoom rather than the current map
	 *  zoom — the target is a landmark somewhere off in the distance, so what
	 *  the user was looking at here says nothing about how close they want it. */
	const COORDS_MAP_ZOOM = 16;
	function coordsMapUrl(lat: number, lon: number): string {
		return constructMapUrl({ lat, lon, zoom: COORDS_MAP_ZOOM, baseUrl: externalBaseUrl() });
	}

	/** Open a body coordinate on the map in a new tab (web) or the system
	 *  browser (Tauri) — deliberately NOT an in-app route change: the zoomview
	 *  is a modal over whatever the user was doing, and navigating away from it
	 *  leaves them with no sane way back. */
	function goToCoords(label: string, lat: number, lon: number) {
		track('annotationCoords', {coords: label, photo: data.photo_id ?? ''});
		closeDropdownMenu();
		openExternalUrl(coordsMapUrl(lat, lon));
	}

	/** Coordinate link in the text modal. Modified clicks (ctrl/meta/shift,
	 *  middle) fall through to the anchor so the browser opens them its own way. */
	function handleCoordLinkClick(e: MouseEvent, label: string, lat: number, lon: number) {
		if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
		e.preventDefault();
		goToCoords(label, lat, lon);
	}

	/** Build dropdown menu items for the selected annotation. */
	function buildAnnotationMenuItems(ann: AnnotationData): DropdownMenuItem[] {
		const items: DropdownMenuItem[] = [];
		const annProps = {annotation: ann.id, photo: data.photo_id ?? ''};
		const trackItem = (label: string) => track('annotationMenuItem:' + label, annProps);

		// @username link
		if (ann.owner_username) {
			items.push({
				id: 'annotation-menu-user',
				label: `@${ann.owner_username}`,
				onclick: () => {
					trackItem('@' + ann.owner_username);
					closeDropdownMenu();
					onClose();
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

		// Go-to-map item for a coordinate pair found in the body
		const pushCoordsItem = (label: string, lat: number, lon: number, i: number) => {
			items.push({
				id: `annotation-menu-coords-${i}`,
				label,
				icon: MapPin,
				url: coordsMapUrl(lat, lon),   // renders as <a> so ctrl/middle-click work
				onclick: () => goToCoords(label, lat, lon),   // goToCoords tracks
				testId: `annotation-menu-coords-${i}`,
			});
		};

		for (let i = 0; i < bodyItems.length; i++) {
			const item = bodyItems[i];
			if (item.type === 'coords') {
				pushCoordsItem(item.value, item.lat, item.lon, i);
				continue;
			}
			if (item.type === 'url') {
				items.push({
					id: `annotation-menu-body-${i}`,
					label: item.display,
					onclick: () => {
						trackItem(item.display);
						closeDropdownMenu();
						openExternalUrl(item.value);
					},
					testId: `annotation-menu-body-${i}`,
				});
			} else {
				const text = item.value;
				const label = text.length > 30 ? text.slice(0, 30) + '\u2026' : text;
				items.push({
					id: `annotation-menu-body-${i}`,
					label,
					onclick: () => {
						trackItem(label);
						closeDropdownMenu();
						textModalContent = text;
						textModalOpenedAt = Date.now();
					},
					testId: `annotation-menu-body-${i}`,
				});
			}
			// Coords embedded in a text/URL segment ("Je\u0161t\u011bd 50.732N, 15.008E",
			// maps links) \u2014 parse_body extracts these from any segment, so give
			// them a go-to-map item too.
			const c = firstCoords(item.value);
			if (c) pushCoordsItem(c.text, c.lat, c.lon, i);
		}

		return items;
	}

	/** Show annotation context menu when a label pill is clicked. */
	function handleLabelClick(e: MouseEvent, cmd: LabelDrawCmd) {
		if (annotationMode !== 'view' || !cmd.id) return;
		const ann = annotations.find(a => a.id === cmd.id);
		if (!ann) return;
		const items = buildAnnotationMenuItems(ann);
		const target = e.currentTarget as HTMLElement;
		showDropdownMenu(items, target, {
			placement: 'below-left',
			testId: 'annotation-context-menu',
		});
	}

	/** Handle label click detected via OSD canvas-click hit-testing.
	 *  Used instead of button onclick since labels have pointer-events: none
	 *  to let touch events pass through to OSD for pinch-zoom. */
	function handleCanvasLabelClick(cmd: LabelDrawCmd) {
		if (!cmd.id) return;
		const ann = annotations.find(a => a.id === cmd.id);
		if (!ann) return;
		const items = buildAnnotationMenuItems(ann);
		const containerRect = container.getBoundingClientRect();
		showDropdownMenuAt(items, containerRect.left + cmd.tx, containerRect.top + cmd.ty + cmd.pillH, {
			anchor: 'top-left',
			testId: 'annotation-context-menu',
		});
	}

	/** Open the context menu for the view-selected annotation, hanging from the
	 *  bottom of its shape. Called straight from selection — clicking a shape
	 *  shows the menu, there is no intermediate "..." button to hunt for. */
	function openViewAnnotationMenu() {
		track('annotationMenu');
		if (!viewSelectedAnnotation || !container) return;
		const items = buildAnnotationMenuItems(viewSelectedAnnotation);
		const containerRect = container.getBoundingClientRect();
		showDropdownMenuAt(items, containerRect.left + menuAnchorX, containerRect.top + menuAnchorY, {
			anchor: 'top-left',
			testId: 'annotation-context-menu',
		});
	}

	let isLoading = true;
	let labelCanvas: HTMLCanvasElement | null = null;
	let resizeObserver: ResizeObserver | null = null;

	// ---- graduated terrain overlay (horizon line + peak labels) ----
	// The document is a few KB and draws everything. Its depth buffer is a few
	// hundred KB and is ONLY needed to answer "what is that?" for an arbitrary
	// pixel, so it loads on the first click, not with the overlay.
	let terrainOverlay: TerrainOverlay | null = null;
	let terrainCanvas: HTMLCanvasElement | null = null;
	let terrainFetchedFor: string | null = null;
	let terrainPick: {
		lat: number;
		lon: number;
		distance_m: number;
		imgX: number;
		imgY: number;
	} | null = null;
	let terrainPickBusy = false;

	/**
	 * Load the overlay for the current photo, clearing the previous photo's
	 * first. Both halves live here rather than in separate reactive blocks:
	 * split across two, whichever Svelte happened to run first would decide
	 * whether the old horizon got cleared at all.
	 */
	async function loadTerrainOverlay() {
		const photoId = data.photo_id;
		if (!photoId || terrainFetchedFor === photoId) return;
		terrainFetchedFor = photoId;
		terrainOverlay = null;
		terrainPick = null;
		releaseOverlayDepth();
		scheduleDrawTerrain();
		try {
			const res = await fetchTerrainOverlay(photoId);
			// a slow response for a photo the user already left must not paint
			// its horizon over the next one
			if (terrainFetchedFor !== photoId) return;
			terrainOverlay = res.terrain_overlay;
			scheduleDrawTerrain();
		} catch (e) {
			console.warn('[OSD] Could not load terrain overlay:', e);
			if (terrainFetchedFor === photoId) terrainOverlay = null;
		}
	}

	// Probed for every photo, not gated on the toggle: the response is a few
	// KB (and `null` for the majority of photos), and it is what decides
	// whether the display menu offers the overlay at all — gating the fetch on
	// the toggle would make the toggle undiscoverable.
	$: if (data.photo_id) {
		loadTerrainOverlay();
	}
	$: {
		void $showTerrainOverlay;
		scheduleDrawTerrain();
	}

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

	/** Human-readable label for a detection, e.g. "person 83% s1" or "manual". */
	function detectionLabel(obj: DetectedObject): string {
		const name = obj.class_name ?? 'manual';
		const conf = typeof obj.confidence === 'number' ? ` ${(obj.confidence * 100).toFixed(0)}%` : '';
		const scale = typeof obj.scale === 'number' ? ` s${obj.scale}` : '';
		return `${name}${conf}${scale}`;
	}

	/** Scale factors from detection space (original full-res pixels) into the
	 *  annotator's working space (the displayed image, via getImageDims).
	 *  These differ when the photo is shown without a DZI pyramid: the 'full'
	 *  web variant is width-capped, while detections are at original res. */
	function detectionScaleFactors(): { fx: number; fy: number } {
		const dims = getImageDims();
		if (!detectionDims?.w || !detectionDims?.h || dims.w <= 1) return { fx: 1, fy: 1 };
		return { fx: dims.w / detectionDims.w, fy: dims.h / detectionDims.h };
	}

	function detectionToW3c(obj: DetectedObject, i: number, fx: number, fy: number) {
		const { x1, y1, x2, y2 } = obj.bbox;
		return {
			'@context': 'http://www.w3.org/ns/anno.jsonld',
			id: `${DETECTION_ID_PREFIX}${i}`,
			type: 'Annotation',
			body: [{ type: 'TextualBody', value: detectionLabel(obj), purpose: 'commenting' }],
			target: {
				selector: {
					type: 'FragmentSelector',
					conformsTo: 'http://www.w3.org/TR/media-frags/',
					value: `xywh=pixel:${x1 * fx},${y1 * fy},${(x2 - x1) * fx},${(y2 - y1) * fy}`,
				},
			},
		};
	}

	async function loadDetections() {
		if (!data.photo_id || detectionsFetched) return;
		detectionsFetched = true;
		try {
			const res = await fetchDetections(data.photo_id);
			detectionObjects = res.detected_objects?.objects ?? [];
			detectionDims = res.width && res.height ? { w: res.width, h: res.height } : null;
			console.log('[OSD] Loaded detections:', detectionObjects.length, 'detection space:', detectionDims);
		} catch (e) {
			console.warn('[OSD] Failed to load detections:', e);
			detectionObjects = [];
		}
		syncDetectionsToViewer();
	}

	/** Add/remove detection annotations in the annotator to match the toggle. */
	function syncDetectionsToViewer() {
		if (!annotator) return;
		try {
			for (const a of annotator.getAnnotations()) {
				if (isDetectionId(a.id)) annotator.removeAnnotation(a.id);
			}
			if ($showDetections) {
				const { fx, fy } = detectionScaleFactors();
				detectionObjects.forEach((obj, i) => {
					annotator.addAnnotation(detectionToW3c(obj, i, fx, fy));
				});
			}
		} catch (e) {
			console.warn('[OSD] Could not sync detections to viewer:', e);
		}
		rebuildParsedAnnotations();
		scheduleDrawLabels();
	}

	// React to the debug-overlay toggle (and to the annotator becoming ready)
	$: if (annotator) {
		if ($showDetections && !detectionsFetched) {
			loadDetections();
		} else {
			syncDetectionsToViewer();
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
			.map((a) => toW3cAnnotation(a, dims.w, dims.h));
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
		// setAnnotations() above wiped any detection overlays — re-add them.
		// syncDetectionsToViewer also rebuilds parsed annotations + labels.
		syncDetectionsToViewer();
	}

	/**
	 * Compute the lowest DZI level whose image is at least tile_size pixels
	 * on its longest side.  Levels below this are single sub-tile images —
	 * fetching them is wasteful (one HTTP request each for a tiny image that
	 * OSD never even displays at normal zoom).
	 */
	// Tile-source construction lives in $zoomview/tileSource (extracted for
	// reuse by the enrichment workbench; unit-tested there).

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
		// Detection bboxes are pixel coords in detection space — rescale into
		// the displayed image space (same conversion as the rectangles)
		if ($showDetections) {
			const { fx, fy } = detectionScaleFactors();
			for (let i = 0; i < detectionObjects.length; i++) {
				const b = detectionObjects[i].bbox;
				parsedAnnotations.push({
					dbId: DETECTION_ID_PREFIX + i,
					label: detectionLabel(detectionObjects[i]),
					imgCx: ((b.x1 + b.x2) / 2) * fx,
					imgCy: ((b.y1 + b.y2) / 2) * fy,
				});
			}
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
				if (viewSelectedAnnotation) updateMenuAnchor();
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
			const vp = {
				x1: bounds.x,
				y1: bounds.y,
				x2: bounds.x + bounds.width,
				y2: bounds.y + bounds.height
			};
			zoomViewportBounds.set(vp);
			track('zoomViewPan', {id: data.photo_id ?? '', ...vp});
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

	import {
		buildLabelCommands,
		resolveOverlaps,
		LABEL_PAD,
		LABEL_PILL_H,
		LABEL_GAP,
		type LabelInput,
		type LabelDrawCmd
	} from '$zoomview/labelLayout';
	import { paintLabels } from '$zoomview/labelPaint';
	import { toW3cAnnotation } from '$zoomview/annotationTargets';
	import { OSD_VIEWER_DEFAULTS, initialSourceFor, swapInMainSource } from '$zoomview/viewerInit';

	const BASE_LABEL_FONT_SIZE = 12;
	const LABEL_FONT_FAMILY = 'system-ui,sans-serif';
	const BASE_LABEL_MARGIN = 14;
	const BASE_LEADER_WIDTH = 1.5;
	const BASE_LEADER_DASH = 15;
	const BASE_PILL_RADIUS = 4;
	const BASE_TEXT_BASELINE_OFFSET = 5;
	const BASE_ANNOTATION_STROKE_WIDTH = 1.5;
	let annotationScale = 1;
	let lastAppliedAnnotationScale = annotationScale;
	const DISPLAY_MENU_TEST_ID = 'osd-display-menu';
	let displayMenuBtnEl: HTMLButtonElement | null = null;
	$: displayMenuOpen = $dropdownMenuState.visible && $dropdownMenuState.testId === DISPLAY_MENU_TEST_ID;

	const scaled = () => {
		const scale = annotationScale;
		return {
			scale,
			labelFont: `bold ${BASE_LABEL_FONT_SIZE * scale}px ${LABEL_FONT_FAMILY}`,
			labelPad: LABEL_PAD * scale,
			labelPillH: LABEL_PILL_H * scale,
			labelGap: LABEL_GAP * scale,
			labelMargin: BASE_LABEL_MARGIN * scale,
			leaderWidth: BASE_LEADER_WIDTH * scale,
			leaderDash: BASE_LEADER_DASH * scale,
			pillRadius: BASE_PILL_RADIUS * scale,
			textBaselineOffset: BASE_TEXT_BASELINE_OFFSET * scale,
			strokeWidth: BASE_ANNOTATION_STROKE_WIDTH * scale,
		};
	};

	function getAnnotatorStyle(): (annotation: any) => DrawingStyle {
		const strokeWidth = scaled().strokeWidth;
		return (annotation: any) =>
			isDetectionId(annotation?.id)
				? {
					fill: '#ff3333',
					fillOpacity: 0.08,
					stroke: '#ff3333',
					strokeWidth,
					strokeOpacity: 0.9,
				}
				: {
					fill: '#00ff00',
					fillOpacity: 0.04,
					stroke: '#00ff00',
					strokeWidth,
					strokeOpacity: 0.6,
				};
	}

	function applyAnnotatorScaleStyle() {
		if (!annotator) return;
		annotator.setStyle(getAnnotatorStyle());
	}

	function onAnnotationScaleChanged() {
		applyAnnotatorScaleStyle();
		lastDrawFingerprint = '';
		scheduleDrawLabels();
	}

	$: if (annotationScale !== lastAppliedAnnotationScale) {
		lastAppliedAnnotationScale = annotationScale;
		onAnnotationScaleChanged();
	}

	/** Build the display/actions menu (share + annotation scale).
	 *  The scale slider snippet is declared in markup, so it's passed in from
	 *  the click handler where it's in lexical scope. */
	function buildDisplayMenuItems(scaleSnippet: Snippet): DropdownMenuItem[] {
		const items: DropdownMenuItem[] = [];
		if ($photoInFront) {
			items.push({
				id: 'share',
				label: 'Share photo',
				icon: Share,
				testId: 'osd-share',
				onclick: handleShare,
			});
			items.push({ type: 'divider' });
		}
		items.push({ type: 'custom', id: 'annotation-scale', render: scaleSnippet });
		// only offered where there is something to show: most photos have no
		// graduated overlay, and a dead toggle is worse than no toggle
		if (terrainOverlay) {
			items.push({ type: 'divider' });
			items.push({
				id: 'terrain-overlay',
				label: $showTerrainOverlay ? 'Hide terrain horizon' : 'Show terrain horizon',
				testId: 'osd-terrain-toggle',
				onclick: () => showTerrainOverlay.update((v) => !v),
			});
		}
		return items;
	}

	/** Toggle the display/actions menu from the toolbar menu button. */
	function toggleDisplayMenu(scaleSnippet: Snippet) {
		track('displayMenu');
		if (!displayMenuBtnEl) return;
		toggleDropdownMenu(buildDisplayMenuItems(scaleSnippet), displayMenuBtnEl, {
			placement: 'below-left',
			testId: DISPLAY_MENU_TEST_ID,
		});
	}

	let labelDrawCmds: LabelDrawCmd[] = [];

	function drawLabelsNow() {
		if (!labelCanvas || !viewer?.viewport) return;
		const W = labelCanvas.width;
		const H = labelCanvas.height;

		const ctx = labelCanvas.getContext('2d');
		if (!ctx) return;
		const {
			labelFont,
			labelPad,
			labelPillH,
			labelGap,
			labelMargin,
			leaderWidth,
			leaderDash,
			pillRadius,
			textBaselineOffset
		} = scaled();
		ctx.font = labelFont;

		// Convert image-space annotations to screen-space inputs
		const item = getMainTiledImage();
		if (!item) return;
		const inputs: LabelInput[] = [];
		for (const { dbId, label, imgCx, imgCy } of parsedAnnotations) {
			const vpPt = item.imageToViewportCoordinates(imgCx, imgCy);
			const scPt = viewer.viewport.viewportToViewerElementCoordinates(vpPt);
			const cx = Math.round(scPt.x);
			const cy = Math.round(scPt.y);
			const tw = ctx.measureText(label).width;
			const pillW = tw + labelPad * 2;
			inputs.push({ label, cx, cy, pillW, id: dbId });
		}

		const { cmds, fingerprint: fp } = buildLabelCommands(inputs, W, H, labelMargin, { pillH: labelPillH });
		if (fp === lastDrawFingerprint) return;
		lastDrawFingerprint = fp;

		resolveOverlaps(cmds, W, H, { gap: labelGap });

		// Expose resolved label state for Playwright tests and render clickable overlays
		if (typeof window !== 'undefined') {
			(window as any).__labelDebugCmds = cmds;
		}
		labelDrawCmds = cmds;

		// Painting lives in $zoomview/labelPaint (extracted for reuse by the
		// enrichment workbench; op sequence pinned by unit tests there).
		paintLabels(ctx, W, H, cmds, {
			labelFont,
			labelPad,
			leaderWidth,
			leaderDash,
			pillRadius,
			textBaselineOffset
		});
	}

	let drawTerrainRaf = 0;

	function scheduleDrawTerrain() {
		if (!drawTerrainRaf) {
			drawTerrainRaf = requestAnimationFrame(() => {
				drawTerrainRaf = 0;
				drawTerrainNow();
			});
		}
	}

	/**
	 * The image→screen mapping as a plain affine, sampled from OSD once per
	 * frame instead of per point: converting 4000 skyline vertices through
	 * imageToViewportCoordinates every frame would be the whole frame budget.
	 * Three probes capture translation, scale AND rotation exactly, because
	 * the underlying transform is affine.
	 */
	function imageToScreenAffine(item: any) {
		const conv = (x: number, y: number) =>
			viewer.viewport.viewportToViewerElementCoordinates(
				item.imageToViewportCoordinates(x, y)
			);
		const o = conv(0, 0);
		const ex = conv(1, 0);
		const ey = conv(0, 1);
		return {
			x: (ix: number, iy: number) => o.x + ix * (ex.x - o.x) + iy * (ey.x - o.x),
			y: (ix: number, iy: number) => o.y + ix * (ex.y - o.y) + iy * (ey.y - o.y)
		};
	}

	function drawTerrainNow() {
		if (!terrainCanvas) return;
		const ctx = terrainCanvas.getContext('2d');
		if (!ctx) return;
		const W = terrainCanvas.width;
		const H = terrainCanvas.height;
		ctx.clearRect(0, 0, W, H);
		if (!$showTerrainOverlay || !terrainOverlay || !viewer?.viewport) return;
		const item = getMainTiledImage();
		if (!item) return;
		const size = item.getContentSize();
		if (!size?.x || !size?.y) return;

		const fit = effectiveFit(terrainOverlay);
		// the fit is scale-invariant, so the image's own pixel space is as
		// valid a box as the bench's contain-fitted one — same curve either way
		const proj = createOverlayProjector(fit, size.x, size.y);
		const to = imageToScreenAffine(item);

		// horizon: stroked as separate runs so sky gaps break the line instead
		// of being bridged by a false chord
		const runs = skylinePolylines(terrainOverlay.skyline, proj, fit);
		for (const [width, color] of [
			[4, 'rgba(0,0,0,0.55)'],
			[1.8, 'rgba(255,220,50,0.95)']
		] as [number, string][]) {
			ctx.lineWidth = width;
			ctx.strokeStyle = color;
			ctx.beginPath();
			for (const run of runs) {
				let pen = false;
				for (const p of run) {
					const sx = to.x(p.x, p.y);
					const sy = to.y(p.x, p.y);
					// cull generously: a vertex just off-canvas still anchors
					// the segment that crosses it
					if (sx < -W || sx > 2 * W || sy < -H || sy > 2 * H) {
						pen = false;
						continue;
					}
					if (pen) ctx.lineTo(sx, sy);
					else ctx.moveTo(sx, sy);
					pen = true;
				}
			}
			ctx.stroke();
		}

		// peak labels: sky-anchored pills above their summits, laid out in
		// screen space by the same layouter the bench and terrain viewer use
		ctx.font = '11px system-ui, sans-serif';
		const inputs: { label: string; cx: number; cy: number; pillW: number; id?: string }[] = [];
		for (const m of terrainOverlay.labels ?? []) {
			const pt = proj.projectAzimuth(m.azimuth_deg, m.elev_deg);
			if (!pt) continue;
			const cx = to.x(pt.x, pt.y);
			const cy = to.y(pt.x, pt.y);
			if (cx < 0 || cx > W || cy < 0 || cy > H) continue;
			const km = m.distance_m / 1000;
			const label = `${m.name} · ${km >= 10 ? Math.round(km) : km.toFixed(1)} km`;
			inputs.push({
				label,
				cx,
				cy,
				pillW: Math.ceil(ctx.measureText(label).width) + 12,
				id: m.kind
			});
		}
		ctx.textBaseline = 'middle';
		for (const l of layoutSkyLabels(inputs, W, H, { pillH: 18, leader: 14 })) {
			const isPlace = !!l.id && PLACE_KINDS.has(l.id);
			ctx.strokeStyle = 'rgba(255,255,255,0.55)';
			ctx.lineWidth = 1;
			ctx.beginPath();
			ctx.moveTo(l.cx, l.ty + l.pillH);
			ctx.lineTo(l.cx, l.cy - 3);
			ctx.stroke();
			ctx.beginPath();
			ctx.arc(l.cx, l.cy, 2.2, 0, Math.PI * 2);
			ctx.fillStyle = isPlace ? 'rgba(143,180,217,0.95)' : 'rgba(255,220,50,0.95)';
			ctx.fill();
			ctx.beginPath();
			ctx.roundRect(l.tx, l.ty, l.pillW, l.pillH, 4);
			ctx.fillStyle = isPlace ? 'rgba(20,44,74,0.68)' : 'rgba(0,0,0,0.62)';
			ctx.fill();
			ctx.strokeStyle = 'rgba(255,255,255,0.35)';
			ctx.stroke();
			ctx.fillStyle = '#fff';
			ctx.fillText(l.label, l.tx + 6, l.ty + l.pillH / 2 + 0.5);
		}

		// the answer to the last click: a marker where the user asked, with
		// its coordinates
		if (terrainPick) {
			const sx = to.x(terrainPick.imgX, terrainPick.imgY);
			const sy = to.y(terrainPick.imgX, terrainPick.imgY);
			ctx.beginPath();
			ctx.arc(sx, sy, 6, 0, Math.PI * 2);
			ctx.strokeStyle = 'rgba(0,0,0,0.7)';
			ctx.lineWidth = 3;
			ctx.stroke();
			ctx.strokeStyle = 'rgba(120,220,255,0.98)';
			ctx.lineWidth = 1.6;
			ctx.stroke();
			const km = terrainPick.distance_m / 1000;
			const text =
				`${terrainPick.lat.toFixed(5)}, ${terrainPick.lon.toFixed(5)} · ` +
				`${km >= 10 ? Math.round(km) : km.toFixed(1)} km`;
			const tw = ctx.measureText(text).width;
			ctx.fillStyle = 'rgba(10,26,44,0.82)';
			ctx.beginPath();
			ctx.roundRect(sx - tw / 2 - 6, sy + 10, tw + 12, 18, 4);
			ctx.fill();
			ctx.strokeStyle = 'rgba(120,220,255,0.55)';
			ctx.lineWidth = 1;
			ctx.stroke();
			ctx.fillStyle = '#fff';
			ctx.fillText(text, sx - tw / 2, sy + 19.5);
		}
	}

	/**
	 * Click-anywhere → coordinates. The depth buffer is fetched here, on the
	 * first ask, because it is two orders of magnitude heavier than everything
	 * else the overlay needs and most viewers never click at all.
	 */
	async function pickTerrainAt(imgX: number, imgY: number) {
		const ref = terrainOverlay?.depth;
		if (!terrainOverlay || !ref || terrainPickBusy) return;
		const item = getMainTiledImage();
		const size = item?.getContentSize();
		if (!size?.x || !size?.y) return;
		terrainPickBusy = !overlayDepthReady(ref.url);
		scheduleDrawTerrain();
		try {
			const depth = await loadOverlayDepth(ref.url, ref.width * ref.height);
			const pick = pickFromOverlay(terrainOverlay, depth, imgX, imgY, size.x, size.y);
			terrainPick = pick
				? {
						lat: pick.lat,
						lon: pick.lon,
						distance_m: pick.distance_m,
						imgX,
						imgY
					}
				: null;
		} catch (e) {
			console.warn('[OSD] terrain pick failed:', e);
			terrainPick = null;
		} finally {
			terrainPickBusy = false;
			scheduleDrawTerrain();
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
		// Source selection + swap logic live in $zoomview/viewerInit
		// (extracted for reuse by the enrichment workbench; behavior pinned
		// by unit tests there).
		console.log('[OSD] fallback_url:', JSON.stringify(data.fallback_url), 'main url:', JSON.stringify(data.url));
		const initial = initialSourceFor(data.fallback_url, data.pyramid, data.url);
		usingFallback = initial.usingFallback;

		viewer = new OpenSeadragon.Viewer({
			...OSD_VIEWER_DEFAULTS,
			element: container,
			tileSources: initial.source
			//debugMode: true
		});

		viewer.addHandler('open', () => {
			console.log('[OSD] open event fired, usingFallback:', usingFallback, 'itemCount:', viewer.world.getItemCount());
			// Real source loaded directly, or fallback thumbnail loaded (from
			// browser cache) — either way, dismiss the spinner
			isLoading = false;
			applyInitialBounds();
			if (!usingFallback) return;
			swapInMainSource(viewer, buildTileSource(data.pyramid, data.url));
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
			// Detections are read-only overlays — never selectable
			userSelectAction: (a: any) => isDetectionId(a?.id) ? UserSelectAction.NONE : UserSelectAction.SELECT,
			style: getAnnotatorStyle(),
			drawingMode: 'drag'
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
			track('annotationCreate', {photo: data.photo_id ?? ''});
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
			track('annotationUpdate', {photo: data.photo_id ?? ''});
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
			track('annotationClick', {id: annotation.id});
			// Re-clicking an already-selected shape fires no selectionChanged, so
			// reopen the menu here — otherwise a shape whose menu was dismissed
			// (Escape) would need a deselect round-trip before it responds again.
			if (annotationMode !== 'edit' && viewSelectedAnnotation
				&& uiToDb.get(annotation.id) === viewSelectedAnnotation.id) {
				openViewAnnotationMenu();
			}
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
				// View-mode selection: open the annotation's context menu
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
				updateMenuAnchor();
				openViewAnnotationMenu();
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

		// Terrain overlay sits UNDER the annotation labels (z-index 1 vs 2):
		// annotations are the user's own content and must stay readable over
		// a horizon line that spans the whole frame.
		terrainCanvas = document.createElement('canvas');
		terrainCanvas.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:1';
		terrainCanvas.dataset.testid = 'osd-terrain-canvas';
		container.appendChild(terrainCanvas);

		resizeObserver = new ResizeObserver(() => {
			if (!labelCanvas) return;
			labelCanvas.width  = container.offsetWidth;
			labelCanvas.height = container.offsetHeight;
			if (terrainCanvas) {
				terrainCanvas.width  = container.offsetWidth;
				terrainCanvas.height = container.offsetHeight;
			}
			scheduleDrawLabels();
			scheduleDrawTerrain();
		});
		resizeObserver.observe(container);

		viewer.addHandler('viewport-change', scheduleDrawLabels);
		viewer.addHandler('update-viewport',  scheduleDrawLabels);
		viewer.addHandler('viewport-change', scheduleDrawTerrain);
		viewer.addHandler('update-viewport',  scheduleDrawTerrain);
		viewer.addHandler('viewport-change', emitViewportBounds);
		viewer.addHandler('update-viewport',  emitViewportBounds);

		// Close the viewer when the user clicks/taps the black background
		// outside the image bounds (mirrors original ZoomView behaviour).
		// event.quick distinguishes a tap/click from a pan/zoom drag — OSD sets
		// quick=false when the pointer moved significantly before release.
		viewer.addHandler('canvas-click', (event: any) => {
			if (!event.quick || annotationMode !== 'view') return;
			const pt = event.position; // viewer-element coordinates

			// Check if click hits an annotation label pill.
			// Labels use pointer-events: none so touch events pass through to
			// OSD for pinch-zoom; we handle label taps here via hit-testing.
			for (const cmd of labelDrawCmds) {
				if (pt.x >= cmd.tx && pt.x <= cmd.tx + cmd.pillW &&
					pt.y >= cmd.ty && pt.y <= cmd.ty + cmd.pillH) {
					event.preventDefaultAction = true;
					handleCanvasLabelClick(cmd);
					return;
				}
			}

			const itemCount = viewer.world.getItemCount();
			const item = itemCount > 0 ? viewer.world.getItemAt(itemCount - 1) : null;
			if (!item) { onClose(); return; }
			const imgBounds = item.getBounds(); // viewport coordinates
			const scrBounds = viewer.viewport.viewportToViewerElementRectangle(imgBounds);

			// Terrain overlay on: a tap ON the photo asks "what am I looking
			// at?" instead of doing nothing. Taps outside the image still fall
			// through to the close-on-background behaviour below.
			if ($showTerrainOverlay && terrainOverlay?.depth) {
				const inside =
					pt.x >= scrBounds.x && pt.x <= scrBounds.x + scrBounds.width &&
					pt.y >= scrBounds.y && pt.y <= scrBounds.y + scrBounds.height;
				if (inside) {
					event.preventDefaultAction = true;
					const vpPt = viewer.viewport.viewerElementToViewportCoordinates(pt);
					const imgPt = item.viewportToImageCoordinates(vpPt);
					pickTerrainAt(imgPt.x, imgPt.y);
					return;
				}
			}

			// Expand the interaction zone around the image to at least 50% of
			// the container in each dimension.  Taps inside this zone do NOT
			// close the viewer — this makes thin panoramas much easier to
			// pinch-zoom without accidentally dismissing the viewer.
			const cw = container.offsetWidth;
			const ch = container.offsetHeight;
			const minW = cw * 0.5;
			const minH = ch * 0.5;
			let zx = scrBounds.x;
			let zy = scrBounds.y;
			let zw = scrBounds.width;
			let zh = scrBounds.height;
			if (zw < minW) {
				const cx = zx + zw / 2;
				zx = cx - minW / 2;
				zw = minW;
			}
			if (zh < minH) {
				const cy = zy + zh / 2;
				zy = cy - minH / 2;
				zh = minH;
			}

			if (
				pt.x < zx ||
				pt.x > zx + zw ||
				pt.y < zy ||
				pt.y > zy + zh
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
		viewer?.removeHandler('viewport-change', scheduleDrawTerrain);
		viewer?.removeHandler('update-viewport',  scheduleDrawTerrain);
		viewer?.removeHandler('viewport-change', emitViewportBounds);
		viewer?.removeHandler('update-viewport',  emitViewportBounds);
		if (viewportBoundsTimeout) { clearTimeout(viewportBoundsTimeout); viewportBoundsTimeout = null; }
		if (ratingMessageTimeout) { clearTimeout(ratingMessageTimeout); ratingMessageTimeout = null; }
		zoomViewportBounds.set(null);
		if (drawLabelsRaf) { cancelAnimationFrame(drawLabelsRaf); drawLabelsRaf = 0; }
		if (drawTerrainRaf) { cancelAnimationFrame(drawTerrainRaf); drawTerrainRaf = 0; }
		// the decoded depth buffer is megabytes — don't hold it once the zoom
		// view is gone
		releaseOverlayDepth();
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
		// Detections are read-only overlays — never selectable/editable
		annotator.setUserSelectAction((a: any) => isDetectionId(a?.id) ? UserSelectAction.NONE : selectAction);
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
			if (displayMenuOpen) {
				closeDropdownMenu();
			} else if (textModalContent) {
				textModalContent = null;
			} else if (editingAnnotation) {
				cancelEditBody();
			} else if (viewSelectedAnnotation) {
				clearViewSelection();
				annotator?.setSelected?.();
			} else {
				onClose();
			}
		} else if (e.key === 'd') {
			if (requireAuth()) setAnnotationMode(annotationMode === 'draw' ? 'view' : 'draw');
		} else if (e.key === 'e') {
			if (requireAuth()) setAnnotationMode(annotationMode === 'edit' ? 'view' : 'edit');
		} else {
			const rating = ratingShortcutFor(e);
			if (rating) {
				e.preventDefault();
				handleRatingKey(rating);
			}
		}
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="osd-overlay" data-testid="osd-viewer-overlay">
	{#if $showPhotoInfoWindow}
		<PhotoInfoWindow photo={$photoInFront} variant="zoom"/>
	{/if}

	<!--
		Terrain data attribution. Displaying it is a LICENCE OBLIGATION, not
		decoration (docs/terrain-data-licensing.md): the DEM notice rides in
		each overlay because a render made from other sources carries a
		different one. Shown whenever the overlay is drawn, and the OSM credit
		only while its labels are on screen.
	-->
	{#if $showTerrainOverlay && terrainOverlay?.attribution}
		<div class="terrain-attribution" data-testid="osd-terrain-attribution">
			{terrainOverlay.attribution}{#if terrainOverlay.label_attribution && terrainOverlay.labels?.length}
				· {terrainOverlay.label_attribution}{/if}
		</div>
	{/if}

	{#if $showTerrainOverlay && terrainPickBusy}
		<div class="terrain-busy" data-testid="osd-terrain-busy">reading terrain…</div>
	{/if}

	<!-- Close button -->
	<button class="close-btn" onclick={onClose} aria-label="Close zoom view" data-testid="osd-viewer-close">
		<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
			<path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
		</svg>
	</button>

	<!-- Toolbar -->
	<div class="annotation-toolbar">
		<button
			class="toolbar-btn toolbar-btn-menu"
			class:active={displayMenuOpen}
			bind:this={displayMenuBtnEl}
			onclick={() => toggleDisplayMenu(scaleControl)}
			title="Menu"
			aria-label="Display and actions menu"
			data-testid="osd-display-menu-toggle"
			aria-haspopup="menu"
			aria-expanded={displayMenuOpen}
		>
			<MoreVertical size={18} aria-hidden="true" />
		</button>
		<button
			class="toolbar-btn toolbar-btn-draw"
			class:active={annotationMode === 'draw'}
			onclick={() => { if (requireAuth()) setAnnotationMode(annotationMode === 'draw' ? 'view' : 'draw'); }}
			title={annotationMode === 'draw' ? 'Stop drawing' : 'Draw annotation'}
			data-testid="osd-annotate-draw"
		>
			✏️ Draw
		</button>
		<button
			class="toolbar-btn toolbar-btn-edit"
			class:active={annotationMode === 'edit'}
			onclick={() => { if (requireAuth()) setAnnotationMode(annotationMode === 'edit' ? 'view' : 'edit'); }}
			title={annotationMode === 'edit' ? 'Stop editing' : 'Edit annotations'}
			data-testid="osd-annotate-edit"
		>
			🔧 Edit
		</button>
	</div>

	{#snippet scaleControl()}
		<div class="display-menu-scale" data-testid="osd-display-menu-scale">
			<div class="display-menu-scale-header">
				<label id="osd-annotation-scale-label" class="display-menu-scale-label" for="osd-annotation-scale">Annotation scale</label>
				<span class="display-menu-scale-value" aria-live="polite">{annotationScale.toFixed(1)}×</span>
			</div>
			<input
				id="osd-annotation-scale"
				class="display-menu-scale-slider"
				type="range"
				min="1"
				max="3"
				step="0.1"
				bind:value={annotationScale}
				aria-labelledby="osd-annotation-scale-label"
				data-testid="osd-annotation-scale-slider"
			/>
		</div>
	{/snippet}

	<!-- Share status message -->
	{#if shareMessage}
		<div class="share-message" class:error={shareMessageError}>{shareMessage}</div>
	{/if}

	<!-- Rating status message (no like/dislike buttons in this view) -->
	{#if ratingMessage}
		<div class="rating-message" data-testid="osd-rating-toast">{ratingMessage}</div>
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

	<!-- Clickable label pill overlays -->
	{#each labelDrawCmds as cmd (cmd.id ?? cmd.label)}
		<button
			class="label-click-target"
			style:left="{cmd.tx}px"
			style:top="{cmd.ty}px"
			style:width="{cmd.pillW}px"
			style:height="{cmd.pillH}px"
			data-testid="label-click-{cmd.id}"
			onclick={(e) => handleLabelClick(e, cmd)}
			aria-label="Annotation: {cmd.label}"
		></button>
	{/each}

	<!-- Annotation text detail modal -->
	{#if textModalContent}
		<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
		<div class="text-modal-overlay" data-testid="annotation-text-modal"
			onclick={() => { if (Date.now() - textModalOpenedAt > 40) textModalContent = null; }}>
			<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
			<div class="text-modal" onclick={(e) => e.stopPropagation()}>
				<!-- runs rendered without stray template whitespace: the body is
				     white-space: pre-wrap, so any newline here would be visible -->
				<p class="text-modal-body">{#each splitOnCoords(textModalContent) as run}{#if run.type === 'coords'}<a
							class="coord-link"
							href={coordsMapUrl(run.lat, run.lon)}
							target="_blank"
							rel="noopener noreferrer"
							data-testid="annotation-text-modal-coords"
							onclick={(e) => handleCoordLinkClick(e, run.text, run.lat, run.lon)}
						>{run.text}</a>{:else}{run.value}{/if}{/each}</p>
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
		<div class="filename-bar">{data.title || data.description || data.filename}</div>
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
		gap: 6px;
	}

	.toolbar-btn {
		background: rgba(255,255,255,0.85);
		border: 2px solid transparent;
		border-radius: 8px;
		padding: 6px 10px;
		cursor: pointer;
		font-size: 13px;
		font-weight: 500;
		color: #222;
	}

	.toolbar-btn-menu {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 6px;
		color: #444;
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

	.toolbar-btn-menu.active {
		border-color: #6c757d;
		background: rgba(108,117,125,0.8);
		color: #fff;
	}

	.display-menu-scale {
		display: flex;
		flex-direction: column;
		gap: 6px;
		padding: 8px 14px;
		min-width: 200px;
	}

	.display-menu-scale-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 8px;
	}

	.display-menu-scale-label {
		font-size: 13px;
		font-weight: 500;
		color: #1f2937;
	}

	.display-menu-scale-value {
		font-size: 13px;
		font-weight: 600;
		color: #1f2937;
	}

	.display-menu-scale-slider {
		width: 100%;
		margin: 0;
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

	.rating-message {
		position: absolute;
		top: calc(56px + var(--safe-area-inset-top, 0px));
		left: 50%;
		transform: translateX(-50%);
		z-index: 10;
		background: rgba(33, 37, 41, 0.92);
		color: white;
		padding: 8px 14px;
		border-radius: 4px;
		font-size: 14px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
		animation: fadeIn 0.3s ease;
		pointer-events: none;
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

	.coord-link {
		color: #7cc4ff;
		text-decoration: underline;
		cursor: pointer;
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

	/* Terrain data credits — a licence obligation, so it must stay legible
	   over any photo and must not be clipped away on narrow screens. */
	.terrain-attribution {
		position: absolute;
		left: 8px;
		right: 8px;
		bottom: 6px;
		z-index: 4;
		pointer-events: none;
		font-size: 10px;
		line-height: 1.3;
		color: rgba(255, 255, 255, 0.82);
		text-shadow: 0 1px 3px rgba(0, 0, 0, 0.9);
		text-align: center;
	}

	.terrain-busy {
		position: absolute;
		left: 50%;
		top: 12px;
		transform: translateX(-50%);
		z-index: 4;
		pointer-events: none;
		font-size: 11px;
		padding: 3px 10px;
		border-radius: 10px;
		color: #fff;
		background: rgba(10, 26, 44, 0.82);
	}

	.label-click-target {
		position: absolute;
		z-index: 3; /* above the label canvas (z-index: 2) */
		background: transparent;
		border: none;
		padding: 0;
		border-radius: 4px;
		/* pointer-events: none so all touch events pass through to OSD
		   for pinch-zoom.  Label clicks are handled via OSD's canvas-click
		   hit-testing instead.  Keyboard focus still works for a11y. */
		pointer-events: none;
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
