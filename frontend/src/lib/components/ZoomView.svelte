<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { browser } from '$app/environment';
	import { zoomViewData, type ZoomViewData } from '$lib/zoomView.svelte';
	import { panZoom } from '$lib/actions/panZoom';
	import { app } from '$lib/data.svelte';

	let container = $state<HTMLDivElement>();
	let translateX = $state(0);
	let translateY = $state(0);
	let imageWidth = $state<number | undefined>($zoomViewData?.width);
	let imageHeight = $state<number | undefined>($zoomViewData?.height);

	// Get container dimensions from the actual container element
	let containerWidth = $derived(container ? container.clientWidth : (browser ? window.innerWidth : 600));
	let containerHeight = $derived(container ? container.clientHeight : (browser ? window.innerHeight : 600));

	// Calculate initial scale to fit image in container
	let initialScale = $derived.by(() => {
		console.log('🔍 [ZoomView] Initial scale derivation running:', {
			imageWidth,
			imageHeight,
			containerWidth,
			containerHeight,
			hasZoomViewData: !!$zoomViewData
		});

		if (!imageWidth || !imageHeight)
		{
			console.warn('🔍 [ZoomView] Initial scale calculation: missing image dimensions, defaulting to 1');
			return 1;
		}

		const scaleX = containerWidth / imageWidth;
		const scaleY = containerHeight / imageHeight;

		// Use the smaller scale to ensure image fits completely
		const r = Math.min(scaleX, scaleY);
		console.log('🔍 [ZoomView] *** Initial scale calculation RESULT ***:', {
			imageWidth,
			imageHeight,
			containerWidth,
			containerHeight,
			scaleX,
			scaleY,
			initialScale: r
		});
		return r;
	});

	let scale = $state(1);

	// Reset state when zoom view opens
	$effect(() => {
		if ($zoomViewData) {
			console.log('🔍 [ZoomView] Opening with data:', $zoomViewData);
			untrack(() => {
				imageWidth = $zoomViewData.width;
				imageHeight = $zoomViewData.height;
				translateX = 0;
				translateY = 0;
			});
		}
	});

	// Update scale when image dimensions are available and initialScale changes
	$effect(() => {
		if ($zoomViewData && imageWidth && imageHeight) {
			console.log('🔍 [ZoomView] Setting scale to initial scale:', initialScale);
			untrack(() => {
				scale = initialScale;
				// Center the image in the viewport
				const scaledWidth = (imageWidth || 800) * initialScale;
				const scaledHeight = (imageHeight || 600) * initialScale;
				translateX = (containerWidth - scaledWidth) / 2;
				translateY = (containerHeight - scaledHeight) / 2;
				console.log('🔍 [ZoomView] Centering image:', { translateX, translateY, scaledWidth, scaledHeight, containerWidth, containerHeight });
			});
		}
	});

	function closeZoomView() {
		zoomViewData.set(null);
	}

	function handleBackdropClick(event: MouseEvent) {
		const target = event.target as HTMLElement;
		console.log('🔍 [ZoomView] Backdrop click:', {
			target: target,
			targetClass: target.className,
			targetTag: target.tagName,
			container: container
		});

		// Don't close if clicking on the close button
		if (target.closest('.close-button')) {
			console.log('🔍 [ZoomView] Click on close button, ignoring');
			return;
		}

		// Don't close if clicking on the zoom image wrapper (for pan/zoom interaction)
		// fallback-image-wrapper has pointer-events: none, so clicks pass through
		if (target.closest('.zoom-image-wrapper')) {
			console.log('🔍 [ZoomView] Click on zoom image, ignoring');
			return;
		}

		// Don't close if clicking on the filename overlay (bottom info bar)
		if (target.closest('.filename-overlay')) {
			console.log('🔍 [ZoomView] Click on filename overlay, ignoring');
			return;
		}

		// Close on backdrop clicks
		console.log('🔍 [ZoomView] Closing zoom view from backdrop click');
		closeZoomView();
	}

	// Pan/zoom state handler
	function handlePanZoomUpdate(state: { scale: number; translateX: number; translateY: number }) {
		console.log('🔍 [ZoomView] Pan/zoom update received:', state);
		console.log('🔍 [ZoomView] Current state before update:', { scale, translateX, translateY });
		scale = state.scale;
		translateX = state.translateX;
		translateY = state.translateY;
		console.log('🔍 [ZoomView] Current state after update:', { scale, translateX, translateY });
	}


	// Calculate scaled image dimensions for direct width/height
	let scaledImageWidth = $derived((imageWidth || 800) * scale);
	let scaledImageHeight = $derived((imageHeight || 600) * scale);




	// Keyboard handling
	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			closeZoomView();
		}
	}

	onMount(() => {
		document.addEventListener('keydown', handleKeydown);
		return () => {
			document.removeEventListener('keydown', handleKeydown);
		};
	});
</script>

<div
		class="zoom-overlay"
		bind:this={container}
		onclick={handleBackdropClick}
		onkeydown={handleKeydown}
		use:panZoom={{
			onUpdate: handlePanZoomUpdate,
			initialScale: initialScale,
			minScale: 0.1,
			maxScale: 5,
			imageWidth,
			imageHeight,
			containerWidth,
			containerHeight
		}}
		role="dialog"
		aria-label="Photo zoom view"
		tabindex="-1"
		data-testid="zoom-view-overlay"
	>
		<button
			class="close-button"
			onclick={closeZoomView}
			aria-label="Close zoom view"
			data-testid="zoom-view-close"
		>
			<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
				<path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
			</svg>
		</button>

		<div class="image-container">
			<!-- Fallback image (already loaded thumbnail) -->
			<div
				class="fallback-image-wrapper"
				style="left: {translateX}px; top: {translateY}px; width: {scaledImageWidth}px; height: {scaledImageHeight}px; position: fixed;"
			>
				<img
					src={$zoomViewData!.fallback_url}
					alt={$zoomViewData!.filename}
					class="fallback-image"
					draggable="false"
					onload={() => console.log('🔍 [ZoomView] Fallback image loaded:', $zoomViewData!.fallback_url)}
					onerror={(e) => console.error('🔍 [ZoomView] Fallback image error:', $zoomViewData!.fallback_url, e)}
				/>
			</div>

			<!-- Full-size image (loads on top) -->
			<div
				class="zoom-image-wrapper"
				style="left: {translateX}px; top: {translateY}px; width: {scaledImageWidth}px; height: {scaledImageHeight}px; position: fixed;"
				role="button"
				tabindex="0"
				aria-label="Double-tap to zoom"
				data-testid="zoom-view-image"
			>
				<img
					src={$zoomViewData!.url}
					alt={$zoomViewData!.filename}
					class="zoom-image"
					draggable="false"
					onload={(e) => {
						console.log('🔍 [ZoomView] Full image loaded:', $zoomViewData!.url);
						const img = e.target as HTMLImageElement;
						// If we don't have dimensions, get them from the loaded image
						if (!imageWidth || !imageHeight) {
							console.log('🔍 [ZoomView] Getting dimensions from loaded image:', img.naturalWidth, 'x', img.naturalHeight);
							imageWidth = img.naturalWidth;
							imageHeight = img.naturalHeight;
						}
					}}
					onerror={(e) => console.error('🔍 [ZoomView] Full image error:', $zoomViewData!.url, e)}
				/>
			</div>
		</div>

		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="filename-overlay" onclick={(e) => e.stopPropagation()} ondblclick={(e) => e.stopPropagation()}>
			{$zoomViewData!.filename}
			{#if $app.debug}
			<br>
			<small>Provided: {$zoomViewData!.width}x{$zoomViewData!.height} | Current: {imageWidth}x{imageHeight} | Scale: {scale.toFixed(2)}</small>
			{/if}
		</div>
	</div>

<style>
	.zoom-overlay {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(0, 0, 0, 0.95);
		z-index: 999999;
		display: flex;
		align-items: center;
		justify-content: center;
		touch-action: none;
	}

	.close-button {
		position: absolute;
		top: calc(20px + var(--safe-area-inset-top, 0px));
		right: calc(20px + var(--safe-area-inset-right, 0px));
		background: rgba(255, 255, 255, 0.9);
		border: none;
		border-radius: 50%;
		width: 44px;
		height: calc(44px);
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		z-index: 1000001;
		color: #333;
		transition: background-color 0.2s ease;
	}

	.close-button:hover {
		background: rgba(255, 255, 255, 1);
	}

	.image-container {
		position: relative;
		width: 100vw;
		height: 100vh;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.fallback-image-wrapper {
		position: absolute;
		top: 0;
		left: 0;
		user-select: none;
		pointer-events: none;
	}

	.fallback-image {
		width: 100%;
		height: 100%;
		object-fit: contain;
		opacity: 0.7;
		user-select: none;
		pointer-events: none;
	}

	.zoom-image-wrapper {
		position: absolute;
		top: 0;
		left: 0;
		cursor: grab;
		user-select: none;
		pointer-events: auto;
	}

	.zoom-image {
		width: 100%;
		height: 100%;
		object-fit: contain;
		user-select: none;
		background: transparent;
		pointer-events: none;
	}

	.zoom-image-wrapper:active {
		cursor: grabbing;
	}

	/* Show full image once it's loaded */
	.zoom-image[src]:not([src=""]) {
		opacity: 1;
	}

	.filename-overlay {
		position: absolute;
		bottom: 20px;
		left: 50%;
		transform: translateX(-50%);
		background: rgba(0, 0, 0, 0.7);
		color: white;
		padding: 8px 16px;
		border-radius: 20px;
		font-size: 14px;
		max-width: 80vw;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	@media (max-width: 768px) {
		.close-button {
			top: calc(10px + var(--safe-area-inset-top, 0px));
			right: calc(20px + var(--safe-area-inset-right, 0px));
		}

		.filename-overlay {
			bottom: 10px;
			font-size: 12px;
			padding: 6px 12px;
		}
	}
</style>
