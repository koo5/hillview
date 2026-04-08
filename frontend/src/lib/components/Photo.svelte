<script lang="ts">
	import {onMount, onDestroy} from 'svelte';
	import PhotoActionsMenu from './PhotoActionsMenu.svelte';
	import Spinner from './Spinner.svelte';
	import {app} from '$lib/data.svelte.js';
	import {auth} from '$lib/auth.svelte.js';
	import {http, handleApiError} from '$lib/http';
	import {myGoto} from '$lib/navigation.svelte.js';
	import {getDevicePhotoUrl} from '$lib/devicePhotoHelper';
	import {simplePhotoWorker} from '$lib/simplePhotoWorker';
	import {zoomViewData, pendingZoomView} from '$lib/zoomView.svelte.js';
	import {singleTap} from '$lib/actions/singleTap';
	import {panZoom} from '$lib/actions/panZoom';
	const doLog = false;
	import {portal} from '$lib/actions/portal';
	import {getFullPhotoInfo, getPhotoSource} from '$lib/photoUtils';
	import HideUserDialog from './HideUserDialog.svelte';
	import PhotoInfoLabels from './PhotoInfoLabels.svelte';
	import {fetchAnnotations, type AnnotationData} from '$lib/annotationApi';
	import type {PhotoData} from '$lib/sources';

	export let photo: PhotoData | null = null;
	let annotations: AnnotationData[] = [];
	let annotationPhotoId: string | null = null;

	$: if (className === 'front' && photo?.id !== annotationPhotoId) {
		loadAnnotations(photo);
	}

	async function loadAnnotations(p: PhotoData | null) {
		const photoId = p?.id ?? null;
		annotationPhotoId = photoId;
		if (!photoId) {
			annotations = [];
			return;
		}
		try {
			annotations = await fetchAnnotations(photoId);
		} catch (e) {
			console.error('Photo: Failed to fetch annotations:', e);
			annotations = [];
		}
	}

	// Track pending timeouts for cleanup
	const pendingTimeouts = new Set<ReturnType<typeof setTimeout>>();

	function scheduleTimeout(callback: () => void, delay: number): ReturnType<typeof setTimeout> {
		const id = setTimeout(() => {
			pendingTimeouts.delete(id);
			callback();
		}, delay);
		pendingTimeouts.add(id);
		return id;
	}

	onDestroy(() => {
		// Note: do NOT clear zoomViewData here. When the gallery re-keys
		// (e.g. photo worker update), Photo components are destroyed and
		// recreated — clearing the store would close the OSD viewer the
		// user explicitly opened. Cleanup is handled by Gallery instead.
		for (const id of pendingTimeouts) {
			clearTimeout(id);
		}
		pendingTimeouts.clear();
	});
	export let className = '';
	export let clientWidth: number | undefined = undefined;
	export let onInteraction: (() => void) | undefined = undefined;

	let clientWidth2: number | undefined;

	let fetchPriority = className === 'front' ? 'high' : 'auto';

	let containerElement: HTMLElement | undefined;
	let selectedUrl: string | undefined;
	let selectedSize: any;
	let width = 100;
	let height = 100;
	let devicePhotoUrl: string | null = null;
	let bg_style_stretched_photo;
	let border_style;

	// Background loading state
	let displayedUrl: string | undefined;
	let isLoadingNewImage = false;
	let preloadImg: HTMLImageElement | null = null;

	// Hide functionality state
	let showHideUserDialog = false;
	let hideMessage = '';


	//$: console.log('🢄Photo.svelte: photo changed:', JSON.stringify(photo));

	// Get current user authentication state
	$: is_authenticated = $auth.is_authenticated;

	// enable for stretched backdrop
	//$: bg_style_stretched_photo = photo.sizes?.[50] ? `background-image: url(${photo.sizes[50].url});` : ''

	$: border_style = ''//className === 'front' && photo ? 'border: 4px dotted #4a90e2;' : '';
	//console.log('🢄border_style:', border_style);

	$: if (photo || clientWidth || containerElement) updateSelectedUrl();

	// Handle selectedUrl changes with background loading
	$: if (selectedUrl !== undefined && selectedUrl !== displayedUrl) {
		handleImageChange(selectedUrl);
	}

	async function updateSelectedUrl() {

		if (clientWidth)
			clientWidth2 = clientWidth;
		else if (!clientWidth2)
			clientWidth2 = 500;

		//console.log('🢄updateSelectedUrl clientWidth:', clientWidth2);

		if (!containerElement) {
			return;
		}

		if (!photo) {
			selectedUrl = '';
			devicePhotoUrl = null;
			return;
		}

		// Handle device photos specially
		if (photo.is_device_photo && photo.url) {
			try {
				devicePhotoUrl = getDevicePhotoUrl(photo.url);
				selectedUrl = devicePhotoUrl;
				/*console.log('🢄Photo.svelte: Device photo URL conversion:', {
					originalUrl: photo.url,
					convertedUrl: devicePhotoUrl,
					photoId: photo.id
				});*/
				return;
			} catch (error) {
				console.error('🢄Failed to load device photo:', error);
				selectedUrl = '';
				return;
			}
		}

		if (!photo.sizes) {
			if (doLog) console.log('🢄Photo.svelte: No sizes, using photo.url:', photo.url);
			selectedUrl = photo.url;
			return;
		}

		//console.log('🢄Photo.svelte: Processing sizes for photo:', photo.id, 'is_device_photo:', photo.is_device_photo, 'sizes:', Object.keys(photo.sizes), 'clientWidth:', clientWidth2);

		// Find the best scaled version based on container width. Take the 'full' size if this fails
		const sizes = Object.keys(photo.sizes).filter(size => /^\d+$/.test(size)).sort((a, b) => Number(a) - Number(b));
		let p: any;
		for (let i = 0; i < sizes.length; i++) {
			const size = sizes[i];
			//console.log('🢄size:', size);
			if (Number(size) >= clientWidth2 || ((i === sizes.length - 1) && !photo.sizes.full)) {
				p = photo.sizes[sizes[i]];
				selectedSize = size;
				width = p.width;
				height = p.height;

				// Handle device photo URLs
				if (photo.is_device_photo) {
					selectedUrl = getDevicePhotoUrl(p.url);
				} else {
					selectedUrl = p.url;
				}
				return;
			}
		}
		selectedSize = 'full';
		width = photo.sizes.full?.width || p?.width || 0;
		height = photo.sizes.full?.height || p?.height || 0;

		// Handle device photo URLs for full size
		if (photo.is_device_photo && photo.sizes.full) {
			selectedUrl = getDevicePhotoUrl(photo.sizes.full.url);
			//console.log('🢄Photo.svelte: Using full size for device photo:', photo.id, 'original:', photo.sizes.full.url, 'converted:', selectedUrl);
		} else {
			selectedUrl = photo.sizes.full?.url || '';
			/*console.log('🢄Photo.svelte: Using full size for regular photo:', {
				photoId: photo.id,
				selectedUrl: selectedUrl
			});*/
		}

		/*console.log('🢄Photo.svelte: URL flow debug:', JSON.stringify({
			photoId: photo.id,
			is_device_photo: photo.is_device_photo,
			selectedUrl: selectedUrl,
			currentDisplayedUrl: displayedUrl,
			willTriggerImageChange: selectedUrl !== displayedUrl
		}));*/
	}

	async function handleImageChange(newUrl: string) {
		/*console.log('🢄Photo.svelte: handleImageChange called:', JSON.stringify({
			newUrl: newUrl,
			currentDisplayedUrl: displayedUrl,
			willReturn: !newUrl || newUrl === displayedUrl
		}));*/

		// hmm..
		if (!newUrl || newUrl === displayedUrl) {
			return;
		}

		// If this is the first image or no previous image, show immediately
		if (!displayedUrl) {
			displayedUrl = newUrl;
			return;
		}

		// Start background loading
		isLoadingNewImage = true;

		try {
			preloadImg = new Image();

			preloadImg.onload = () => {
				displayedUrl = newUrl;
				isLoadingNewImage = false;
				preloadImg = null;
			};

			preloadImg.onerror = () => {
				console.error('🢄Failed to preload image:', newUrl);
				isLoadingNewImage = false;
				preloadImg = null;
			};

			preloadImg.src = newUrl;

		} catch (error) {
			console.error('🢄Error preloading image:', error);
			isLoadingNewImage = false;
		}
	}

	function getUserId(photo: PhotoData): string | null {
		if (!photo) return null;

		// For Mapillary photos, check if creator info exists in the photo data
		if ((photo as any).creator?.id) {
			return (photo as any).creator.id;
		}
		// For Hillview photos, check for owner_id field
		if ((photo as any).owner_id) {
			return (photo as any).owner_id;
		}
		return null;
	}

	function getUserName(photo: PhotoData): string | null {
		if (!photo) return null;

		// For Mapillary photos, check if creator info exists in the photo data
		if ((photo as any).creator?.username) {
			return (photo as any).creator.username;
		}
		// For Hillview photos, check for owner_username field
		if ((photo as any).owner_username) {
			return (photo as any).owner_username;
		}
		return null;
	}

	// --- Pinch-zoom / pan state ---
	let zoomScale = 1;
	let zoomTx = 0;
	let zoomTy = 0;
	let isZoomedIn = false;

	$: isFront = className === 'front';
	$: zoomTransform = zoomScale > 1.01
		? `translate(${zoomTx}px, ${zoomTy}px) scale(${zoomScale})`
		: '';

	function handlePanZoomUpdate(state: { scale: number; translateX: number; translateY: number }) {
		zoomScale = state.scale;
		zoomTx = state.translateX;
		zoomTy = state.translateY;
	}

	function handleZoomChange(zoomed: boolean) {
		isZoomedIn = zoomed;
		if (zoomed) {
			onInteraction?.();
		}
	}

	// Scale above which a released pinch promotes the inline preview into the
	// full ZoomView, carrying the current zoom/pan as initial bounds. Below
	// this, the gesture is treated as incidental and the inline snaps back.
	const PINCH_PROMOTE_SCALE = 1.15;

	function handlePinchEnd() {
		if (!isFront || !photo) return;
		if (zoomScale <= PINCH_PROMOTE_SCALE) {
			// Not a deliberate zoom — snap back to 1x inline.
			(containerElement as any)?.__panZoom_action?.reset();
			return;
		}

		const cw = clientWidth2 || containerElement?.clientWidth || 0;
		const ch = containerElement?.clientHeight || 0;
		if (width && height && cw && ch) {
			// The inline image is letterboxed (object-fit: contain) inside a
			// container of size (cw, ch). Its rendered rect in pre-transform
			// zoom-container space:
			const fit = Math.min(cw / width, ch / height);
			const rw = width * fit;
			const rh = height * fit;
			const ix0 = (cw - rw) / 2;
			const iy0 = (ch - rh) / 2;

			// Visible viewport in pre-transform zoom-container coordinates.
			// Transform is translate(tx, ty) scale(s) with origin (0,0), so
			// screen (0..cw, 0..ch) maps back to ((-tx)/s..(cw-tx)/s, ...).
			const vx1 = -zoomTx / zoomScale;
			const vy1 = -zoomTy / zoomScale;
			const vx2 = (cw - zoomTx) / zoomScale;
			const vy2 = (ch - zoomTy) / zoomScale;

			// Convert to OSD viewport coords (image width = 1 unit, image
			// height = aspectRatio). Both axes normalize by rw since OSD's
			// y-axis is in image-width units.
			const aspectY = height / width;
			const clamp = (v: number, lo: number, hi: number) =>
				Math.max(lo, Math.min(hi, v));
			const x1 = clamp((vx1 - ix0) / rw, 0, 1);
			const y1 = clamp((vy1 - iy0) / rw, 0, aspectY);
			const x2 = clamp((vx2 - ix0) / rw, 0, 1);
			const y2 = clamp((vy2 - iy0) / rw, 0, aspectY);

			if (x2 > x1 && y2 > y1) {
				pendingZoomView.set({x1, y1, x2, y2});
			}
		}

		openZoomView(photo);
		(containerElement as any)?.__panZoom_action?.reset();
	}

	// Reset zoom when photo changes
	let lastPhotoId: string | undefined;
	$: if (photo?.id !== lastPhotoId) {
		lastPhotoId = photo?.id;
		zoomScale = 1;
		zoomTx = 0;
		zoomTy = 0;
		isZoomedIn = false;
	}

	// panZoom options — reactive so container size updates propagate
	$: panZoomOptions = isFront ? {
		onUpdate: handlePanZoomUpdate,
		onZoomChange: handleZoomChange,
		onPinchEnd: handlePinchEnd,
		isEmbedded: true,
		minScale: 0.8,
		maxScale: 5,
		imageWidth: width,
		imageHeight: height,
		containerWidth: clientWidth2 || 500,
		containerHeight: containerElement?.clientHeight || 500,
	} : undefined;

	// --- Annotation canvas overlay ---
	let annotationCanvas: HTMLCanvasElement | undefined;
	let imgElement: HTMLImageElement | undefined;

	function parseAnnotationRect(target: any): {x: number, y: number, w: number, h: number} | null {
		const selector = Array.isArray(target?.selector) ? target.selector[0] : target?.selector;
		if (selector?.type === 'RECTANGLE' && selector.geometry) {
			const g = selector.geometry;
			return {x: g.x, y: g.y, w: g.w, h: g.h};
		}
		if (typeof selector?.value === 'string') {
			const match = selector.value.match(/xywh=pixel:([\d.]+),([\d.]+),([\d.]+),([\d.]+)/);
			if (match) return {x: +match[1], y: +match[2], w: +match[3], h: +match[4]};
		}
		return null;
	}

	function drawAnnotations() {
		if (!annotationCanvas || !imgElement) return;
		const ctx = annotationCanvas.getContext('2d');
		if (!ctx) return;

		const cw = containerElement?.clientWidth || annotationCanvas.clientWidth;
		const ch = containerElement?.clientHeight || annotationCanvas.clientHeight;
		if (!width || !height) return;

		annotationCanvas.width = cw;
		annotationCanvas.height = ch;
		ctx.clearRect(0, 0, cw, ch);

		// Compute rendered image rect (object-fit: contain letterboxing).
		// Annotation coords are [0,1] normalized, so multiply by rendered dims.
		const scale = Math.min(cw / width, ch / height);
		const rw = width * scale, rh = height * scale;
		const rx = (cw - rw) / 2, ry = (ch - rh) / 2;

		ctx.strokeStyle = 'rgba(0, 255, 0, 0.8)';
		ctx.lineWidth = 1.5;

		for (const ann of annotations) {
			const rect = parseAnnotationRect(ann.target);
			if (!rect) continue;
			ctx.strokeRect(
				rx + rect.x * rw,
				ry + rect.y * rh,
				rect.w * rw,
				rect.h * rh
			);
		}
	}

	$: if (annotations && displayedUrl && annotationCanvas && imgElement) {
		// Use tick to ensure img has rendered at its new size
		drawAnnotations();
	}

	function openZoomView(photo: PhotoData) {
		if (!photo) return;

		// Notify parent about the interaction to reset swipe state
		if (doLog) console.log('🢄Photo: Opening zoom view, notifying parent about interaction');
		if (doLog) console.log('🢄Photo: onInteraction callback:', onInteraction);
		onInteraction?.();

		const fallbackUrl = displayedUrl || selectedUrl || '';
		if (doLog) console.log('🢄Photo.svelte: [zoomview] Opening zoom view for photo:', JSON.stringify(photo));
		const fullPhotoInfo = getFullPhotoInfo(photo);

		if (doLog) console.log('🢄Photo.svelte: [zoomview] Full photo info:', JSON.stringify(fullPhotoInfo));

		zoomViewData.set({
			fallback_url: fallbackUrl,
			url: fullPhotoInfo.url,
			filename: photo.filename,
			description: photo.description,
			width: fullPhotoInfo.width,
			height: fullPhotoInfo.height,
			photo_id: photo.id,
			pyramid: (photo as any).sizes?.full?.pyramid ?? undefined,
		});
	}




</script>
{#if $app.debug === 5}
	<div class="debug">
		<b>Debug Information</b><br>
		<b>clientWidth2:</b> {clientWidth2}<br>
		<b>Selected URL:</b> {JSON.stringify(selectedUrl)}<br>
		<b>Selected Size:</b> {selectedSize}
		<b>Width:</b> {width}
		<b>Height:</b> {height}
		<b>Photo:</b>
		<pre>{JSON.stringify(photo, null, 2)}</pre>
	</div>
{/if}


<div bind:this={containerElement} class="photo-wrapper" class:zoomed={isZoomedIn}
	 use:panZoom={panZoomOptions || { onUpdate: () => {}, isEmbedded: true }}>

	{#if photo?.is_placeholder}
		<div class="placeholder-container" data-testid="placeholder-photo">
			<div class="placeholder-content">
				<Spinner />
				<div class="placeholder-text">Saving photo...</div>
			</div>
		</div>
	{/if}

	{#if photo && !photo.is_placeholder}
		<div class="zoom-container" style:transform={zoomTransform} style:transform-origin="0 0">
			<img
				bind:this={imgElement}
				src={displayedUrl}
				alt={photo.filename}
				style="{bg_style_stretched_photo} {border_style}"
				fetchpriority={fetchPriority as any}
				data-testid="main-photo"
				data-photo={JSON.stringify(photo)}
				onerror={(e) => {
					// onerror is "obsolete attributes" according to MDN, but still works. Eventually, we'll replace this with the service worker.
					console.error('🢄Photo.svelte: Image load error:', JSON.stringify({
						photoId: photo?.id,
						displayedUrl: displayedUrl,
						is_device_photo: photo?.is_device_photo,
						originalUrl: photo?.url,
						errorMessage: e?.toString?.() || 'Unknown error'
					}));
				}}
				onload={() => {
					if (doLog) console.log('🢄Photo.svelte: Image loaded successfully:', JSON.stringify({
						photoId: photo?.id,
						displayedUrl: displayedUrl,
						is_device_photo: photo?.is_device_photo
					}));
					drawAnnotations();
				}}
				class="photo {className}"
				use:singleTap={{ callback: () => openZoomView(photo), edgeMargin: 30 }}
			/>

			<!-- Annotation rectangles overlay -->
			{#if className === 'front' && annotations.length > 0}
				<canvas
					bind:this={annotationCanvas}
					class="annotation-canvas"
					data-testid="annotation-canvas"
				></canvas>
			{/if}
		</div>

		<!-- Loading spinner overlay -->
		{#if isLoadingNewImage}
			<div class="photo-loading-overlay" data-testid="photo-loading-spinner">
				<div class="photo-spinner"></div>
			</div>
		{/if}

		<!-- Photo actions for front photo only -->
		{#if className === 'front'}
			<PhotoInfoLabels {photo} {annotations} />
			<div class="photo-actions-container">
				<PhotoActionsMenu
					{photo}
					bind:showHideUserDialog
				/>
			</div>
		{/if}

		<!-- Status message -->
		{#if hideMessage}
			<div class="hide-message" class:error={hideMessage.startsWith('Error')}>
				{hideMessage}
			</div>
		{/if}
	{/if}
</div>

{#if photo}
	<HideUserDialog
		bind:show={showHideUserDialog}
		userId={getUserId(photo) || ''}
		username={getUserName(photo)}
		userSource={(getPhotoSource(photo) || 'hillview') as 'hillview' | 'mapillary'}
	/>
{/if}

<style>
	.debug {
		overflow: auto;
		position: absolute;
		top: 130;
		left: 100;
		padding: 0.5rem;
		background: #f0f070;
		border: 1px solid black;
		z-index: 1000;
		width: 320px; /* Fixed width */
		height: 320px; /* Fixed height */
	}

	.photo-wrapper {
		position: relative;
		display: flex;
		justify-content: center;
		width: 100%;
		height: 100%;
		max-width: 100%;
		max-height: 100%;
		object-fit: contain;
		background-repeat: no-repeat;
		overflow: hidden;
		touch-action: none;
	}

	.zoom-container {
		display: flex;
		justify-content: center;
		align-items: center;
		width: 100%;
		height: 100%;
		position: relative;
	}

	.annotation-canvas {
		position: absolute;
		top: 0;
		left: 0;
		width: 100%;
		height: 100%;
		pointer-events: none;
		z-index: 3;
	}

	.photo {
		object-fit: contain;
		background-size: cover;
		-o-background-size: cover;
		max-width: 100%;
		max-height: 100%;
		width: auto;
		height: auto;
	}

	.photo-actions-container {
		position: absolute;
		bottom: 12px;
		right: 10px;
		z-index: 100000;
		display: flex;
	}


	/* Front image is centered and on top */
	.front {
		z-index: 2;
	}


	/* Status message */
	.hide-message {
		position: absolute;
		bottom: 60px;
		right: 10px;
		background: rgba(40, 167, 69, 0.9);
		color: white;
		padding: 8px 12px;
		border-radius: 4px;
		font-size: 14px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
		z-index: 10;
		animation: fadeIn 0.3s ease;
	}

	.hide-message.error {
		background: rgba(220, 53, 69, 0.9);
	}

	@keyframes fadeIn {
		from {
			opacity: 0;
			transform: translateY(10px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	/* Photo loading overlay */
	.photo-loading-overlay {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		/*background-color: rgba(0, 0, 0, 0.3);*/
		z-index: 8;
		pointer-events: none;
	}

	/* Simple spinner animation */
	.photo-spinner {
		width: 40px;
		height: 40px;
		border: 4px solid rgba(255, 255, 255, 0.3);
		border-top: 4px solid #ffffff;
		border-radius: 50%;
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		0% {
			transform: rotate(0deg);
		}
		100% {
			transform: rotate(360deg);
		}
	}

	.placeholder-container {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		background: linear-gradient(135deg, #f0f0f0 0%, #e0e0e0 100%);
		border-radius: 8px;
		z-index: 5;
	}

	.placeholder-content {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 12px;
		opacity: 0.8;
	}

	.placeholder-text {
		font-size: 14px;
		color: #666;
		font-weight: 500;
	}

</style>
