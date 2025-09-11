<script lang="ts">
	import {onDestroy, onMount, tick} from 'svelte';
	import PhotoGallery from '../components/Gallery.svelte';
	import Map from '../components/Map.svelte';
	import {
		Camera,
		Maximize2,
		Menu,
		Minimize2
	} from 'lucide-svelte';
	import {app, sources, toggleDebug} from "$lib/data.svelte";
	import {
		bearingState,
		spatialState,
		updateSpatialState,
		updateBearing as mapStateUpdateBearing
	} from "$lib/mapState";
	import {LatLng} from 'leaflet';
	import {replaceState} from "$app/navigation";
	import {get} from "svelte/store";
	import {auth, checkAuth, logout} from "$lib/auth.svelte";
	import CameraCapture from '../components/CameraCapture.svelte';
	import DebugOverlay from '../components/DebugOverlay.svelte';
	import AlertArea from '../components/AlertArea.svelte';
	import NavigationMenu from '../components/NavigationMenu.svelte';
	import {FEATURE_USER_ACCOUNTS} from '$lib/config';
	import {gpsLocation} from '$lib/location.svelte';
	import type {DevicePhotoMetadata} from '$lib/types/photoTypes';
	import {startCompass, stopCompass} from '$lib/compass.svelte';
	import '$lib/debugTauri';
	import {bearingDiffColorsUpdateInterval} from "$lib/optimizedMarkers";

	let map: any = null;
	let mapComponent: any = null;
	let update_url = false;
	let menuOpen = false;
	$: showCameraView = $app.activity === 'capture';
	let debugOverlay: any = null;

	onMount(async () => {
		console.log('🢄Page mounted');
		await tick();

		// Check authentication status
		checkAuth();

		const urlParams = new URLSearchParams(window.location.search);
		const lat = urlParams.get('lat');
		const lon = urlParams.get('lon');
		const zoom = urlParams.get('zoom');
		const bearingParam = urlParams.get('bearing');

		let p = get(spatialState);
		let update = false;

		if (lat && lon) {
			console.log('🢄Setting position to', lat, lon, 'from URL');
			p.center = new LatLng(parseFloat(lat), parseFloat(lon));
			update = true;
		}

		if (zoom) {
			console.log('🢄Setting zoom to', zoom, 'from URL');
			p.zoom = parseFloat(zoom);
			update = true;
		}

		if (update) {
			updateSpatialState({...p});
			map?.setView(p.center, p.zoom);
		}

		if (bearingParam) {
			console.log('🢄Setting bearing to', bearingParam, 'from URL');
			mapStateUpdateBearing(parseFloat(bearingParam));
		}

		setTimeout(() => {
			update_url = true;
		}, 100);

		// Add keyboard event listener for debug toggle
		window.addEventListener('keydown', handleKeyDown);

	});

	onDestroy(() => {
		console.log('🢄Page destroyed');
		window.removeEventListener('keydown', handleKeyDown);
	});


	let bearingUrlUpdateTimeout: ReturnType<typeof setTimeout> | null = null;
	let lastVal: number | undefined = undefined;

	bearingState.subscribe(visual => {

		if (!update_url) {
			return;
		}

		lastVal = visual.bearing;

		if (bearingUrlUpdateTimeout) {
			return;
		}

		bearingUrlUpdateTimeout = setTimeout(() => {
			bearingUrlUpdateTimeout = null;
			if (lastVal === undefined || lastVal === null) {
				return;
			}
			const url = new URL(window.location.href);
			url.searchParams.set('bearing', String(lastVal));
			replaceState2(url.toString());
		}, 2000);

	});

	let desiredUrl: string | null = null;

	function replaceState2(url: string) {
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

	const toggleDisplayMode = async () => {
		app.update(a => ({
			...a,
			displayMode: a.displayMode === 'split' ? 'max' : 'split'
		}));

		// Wait for DOM to update
		await tick();

		// Trigger a window resize event to make the map recalculate
		setTimeout(() => {
			window.dispatchEvent(new Event('resize'));
		}, 100);
	}

	function handleKeyDown(e: KeyboardEvent) {
		// Only handle debug toggle when no modifier keys are pressed
		// and when not typing in an input/textarea/contenteditable element
		if (e.ctrlKey || e.altKey || e.metaKey || e.shiftKey) {
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

		// Handle debug toggle
		if (e.key === 'd') {
			e.preventDefault();
			toggleDebug();
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
			timestamp,
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


	function toggleCamera() {
		const newActivity = get(app).activity === 'capture' ? 'view' : 'capture';

		app.update(a => ({
			...a,
			activity: newActivity
		}));

		if (newActivity === 'capture') {

			// Entering capture mode - disable all photo sources
			sources.update(srcs => {
				return srcs.map(src => ({
					...src,
					enabled: false
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
	}


	// Reactive statement to ensure geolocation and bearing are enabled when in capture mode
	// This handles both toggle events and initial page load
	$: if ($app.activity === 'capture') {
		//console.log('🢄🎥 Capture mode detected, ensuring location and compass are enabled');

		// Enable location tracking when in capture mode
		if (mapComponent) {
			mapComponent.enableLocationTracking();
		}

		// Enable compass/bearing when in capture mode
		startCompass().catch(err => {
			console.warn('🢄Failed to start compass for camera capture:', err);
		});
	} else if ($app.activity === 'view') {
		//console.log('🢄👁️ View mode detected, stopping compass');
		// Stop compass when exiting capture mode (optional - can be removed if you want compass to stay active)
		stopCompass().catch(err => console.error('Error stopping compass:', err));
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

<!-- Display mode toggle -->
<button
        class="display-mode-toggle"
        on:click={toggleDisplayMode}
        on:keydown={(e) => e.key === 'Enter' && toggleDisplayMode()}
        aria-label="Toggle display mode"
        title={$app.displayMode === 'split' ? 'Maximize view' : 'Split view'}
>
    {#if $app.displayMode === 'split'}
        <Maximize2 size={24}/>
    {:else}
        <Minimize2 size={24}/>
    {/if}
</button>

<!-- Camera button -->
<button
        class="camera-button {showCameraView ? 'active' : ''}"
        on:click={toggleCamera}
        on:keydown={(e) => e.key === 'Enter' && toggleCamera()}
        aria-label="{showCameraView ? 'Close camera' : 'Take photo'}"
        title="{showCameraView ? 'Close camera' : 'Take photos'}"
        data-testid="camera-button"
>
    <Camera size={24}/>
</button>

<button
        on:click={toggleDebug}
        class="debug-toggle"
        on:keydown={(e) => e.key === 'Enter' && toggleDebug()}
        aria-label="Toggle debug overlay"
        title="Toggle debug overlay"
>
    Debug
</button>

<NavigationMenu isOpen={menuOpen} onClose={() => menuOpen = false} />

<!-- Alert area for main page -->
<div class="main-page-alert-area">
    <AlertArea position="main" />
</div>

<div class="container" class:max-mode={$app.displayMode === 'max'}>
    <div class="panel photo-panel">
        {#if showCameraView}
            <CameraCapture
                    show={true}
                    on:close={() => app.update(a => ({...a, activity: 'view'}))}
            />
        {:else}
            <PhotoGallery/>
        {/if}
    </div>
    <div class="panel map-panel">
        <Map bind:this={mapComponent}/>
    </div>
</div>


<!-- Debug Overlay -->
<DebugOverlay bind:this={debugOverlay}/>

<style>
    /* Reset default margin, padding and prevent body scroll for main app */
    :global(html, body) {
        margin: 0;
        padding: 0;
        overflow: hidden;
        width: 100%;
        height: 100%;
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

    /* Container occupies the full viewport */
    .container {
        display: flex;
        width: 100vw;
        height: 100vh;
        flex-direction: row; /* Default landscape mode */
    }

    /* Each panel takes up equal space */
    .panel {
        flex: 1;
        overflow: auto;
    }

    /* Max mode: photo panel takes up 7/8 of the screen */
    .container.max-mode {
        flex-direction: row;
    }

    .container.max-mode .photo-panel {
        flex: 7;
    }

    .container.max-mode .map-panel {
        flex: 1;
    }

    /* For portrait mode, stack panels vertically */
    @media (orientation: portrait) {
        .container {
            flex-direction: column;
        }

        /* In portrait max mode, photo panel takes up 3/4 of height */
        .container.max-mode {
            flex-direction: column;
        }
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

    .display-mode-toggle {
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
    }

    .camera-button {
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
        touch-action: none;
        user-select: none;
        -webkit-user-select: none;
        -webkit-touch-callout: none;
        transition: all 0.2s ease;
    }

    .debug-toggle {
        position: absolute;
        top: 10px;
        left: 160px;
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

    .camera-button:hover {
        transform: scale(1.05);
    }


    .main-page-alert-area {
        position: absolute;
        top: 60px; /* Below the top buttons */
        left: 10px;
        right: 10px;
        z-index: 30000;
        pointer-events: none; /* Let clicks through unless there's an alert */
    }

    .main-page-alert-area :global(.alert-area) {
        pointer-events: auto; /* Re-enable clicks on actual alerts */
    }

    :global(#sentry-feedback) {
        --trigger-background: rgba(74, 144, 226, 0.6);
        --inset: auto auto 0 0;
    }

</style>
