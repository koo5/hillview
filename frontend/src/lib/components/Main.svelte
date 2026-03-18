<script lang="ts">
	import {addPluginListener, invoke, type PluginListener} from '@tauri-apps/api/core';
	import {BROWSER, TAURI} from '$lib/tauri';
	import {onDestroy, onMount, tick} from 'svelte';
	import {browser} from '$app/environment';
	import {parsePhotoUid} from '$lib/urlUtils';
	import PhotoGallery from './Gallery.svelte';
	import Map from './Map.svelte';
	import {
		Camera,
		Menu,
		Bug,
		Maximize2,
		Minimize2
	} from 'lucide-svelte';
	import {
		app,
		sources,
		toggleDebug,
		turn_to_photo_to,
		enableSourceForPhotoUid,
		splitPercent,
		showCalibrationView, onAppActivityChange
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
	import {derived, get} from "svelte/store";
	import {zoomViewData, pendingZoomView, zoomViewportBounds} from '$lib/zoomView.svelte';
	import {getFullPhotoInfo} from '$lib/photoUtils';
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
	import {enableBearingTracking, disableBearingTracking} from '$lib/bearingTracking';
	import {networkWorkerManager} from "$lib/networkWorkerManager";
	import {enableLocationTracking} from "$lib/locationManager";
	import InsetGradients from "$lib/components/InsetGradients.svelte";

	let map: any = null;
	let mapComponent: any = null;
	let update_url: boolean = false;
	let menuOpen = false;
	let containerElement: HTMLElement;
	let isFullscreen = false;
	let screenAngleUnlisten: PluginListener | null = null;

	function toggleFullscreen() {
		if (!document.fullscreenElement) {
			document.documentElement.requestFullscreen().then(() => {
				isFullscreen = true;
			}).catch(err => {
				console.warn('Fullscreen request failed:', err);
			});
		} else {
			document.exitFullscreen().then(() => {
				isFullscreen = false;
			});
		}
	}

	async function handleNativeCapture() {
		console.log('🢄[NATIVE CAMERA] Starting native camera capture');
		try {
			const result: any = await invoke('take_native_photo');
			console.log('🢄[NATIVE CAMERA] Result:', JSON.stringify(result));
			if (result.success) {
				console.log('🢄[NATIVE CAMERA] Photo captured with id:', result.photo_id);
			} else {
				console.error('🢄[NATIVE CAMERA] Error:', result.error);
			}
		} catch (error) {
			console.error('🢄[NATIVE CAMERA] Invoke error:', error);
		}
	}

	// Listen for fullscreen changes (e.g., user presses Escape)
	if (browser) {
		document.addEventListener('fullscreenchange', () => {
			isFullscreen = !!document.fullscreenElement;
		});
	}

	$: showCameraView = $app.activity === 'capture';


	onMount(() => {

		updateOrientation();

		// fixme: needs deinit? // should we handle this with a separate ssr layout.svelte?
		networkWorkerManager.init();

		// Add keyboard event listener for debug toggle
		window.addEventListener('keydown', handleKeyDown);

		// Initialize and track orientation for split direction
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
			}).then(listener => {
				screenAngleUnlisten = listener;
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

		// Sync zoom viewport bounds to URL params
		const unsubscribeZoomBounds = zoomViewportBounds.subscribe(bounds => {
			if (!update_url) return;
			const url = new URL(window.location.href);
			if (bounds) {
				url.searchParams.set('x1', bounds.x1.toFixed(6));
				url.searchParams.set('y1', bounds.y1.toFixed(6));
				url.searchParams.set('x2', bounds.x2.toFixed(6));
				url.searchParams.set('y2', bounds.y2.toFixed(6));
			} else {
				url.searchParams.delete('x1');
				url.searchParams.delete('y1');
				url.searchParams.delete('x2');
				url.searchParams.delete('y2');
			}
			replaceState2(url.toString());
		});

		// Clear zoom URL params when zoom view closes
		const unsubscribeZoomClose = zoomViewData.subscribe(data => {
			if (!update_url) return;
			if (!data) {
				zoomViewportBounds.set(null);
			}
		});

		// Bridge: when pending zoom is set and photo arrives, open zoom view
		const unsubscribePendingZoom = derived(
			[pendingZoomView, photoInFront],
			([pending, photo]) => ({ pending, photo })
		).subscribe(({ pending, photo }) => {
			if (!pending || !photo) return;
			const fullPhotoInfo = getFullPhotoInfo(photo);
			zoomViewData.set({
				fallback_url: '',
				url: fullPhotoInfo.url,
				filename: photo.filename,
				width: fullPhotoInfo.width,
				height: fullPhotoInfo.height,
				photo_id: photo.id,
				pyramid: (photo as any).sizes?.full?.pyramid ?? undefined,
			});
		});

		const unsubscribeBearing = bearingState.subscribe(onBearingStateChange);
		const unsubscribeSpatial = spatialState.subscribe(onSpatialStateChange);

		return () => {
			unsubscribe1();
			unsubscribeZoomBounds();
			unsubscribeZoomClose();
			unsubscribePendingZoom();
			unsubscribeBearing();
			unsubscribeSpatial();
			if (bearingUrlUpdateTimeout) clearTimeout(bearingUrlUpdateTimeout);
			if (spatialUrlUpdateTimeout) clearTimeout(spatialUrlUpdateTimeout);
		};

	});

	onDestroy(() => {
		console.log('🢄Page destroyed');
		window.removeEventListener('keydown', handleKeyDown);
		window.removeEventListener('resize', updateOrientation);
		window.removeEventListener('orientationchange', updateOrientation);
		screen.orientation.removeEventListener("change", handleOrientationChange);
		if (screenAngleUnlisten) {
			screenAngleUnlisten.unregister();
			screenAngleUnlisten = null;
		}
	});


	function handleOrientationChange(e: Event) {
		console.log('🢄device-orientation: WEB screen orientation changed:', e);
		const target = e.target as any; // Screen orientation API types not fully supported
		screenOrientationAngle.set(target?.angle || 0);
	}


	let bearingUrlUpdateTimeout: ReturnType<typeof setTimeout> | null = null;
	let lastBearingState: any = undefined;

	function onBearingStateChange(visual: any) {
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
	}

	// Subscribed in onMount, cleaned up on destroy

	let desiredUrl: string | null = null;

	async function replaceState2(url: string) {
		//console.log('replaceState2: updating URL to', url);
		await tick();
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

	function onSpatialStateChange(p: any) {
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
	}

	// Subscribed in onMount, cleaned up on destroy

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
	const getIsPortrait = () => typeof window !== 'undefined' && window.innerHeight > window.innerWidth;
	let isPortrait = getIsPortrait();

	const updateOrientation = () => {
		const newIsPortrait = getIsPortrait();
		// console.log('🔄SPLIT: updateOrientation called', JSON.stringify({
		// 	oldIsPortrait: isPortrait,
		// 	newIsPortrait,
		// 	windowSize: {width: window.innerWidth, height: window.innerHeight}
		// }));
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
		onAppActivityChange(newActivity);
		if (get(spatialState).zoom < 17 && newActivity === 'capture') {
			updateSpatialState({
				...get(spatialState),
				zoom: 17
			});
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
			enableLocationTracking();
			enableBearingTracking();
		} else if ($app.activity === 'view') {
			disableBearingTracking();
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

<button
	class="camera-button {showCameraView ? 'active' : ''}"
	style="transform: rotate({getCssRotationFromOrientation($relativeOrientationExif)}deg);"
	on:click={toggleCamera}
	on:keydown={(e) => e.key === 'Enter' && toggleCamera()}
	aria-label="{showCameraView ? 'Close camera' : 'Take photo'}"
	title="{showCameraView ? 'Close camera' : 'Take photos'}"
	data-testid="camera-button"
>
	<Camera size={24} class="camera-button-icon" />
</button>

{#if BROWSER}
	<button
		on:click={toggleFullscreen}
		class="fullscreen-toggle"
		on:keydown={(e) => e.key === 'Enter' && toggleFullscreen()}
		aria-label="{isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}"
		title="{isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}"
	>
		{#if isFullscreen}
			<Minimize2 size={24}/>
		{:else}
			<Maximize2 size={24}/>
		{/if}
	</button>
{/if}

<NavigationMenu isOpen={menuOpen} onClose={() => menuOpen = false}/>

<!-- Alert area for main page -->
<div class="main-page-alert-area">
	<AlertArea position="main"/>
</div>

{#if true}

{@const s = getComputedStyle(document.documentElement)}
<!--  + Math.max(s.getPropertyValue('--safe-area-inset-top').replace('px','')*1.0, s.getPropertyValue('--safe-area-inset-left').replace('px','')*1.0, 0), -->

<div
	class="container"
	bind:this={containerElement}
	use:resizableSplit={{
		direction: isPortrait ? 'horizontal' : 'vertical',
		defaultSplit: $splitPercent,
		minSize: 100,
		onResize: handleSplitResize
	}}
>
	<div class="panel photo-panel" style="
		position: absolute;
		top: 0;
		left: 0;
		{isPortrait ? `height: ${$splitPercent}%; width: 100%;` : `width: ${$splitPercent}%; height: 100%;`}
	">

		{#if $app.debug_enabled}
			<button
				on:click={toggleDebug}
				class="debug-toggle"
				on:keydown={(e) => e.key === 'Enter' && toggleDebug()}
				aria-label="Toggle debug overlay"
				title="Toggle debug overlay"
			>
				<Bug size={24}/>
			</button>
		{/if}

		{#if TAURI && $app.debug}
			<button
				on:click={handleNativeCapture}
				class="native-camera-toggle"
				aria-label="Native camera capture"
				title="Native camera capture (tauri-plugin-camera)"
				data-testid="native-camera-btn"
			>
				📸
			</button>
		{/if}

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
	<div class="panel map-panel" style="
		position: absolute;
		{isPortrait ? `bottom: 0; left: 0; height: ${100 - $splitPercent}%; width: 100%;` : `right: 0; top: 0; width: ${100 - $splitPercent}%; height: 100%;`}
	">
		<Map bind:this={mapComponent} bind:update_url={update_url}/>
	</div>
</div>
{/if}

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
		top: calc(0px + var(--safe-area-inset-top, 10px));
		left: calc(0px + var(--safe-area-inset-left, 10px));
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
		top: calc(0px + var(--safe-area-inset-top, 10px));
		left: calc(50px + var(--safe-area-inset-left, 10px));
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

	.fullscreen-toggle {
		position: absolute;
		top: calc(0px + var(--safe-area-inset-top, 10px));
		left: calc(100px + var(--safe-area-inset-left, 10px));
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

	.debug-toggle {
		position: absolute;
		top: calc(0px + var(--safe-area-inset-top, 10px));
		right: calc(0px + var(--safe-area-inset-right, 15px));
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

	.native-camera-toggle {
		position: absolute;
		top: calc(0px + var(--safe-area-inset-top, 0px));
		right: calc(50px + var(--safe-area-inset-right, 0px));
		z-index: 30001;
		background: orange;
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
		font-size: 20px;
		transition: all 0.2s ease;
	}

	.native-camera-toggle:active {
		transform: scale(0.95);
		background: darkorange;
	}

	.camera-button.active {
		background: #4a90e2;
		color: white;
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
