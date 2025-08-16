<script lang="ts">
    import {onDestroy, onMount, tick} from 'svelte';
    import PhotoGallery from '../components/Gallery.svelte';
    import Map from '../components/Map.svelte';
    import {Camera, Compass, User, LogOut, Menu, Download, Maximize2, Minimize2} from 'lucide-svelte';
    import {sources, toggleDebug} from "$lib/data.svelte";
    import {dms} from "$lib/utils";
    import {app, turn_to_photo_to, update_bearing} from "$lib/data.svelte";
    import {spatialState, visualState, updateSpatialState} from "$lib/mapState";
    import {LatLng} from 'leaflet';
    import { goto, replaceState } from "$app/navigation";
    import {get, writable} from "svelte/store";
    import { auth, logout, checkAuth } from "$lib/auth.svelte";
    import CameraCapture from '../components/CameraCapture.svelte';
    import DebugOverlay from '../components/DebugOverlay.svelte';
    import { FEATURE_USER_ACCOUNTS } from '$lib/config';
    import { gpsLocation } from '$lib/location.svelte';
    import { photoCaptureService } from '$lib/photoCapture';
    import type { DevicePhotoMetadata } from '$lib/types/photoTypes';
    import { devicePhotos } from '$lib/stores';
    import { captureLocation, captureLocationWithCompassBearing } from '$lib/captureLocation';
    import { compassActive, stopCompass, startCompass } from '$lib/compass.svelte';
    import '$lib/captureLocationManager'; // Activate capture location management
    import '$lib/mapBearingSync'; // Sync map bearing with sensors
    import '$lib/debugTauri';

    let map: any = null;
    let mapComponent: any = null;
    let update_url = false;
    let menuOpen = false;
    $: showCameraView = $app.activity === 'capture';
    let debugOverlay: any = null;

    onMount(async () => {
        console.log('Page mounted');
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
            console.log('Setting position to', lat, lon, 'from URL');
            p.center = new LatLng(parseFloat(lat), parseFloat(lon));
            update = true;
        }

        if (zoom) {
            console.log('Setting zoom to', zoom, 'from URL');
            p.zoom = parseFloat(zoom);
            update = true;
        }

        if (update) {
            updateSpatialState({...p});
            map?.setView(p.center, p.zoom);
        }

        if (bearingParam) {
            console.log('Setting bearing to', bearingParam, 'from URL');
            update_bearing(parseFloat(bearingParam));
        }

        setTimeout(() => {
            update_url = true;
        }, 100);

        // Add keyboard event listener for debug toggle
        window.addEventListener('keydown', handleKeyDown);

    });

    onDestroy(() => {
        console.log('Page destroyed');
        window.removeEventListener('keydown', handleKeyDown);
    });

    spatialState.subscribe(p => {
        if (!update_url) {
            return;
        }
        const url = new URL(window.location.href);
        url.searchParams.set('lat', String(p.center.lat));
        url.searchParams.set('lon', String(p.center.lng));
        url.searchParams.set('zoom', String(p.zoom));
        //console.log('Setting URL to', url.toString());
        replaceState2(url.toString());
    });

    visualState.subscribe(visual => {
        const b = visual.bearing;
        if (!update_url) {
            return;
        }
        const url = new URL(window.location.href);
        url.searchParams.set('bearing', String(b));
        //console.log('Setting URL to', url.toString());
        setTimeout(() => {
            replaceState2(url.toString());
        }, 1000);
    });

    let desiredUrl: string | null = null;

    function replaceState2(url: string) {
        desiredUrl = url;
        try {
            replaceState(url, {});
        } catch (e) {
            console.error('Failed to update URL', e);
            setTimeout(() => {
                if (desiredUrl) replaceState(desiredUrl, {});
            }, 1000);
        }
    }

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
    
    function handleLogout() {
        logout();
        menuOpen = false;
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

    function updateDevicePhotos(callback: (photos: DevicePhotoMetadata[]) => DevicePhotoMetadata[]) {
        devicePhotos.update(callback);
    }

    let currentPlaceholderId: string | null = null;

    function addPlaceholder() {
        const captureLoc = $captureLocationWithCompassBearing;
        if (!captureLoc) {
            console.log('🔍❌ addPlaceholder: No capture location available');
            return;
        }

        currentPlaceholderId = `temp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const timestamp = Date.now();
        const placeholderPhoto = createPlaceholderPhoto(captureLoc, currentPlaceholderId, timestamp);

        console.log('🔍📍 Adding placeholder photo:', placeholderPhoto.id, 'at location:', captureLoc);
        updateDevicePhotos(photos => {
            const updated = [...photos, placeholderPhoto];
            console.log('🔍📊 Device photos updated with placeholder, total count:', updated.length);
            return updated;
        });
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
    
    // Use the reactive GPS location store
    $: currentLocation = $gpsLocation;

    // Subscribe to auth store
    let isAuthenticated = false;
    auth.subscribe(value => {
        isAuthenticated = value.isAuthenticated;
    });

    // Reactive statement to ensure geolocation and bearing are enabled when in capture mode
    // This handles both toggle events and initial page load
    $: if ($app.activity === 'capture') {
        console.log('🎥 Capture mode detected, ensuring location and compass are enabled');
        
        // Enable location tracking when in capture mode
        if (mapComponent) {
            mapComponent.enableLocationTracking();
        }
        
        // Enable compass/bearing when in capture mode
        startCompass().catch(err => {
            console.warn('Failed to start compass for camera capture:', err);
        });
    } else if ($app.activity === 'view') {
        console.log('👁️ View mode detected, stopping compass');
        
        // Stop compass when exiting capture mode (optional - can be removed if you want compass to stay active)
        stopCompass();
    }
</script>


<!-- Hamburger icon -->
<button 
    class="hamburger" 
    on:click={toggleMenu}
    on:keydown={(e) => e.key === 'Enter' && toggleMenu()}
    aria-label="Toggle menu"
    aria-expanded={menuOpen}
>
    <Menu size={24} />
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
        <Maximize2 size={24} />
    {:else}
        <Minimize2 size={24} />
    {/if}
</button>

<!-- Camera button -->
<button 
    class="camera-button {showCameraView ? 'active' : ''}" 
    on:click={toggleCamera}
    on:keydown={(e) => e.key === 'Enter' && toggleCamera()}
    aria-label="{showCameraView ? 'Close camera' : 'Take photo'}"
    title="{showCameraView ? 'Close camera' : 'Take photo with location'}"
    data-testid="camera-button"
>
    <Camera size={24} />
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

{#if menuOpen}

    <nav class="nav-menu">
        {#if $app.debug  === 3}
            <div class="debug-info">
                <h4>Auth Debug:</h4>
                <pre>isAuthenticated: {$auth.isAuthenticated}</pre>
                <pre>token: {$auth.token ? 'exists' : 'none'}</pre>
                <pre>user: {$auth.user ? $auth.user.username : 'none'}</pre>
            </div>
        {/if}

        <ul>
            {#if FEATURE_USER_ACCOUNTS}
                {#if isAuthenticated}
                    <li><a href="/photos" on:click={() => menuOpen = false}>
                        My Photos
                    </a></li>
                {/if}
            {/if}
            <li><a href="/sources" on:click={() => menuOpen = false}>Sources</a></li>
            <li>
                <a href="/hillview.apk" download on:click={() => menuOpen = false}>
                    <Download size={18} />
                    Download Android App
                </a>
            </li>
            {#if FEATURE_USER_ACCOUNTS}
                {#if isAuthenticated}
                    <li>
                        <button class="menu-button logout" on:click={handleLogout}>
                            <LogOut size={18} />
                            Logout
                        </button>
                    </li>
                {:else}
                    <li>
                        <a href="/login" on:click={() => menuOpen = false}>
                            <User size={18} />
                            Login / Register
                        </a>
                    </li>
                {/if}
            {/if}
            <li><a href="/about" on:click={() => menuOpen = false}>About</a></li>
        </ul>
    </nav>
{/if}

<div class="container" class:max-mode={$app.displayMode === 'max'}>
    <div class="panel photo-panel">
        {#if showCameraView}
            <CameraCapture 
                show={true}
                on:close={() => app.update(a => ({...a, activity: 'view'}))}
                locationData={$captureLocationWithCompassBearing ? {
                    latitude: $captureLocationWithCompassBearing.latitude,
                    longitude: $captureLocationWithCompassBearing.longitude,
                    altitude: $captureLocationWithCompassBearing.altitude,
                    accuracy: $captureLocationWithCompassBearing.accuracy,
                    heading: $captureLocationWithCompassBearing.heading,
                    source: $captureLocationWithCompassBearing.source
                } : null}
                locationError={null}
                locationReady={!!$captureLocationWithCompassBearing}
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
<DebugOverlay bind:this={debugOverlay} />

<style>
    /* Reset default margin, padding and prevent body scroll */
    :global(html, body) {
        margin: 0;
        padding: 0;
        overflow: hidden;
        width: 100%;
        height: 100%;
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

    .nav-menu {
        z-index: 30000;
        background: white;
        position: absolute;
        top: 0;
        left: 0;
        width: 250px;
        height: 100vh;
        padding: 60px 1rem 1rem;
        box-shadow: 0 0 10px rgba(0, 0, 0, 0.2);
    }

    .nav-menu ul {
        list-style: none;
        padding: 0;
        margin: 0;
    }

    .nav-menu li {
        margin-bottom: 1rem;
    }

    .nav-menu li a {
        display: flex;
        align-items: center;
        gap: 10px;
        text-decoration: none;
        color: #333;
        font-size: 1.2rem;
        padding: 8px 0;
    }

    .menu-button {
        display: flex;
        align-items: center;
        gap: 10px;
        background: none;
        border: none;
        font-size: 1.2rem;
        color: #333;
        padding: 8px 0;
        cursor: pointer;
        width: 100%;
        text-align: left;
    }

    .menu-button.logout {
        color: #e53935;
    }

    .nav-menu li a:hover,
    .menu-button:hover {
        color: #4a90e2;
    }

    .menu-button.logout:hover {
        color: #c62828;
    }
    
    .debug-info {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 4px;
        padding: 10px;
        margin: 0 10px 16px;
        font-family: monospace;
        font-size: 12px;
    }
    
    .debug-info h4 {
        margin-top: 0;
        margin-bottom: 8px;
        color: #495057;
    }
    
    .debug-info pre {
        margin: 0;
        white-space: pre-wrap;
        word-break: break-all;
    }
    

    :global(#sentry-feedback) {
        --trigger-background: rgba(74, 144, 226, 0.6);
        --inset: auto auto 0 0;
    }
    
</style>
