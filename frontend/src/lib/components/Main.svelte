<script lang="ts">
	import {addPluginListener, type PluginListener} from '@tauri-apps/api/core';
	import {TAURI} from '$lib/tauri';
	import {onDestroy, onMount, tick} from 'svelte';
	import {browser} from '$app/environment';
	import {parsePhotoUid} from '$lib/urlUtils';
	import PhotoGallery from './Gallery.svelte';
	import Map from './Map.svelte';
	import {
		Camera,
		Menu
	} from 'lucide-svelte';
	import {
		app,
		sources,
		toggleDebug,
		turn_to_photo_to,
		enableSourceForPhotoUid,
		splitPercent,
		showCalibrationView
	} from "$lib/data.svelte.js";
	import {resizableSplit} from '$lib/actions/resizableSplit';
	import {
		bearingState,
		spatialState,
		updateSpatialState,
		updateBearing,
		updateBearingByDiff,
		photoInFront
	} from "$lib/mapState";
	import {LatLng} from 'leaflet';
	import {replaceState} from "$app/navigation";
	import {get} from "svelte/store";
	import CameraCapture from './CameraCapture.svelte';
	import DebugOverlay from './DebugOverlay.svelte';
	import CompassCalibration from './CompassCalibration.svelte';
	import {
		deviceOrientationExif, getCssRotationFromOrientation,
		getRotationFromOrientation, getWebviewOrientation, relativeOrientationExif,
		screenOrientationAngle
	} from "$lib/deviceOrientationExif";
	import AlertArea from './AlertArea.svelte';
	import NavigationMenu from './NavigationMenu.svelte';
	import type {DevicePhotoMetadata} from '$lib/types/photoTypes';
	import {enableCompass, disableCompass} from '$lib/compass.svelte.js';
	import {networkWorkerManager} from "$lib/networkWorkerManager";
	import type {SensorData} from "$lib/tauri";

	let map: any = null;
	let mapComponent: any = null;
	let update_url: boolean = false;
	let menuOpen = false;
	let containerElement: HTMLElement;

	$: showCameraView = $app.activity === 'capture';


	onMount(() => {

		// fixme: needs deinit? // should we handle this with a separate ssr layout.svelte?
		networkWorkerManager.init();


		init();

		// Add keyboard event listener for debug toggle
		window.addEventListener('keydown', handleKeyDown);

		// Initialize and track orientation for split direction
		updateOrientation();
		window.addEventListener('resize', updateOrientation);
		window.addEventListener('orientationchange', updateOrientation);

		// Firefox fallback for dvh support
		if (!CSS.supports('height', '100dvh')) {
			console.log('🢄Browser lacks dvh support, using innerHeight fallback');
			const updateContainerHeight = () => {
				if (containerElement) {
					containerElement.style.height = `${window.innerHeight}px`;
				}
			};
			updateContainerHeight();
			window.addEventListener('resize', updateContainerHeight);
			window.addEventListener('orientationchange', updateContainerHeight);
		}

		screenOrientationAngle.set(getWebviewOrientation());
		if (TAURI) {
			addPluginListener('hillview', 'screen-angle', (data: any) => {
				console.log('🢄device-orientation: Tauri screen angle changed:', data.angle);
				screenOrientationAngle.set(data.angle);
			});

		} else {
			screen.orientation.addEventListener("change", handleOrientationChange);
		}

		const unsubscribe1 = photoInFront.subscribe(photo => {
			if (!update_url) return;

			const url = new URL(window.location.href);

			if (photo?.uid) {
				url.searchParams.set('photo', encodeURIComponent(photo.uid));
			} else {
				url.searchParams.delete('photo');
			}

			replaceState2(url.toString());
		});

		return () => {
			unsubscribe1();
		};

	});

	async function init() {

	}

	onDestroy(() => {
		console.log('🢄Page destroyed');
		window.removeEventListener('keydown', handleKeyDown);
		window.removeEventListener('resize', updateOrientation);
		window.removeEventListener('orientationchange', updateOrientation);
		screen.orientation.removeEventListener("change", handleOrientationChange);
	});


	function handleOrientationChange(e: Event) {
		console.log('🢄device-orientation: WEB screen orientation changed:', e);
		const target = e.target as any; // Screen orientation API types not fully supported
		screenOrientationAngle.set(target?.angle || 0);
	}


	let bearingUrlUpdateTimeout: ReturnType<typeof setTimeout> | null = null;
	let lastBearingState: any = undefined;

	bearingState.subscribe(visual => {

		if (!update_url) {
			return;
		}

		lastBearingState = visual;

		if (bearingUrlUpdateTimeout) {
			return;
		}

		bearingUrlUpdateTimeout = setTimeout(() => {
			bearingUrlUpdateTimeout = null;
			if (lastBearingState === undefined || lastBearingState === null || lastBearingState.bearing === undefined) {
				return;
			}
			const url = new URL(window.location.href);
			url.searchParams.set('bearing', String(lastBearingState.bearing));

			/*
			if (lastBearingState?.photoUid) {
				url.searchParams.set('photo', encodeURIComponent(lastBearingState.photoUid));
			} else {
				url.searchParams.delete('photo');
			}
			*/

			replaceState2(url.toString());
		}, 2000);

	});

	let desiredUrl: string | null = null;

	function replaceState2(url: string) {
		console.log('replaceState2: updating URL to', url);
		desiredUrl = url;
		try {
			replaceState(url, {});
		} catch (e) {
			console.error('🢄Failed to update URL', e);
			setTimeout(() => {
				if (desiredUrl) replaceState(desiredUrl, {});
			}, 1000);
		}
	}

	let spatialUrlUpdateTimeout: ReturnType<typeof setTimeout> | null = null;

	spatialState.subscribe(p => {
		if (!update_url) {
			return;
		}

		if (spatialUrlUpdateTimeout) {
			clearTimeout(spatialUrlUpdateTimeout);
		}
		spatialUrlUpdateTimeout = setTimeout(() => {
			spatialUrlUpdateTimeout = null;
			const url = new URL(window.location.href);
			url.searchParams.set('lat', String(p.center.lat));
			url.searchParams.set('lon', String(p.center.lng));
			url.searchParams.set('zoom', String(p.zoom));
			replaceState2(url.toString());
		}, 500);
	});

	const toggleMenu = () => {
		menuOpen = !menuOpen;
	}

	// Handle split resize
	const handleSplitResize = (newSplitPercent: number) => {
		splitPercent.set(newSplitPercent);
		// Trigger a window resize event to make the map recalculate
		setTimeout(() => {
			window.dispatchEvent(new Event('resize'));
		}, 10);
	}

	// Detect orientation for split direction
	let isPortrait = false;

	const updateOrientation = () => {
		const newIsPortrait = window.innerHeight > window.innerWidth;
		console.log('🔄SPLIT: updateOrientation called', JSON.stringify({
			oldIsPortrait: isPortrait,
			newIsPortrait,
			windowSize: {width: window.innerWidth, height: window.innerHeight}
		}));
		if (newIsPortrait !== isPortrait) {
			isPortrait = newIsPortrait;
		}
	};

	function handleKeyDown(e: KeyboardEvent) {
		// Only handle debug toggle when no modifier keys are pressed
		// and when not typing in an input/textarea/contenteditable element
		if (e.ctrlKey || e.altKey || e.metaKey) {
			return;
		}

		// Check if we're currently typing in an input field
		const activeElement = document.activeElement as HTMLElement;
		const isTyping = activeElement && (
			activeElement.tagName === 'INPUT' ||
			activeElement.tagName === 'TEXTAREA' ||
			activeElement.contentEditable === 'true' ||
			activeElement.getAttribute('contenteditable') === 'true'
		);

		if (isTyping) {
			return;
		}

		const shift = e.shiftKey;

		// Handle debug toggle
		if (e.key === 'd') {
			e.preventDefault();
			toggleDebug();
		}
		// Handle source toggle - if any enabled, disable all; if none enabled, enable all
		else if (e.key === 's') {
			e.preventDefault();
			toggleAllSources();
		}

		// Handle navigation shortcuts
		else if (e.key === 'z') {
			e.preventDefault();
			turn_to_photo_to('left');
		} else if (e.key === 'x') {
			e.preventDefault();
			updateBearingByDiff(-15);
		} else if (e.key === 'X') {
			e.preventDefault();
			updateBearingByDiff(-1);
		} else if (e.key === 'c') {
			e.preventDefault();
			mapComponent?.moveForward?.();
		} else if (e.key === 'v') {
			e.preventDefault();
			mapComponent?.moveBackward?.();
		} else if (e.key === 'B') {
			e.preventDefault();
			updateBearingByDiff(1);
		} else if (e.key === 'b') {
			e.preventDefault();
			updateBearingByDiff(15);
		} else if (e.key === 'k') {
			e.preventDefault();
			turn_to_photo_to('right');
		} else if (e.key === 'm') {
			e.preventDefault();
			toggleSource('mapillary');
		}
	}


	function createPlaceholderPhoto(captureLoc: any, id: string, timestamp: number): DevicePhotoMetadata {
		return {
			id,
			filename: 'processing.jpg',
			path: 'placeholder://processing', // Use special placeholder URL instead of empty string
			latitude: captureLoc.latitude,
			longitude: captureLoc.longitude,
			altitude: captureLoc.altitude,
			bearing: captureLoc.heading,
			captured_at: timestamp,
			accuracy: captureLoc.accuracy || 1,
			width: 0,
			height: 0,
			file_size: 0,
			created_at: timestamp
		};
	}

	function createPhotoData(captureLoc: any, timestamp: number, file: File) {
		return {
			image: file,
			location: {
				latitude: captureLoc.latitude,
				longitude: captureLoc.longitude,
				altitude: captureLoc.altitude,
				accuracy: captureLoc.accuracy || 1
			},
			bearing: captureLoc.heading,
			timestamp: timestamp
		};
	}

	const toggleAllSources = () => {
		const currentSources = get(sources);
		const anyEnabled = currentSources.some(src => src.enabled);

		if (anyEnabled) {
			// If any sources are enabled, disable all
			sources.update(srcs => {
				return srcs.map(src => ({
					...src,
					enabled: false
				}));
			});
		} else {
			// If no sources are enabled, enable all
			sources.update(srcs => {
				return srcs.map(src => ({
					...src,
					enabled: true
				}));
			});
		}
	}

	function toggleSource(id: string) {
		sources.update(srcs => {
			return srcs.map(src => ({
				...src,
				enabled: src.id === id ? !src.enabled : src.enabled
			}));
		});
	}

	function toggleCamera() {
		const newActivity = get(app).activity === 'capture' ? 'view' : 'capture';

		if (newActivity === 'capture') {

			// Entering capture mode - disable all photo sources
			sources.update(srcs => {
				return srcs.map(src => ({
					...src,
					enabled: src.id === 'device' // Only enable device source
				}));
			});
			// Note: Location and compass are now handled by reactive statement
		} else {

			// Exiting capture mode - re-enable previously enabled sources
			// For now, we'll re-enable hillview and device sources by default
			sources.update(srcs => {
				return srcs.map(src => ({
					...src,
					enabled: src.id === 'hillview' || src.id === 'device'
				}));
			});
			// Note: Compass stopping is now handled by reactive statement
		}

		app.update(a => ({
			...a,
			activity: newActivity
		}));


	}


	// Reactive statement to ensure geolocation and bearing are enabled when in capture mode
	// This handles both toggle events and initial page load
	let appOldActivity = '';
	$: if (appOldActivity != $app.activity) {
		if ($app.activity === 'capture') {
			//console.log('🢄🎥 Capture mode detected, ensuring location and compass are enabled');

			// Enable location tracking when in capture mode
			if (mapComponent) {
				mapComponent.enableLocationTracking();
			}

			// Enable compass/bearing when in capture mode
			enableCompass();
		} else if ($app.activity === 'view') {
			//console.log('🢄👁️ View mode detected, stopping compass');
			// Stop compass when exiting capture mode (optional - can be removed if you want compass to stay active)
			disableCompass();
		}
		appOldActivity = $app.activity;
	}
</script>


<!-- Hamburger icon -->
<button
	class="hamburger"
	data-testid="hamburger-menu"
	on:click={toggleMenu}
	on:keydown={(e) => e.key === 'Enter' && toggleMenu()}
	aria-label="Toggle menu"
	aria-expanded={menuOpen}
>
	<Menu size={24}/>
</button>


{#if TAURI || $app.debug_enabled}
	<button
		class="camera-button {showCameraView ? 'active' : ''}"
		style="transform: rotate({getCssRotationFromOrientation($relativeOrientationExif)}deg);"
		on:click={toggleCamera}
		on:keydown={(e) => e.key === 'Enter' && toggleCamera()}
		aria-label="{showCameraView ? 'Close camera' : 'Take photo'}"
		title="{showCameraView ? 'Close camera' : 'Take photos'}"
		data-testid="camera-button"
	>
		<Camera size={24}/>
	</button>
{/if}

<!--{#if import.meta.env.VITE_DEV_MODE === 'true'}-->
{#if $app.debug_enabled}
	<button
		on:click={toggleDebug}
		class="debug-toggle"
		on:keydown={(e) => e.key === 'Enter' && toggleDebug()}
		aria-label="Toggle debug overlay"
		title="Toggle debug overlay"
	>
		{getCssRotationFromOrientation($relativeOrientationExif)}
	</button>
{/if}

<NavigationMenu isOpen={menuOpen} onClose={() => menuOpen = false}/>

<!-- Alert area for main page -->
<div class="main-page-alert-area">
	<AlertArea position="main"/>
</div>

<div
	class="container"
	bind:this={containerElement}
	use:resizableSplit={{
		direction: isPortrait ? 'horizontal' : 'vertical',
		defaultSplit: $splitPercent,
		minSize: 50,
		onResize: handleSplitResize
	}}
>
	<div class="panel photo-panel">
		{#if $showCalibrationView}
			<CompassCalibration />
		{:else if showCameraView}
			<CameraCapture
				show={true}
				on:close={() => app.update(a => ({...a, activity: 'view'}))}
			/>
		{:else}
			<PhotoGallery/>
		{/if}
	</div>
	<div class="panel map-panel">
		<Map bind:this={mapComponent} bind:update_url={update_url}/>
	</div>
</div>


<DebugOverlay/>

<style>
	/* Reset default margin, padding and prevent body scroll for main app */
	:global(html, body) {
		margin: 0;
		padding: 0;
		overflow: hidden;
		width: 100%;
		height: 100%;
		touch-action: manipulation;
	}

	/* Allow specific pages to enable scrolling */
	:global(body:has(.page-scrollable), html:has(.page-scrollable)) {
		overflow: auto !important;
		height: auto !important;
	}

	/* Fallback for browsers that don't support :has() */
	:global(body.scrollable, html.scrollable) {
		overflow: auto !important;
		height: auto !important;
	}

	/* Ensure padding and borders are included in the elements' total size */
	:global(*) {
		box-sizing: border-box;
	}

	/* Container with draggable split */
	.container {
		width: 100vw;
		height: 100vh;
		/* Use dynamic viewport height for mobile browsers */
		height: 100dvh;
	}

	.panel {
		overflow: auto;
	}

	.hamburger {
		position: absolute;
		top: 10px;
		left: 10px;
		z-index: 30001;
		background: white;
		border-radius: 50%;
		width: 40px;
		height: 40px;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
		cursor: pointer;
		border: none;
		padding: 0;
	}


	.camera-button {
		position: absolute;
		top: 10px;
		left: 60px;
		z-index: 30001;
		background: white;
		border-radius: 50%;
		width: 40px;
		height: 40px;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
		cursor: pointer;
		border: none;
		padding: 0;
		user-select: none;
		-webkit-user-select: none;
		-webkit-touch-callout: none;
		transition: all 0.2s ease, transform 0.3s ease;
	}

	.debug-toggle {
		position: absolute;
		top: 10px;
		left: 110px;
		z-index: 30001;
		background: white;
		border-radius: 50%;
		width: 40px;
		height: 40px;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
		cursor: pointer;
		border: none;
		padding: 0;
		transition: all 0.2s ease;
	}

	.camera-button.active {
		background: #4a90e2;
		color: white;
		box-shadow: 0 2px 8px rgba(74, 144, 226, 0.4);
	}

	/* Red animated style when not active (view mode) */
	.camera-button:not(.active) {
		background: white;
		color: black;
		animation: pulse 2s infinite;
	}

	@keyframes pulse {
		0% {
			box-shadow: 0 2px 5px rgba(100, 0, 100, 0.2);
		}
		50% {
			box-shadow: 0 2px 12px rgba(131, 255, 60, 0.6);
			transform: scale(1.10);
		}
		100% {
			box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
		}
	}

	.camera-button:hover {
		transform: scale(1.05);
	}


	.main-page-alert-area {
		position: absolute;
		top: 60px; /* Below the top buttons */
		left: 10px;
		right: 100px;
		z-index: 30000;
		pointer-events: none; /* Let clicks through unless there's an alert */
		background: rgba(255, 255, 255, 0.2);
	}

	.main-page-alert-area :global(.alert-area) {
		pointer-events: auto; /* Re-enable clicks on actual alerts */
	}

	:global(#sentry-feedback) {
		--trigger-background: rgba(74, 144, 226, 0.6);
		--inset: auto auto 0 0;
	}

</style>
