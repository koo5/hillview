<script lang="ts">
    import {onDestroy, onMount, tick} from 'svelte';
    import PhotoGallery from '../components/Gallery.svelte';
    import Map from '../components/Map.svelte';
    import UploadDialog from '../components/UploadDialog.svelte';
    import {Camera, Compass, User, LogOut, Upload, Menu, Download, Maximize2, Minimize2} from 'lucide-svelte';
    import {fetch_photos} from "$lib/sources";
    import {dms} from "$lib/utils";
    import {app, pos, bearing, turn_to_photo_to, update_bearing, update_pos} from "$lib/data.svelte";
    import {LatLng} from 'leaflet';
    import { goto, replaceState } from "$app/navigation";
    import {get, writable} from "svelte/store";
    import { auth, logout, checkAuth } from "$lib/auth.svelte";
    import CameraCapture from '../components/CameraCapture.svelte';
    import DebugOverlay from '../components/DebugOverlay.svelte';
    import MapillaryCacheStatus from '../components/MapillaryCacheStatus.svelte';
    import { gpsLocation } from '$lib/location.svelte';
    import { photoCaptureService } from '$lib/photoCapture';
    import { devicePhotos } from '$lib/stores';
    import { captureLocation, captureLocationWithFusedBearing } from '$lib/captureLocation';
    import '$lib/captureLocationManager'; // Activate capture location management
    import '$lib/mapBearingSync'; // Sync map bearing with sensors

    let map: any = null;
    let mapComponent: any = null;
    let update_url = false;
    let menuOpen = false;
    let showUploadDialog = false;
    let showCameraView = false;
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

        let p = get(pos);
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
            update_pos((v) => {return {...p, reason: 'url'}});
            map?.setView(p.center, p.zoom);
        }

        if (bearingParam) {
            console.log('Setting bearing to', bearingParam, 'from URL');
            bearing.set(parseFloat(bearingParam));
        }

        await fetch_photos();
        window.addEventListener('keydown', handleKeyDown);

        setTimeout(() => {
            update_url = true;
        }, 100);

    });

    pos.subscribe(p => {
        if (!update_url) {
            return;
        }
        const url = new URL(window.location.href);
        url.searchParams.set('lat', String(p.center.lat));
        url.searchParams.set('lon', String(p.center.lng));
        url.searchParams.set('zoom', String(p.zoom));
        console.log('Setting URL to', url.toString());
        replaceState2(url.toString());
    });

    bearing.subscribe(b => {
        if (!update_url) {
            return;
        }
        const url = new URL(window.location.href);
        url.searchParams.set('bearing', String(b));
        console.log('Setting URL to', url.toString());
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

    onDestroy(() => {
        console.log('Page destroyed');
        window.removeEventListener('keydown', handleKeyDown);
    });

    async function handleKeyDown(e: KeyboardEvent) {
        if (!e.ctrlKey && !e.altKey && !e.metaKey) {
            if (e.key === 'z') {
                e.preventDefault();
                update_bearing(-5);
            } else if (e.key === 'x') {
                e.preventDefault();
                update_bearing(5);
            } else if (e.key === 'c') {
                e.preventDefault();
                await turn_to_photo_to('left');
            } else if (e.key === 'v') {
                e.preventDefault();
                await turn_to_photo_to('right');
            } else if (e.key === 'd') {
                e.preventDefault();
                app.update(a => {
                    a.debug = a.debug + 1;
                    if (a.debug > 5) {
                        a.debug = 0;
                    }
                    return a;
                });
            } else if (e.key === 'm') {
                e.preventDefault();
                toggleDisplayMode();
            }
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

    let debugOpen = false;
    const toggleDebug = () => {
        app.update(a => {
            a.debug = a.debug ? 0 : 1;
            return a;
        });
    }

    function handleLogout() {
        logout();
        menuOpen = false;
    }

    async function handlePhotoCaptured(event: CustomEvent<{ file: File }>) {
        const { file } = event.detail;
        const captureLoc = $captureLocationWithFusedBearing;
        
        if (!captureLoc) {
            alert('Location not available. Please wait for GPS or move the map.');
            return;
        }
        
        try {
            // Prepare photo data with capture location (either GPS or map position)
            const photoData = {
                image: file,
                location: {
                    latitude: captureLoc.latitude,
                    longitude: captureLoc.longitude,
                    altitude: captureLoc.altitude,
                    accuracy: captureLoc.accuracy || 1 // Default to 1m if undefined
                },
                bearing: captureLoc.heading,
                timestamp: Date.now()
            };
            
            console.log(`Saving photo with ${captureLoc.source} location:`, captureLoc);
            
            // Save photo with EXIF metadata
            const savedPhoto = await photoCaptureService.savePhotoWithExif(photoData);
            
            // Update device photos store
            devicePhotos.update(photos => [...photos, savedPhoto]);
            
            // Refresh photos to show on map
            await fetch_photos();
            
            // Keep camera view open for continuous capture
        } catch (error) {
            console.error('Failed to save captured photo:', error);
            alert('Failed to save photo. Please try again.');
        }
    }

    function toggleCamera() {
        showCameraView = !showCameraView;
        if (showCameraView && mapComponent) {
            // Enable location tracking when camera opens
            mapComponent.enableLocationTracking();
        } else if (!showCameraView && mapComponent) {
            // Optionally disable location tracking when camera closes
            // Commenting out to let user control via location button
            // mapComponent.disableLocationTracking();
        }
    }
    
    // Use the reactive GPS location store
    $: currentLocation = $gpsLocation;

    // Subscribe to auth store
    let isAuthenticated = false;
    auth.subscribe(value => {
        isAuthenticated = value.isAuthenticated;
    });
</script>

<!-- Upload button (visible when authenticated) -->
{#if isAuthenticated}
    <div class="upload-button-container">
        <button class="floating-upload-button" on:click={() => showUploadDialog = true}>
            <Upload size={24} />
        </button>
    </div>
{/if}

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
    on:click={debugOverlay.toggleDebug}
    class="debug-toggle"
    on:keydown={(e) => e.key === 'Enter' && debugOverlay.toggleDebug()}
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
            <li><a href="/" on:click={() => menuOpen = false}>Map</a></li>
            <li>
                <button class="menu-button" on:click={() => {
                    showUploadDialog = true;
                    menuOpen = false;
                }}>
                    <Upload size={18} />
                    Upload Photos
                </button>
            </li>
            {#if isAuthenticated}
                <li><a href="/photos" on:click={() => menuOpen = false}>
                    <Upload size={18} />
                    My Photos
                </a></li>
            {/if}
            <li><a href="/upload" on:click={() => menuOpen = false}>Sources</a></li>
            <li><a href="/about" on:click={() => menuOpen = false}>About</a></li>
            <li>
                <a href="/hillview.apk" download on:click={() => menuOpen = false}>
                    <Download size={18} />
                    Download Android App
                </a>
            </li>
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
        </ul>
    </nav>
{/if}

<div class="container" class:max-mode={$app.displayMode === 'max'}>
    <div class="panel photo-panel">
        {#if showCameraView}
            <CameraCapture 
                show={true}
                on:close={() => showCameraView = false}
                on:photoCaptured={handlePhotoCaptured}
                locationData={$captureLocationWithFusedBearing ? {
                    latitude: $captureLocationWithFusedBearing.latitude,
                    longitude: $captureLocationWithFusedBearing.longitude,
                    altitude: $captureLocationWithFusedBearing.altitude,
                    accuracy: $captureLocationWithFusedBearing.accuracy,
                    heading: $captureLocationWithFusedBearing.heading,
                    source: $captureLocationWithFusedBearing.source
                } : null}
                locationError={null}
                locationReady={!!$captureLocationWithFusedBearing}
            />
        {:else}
            <PhotoGallery/>
        {/if}
    </div>
    <div class="panel map-panel">
        <Map bind:this={mapComponent}/>
    </div>
</div>

<!-- Upload Dialog -->
<UploadDialog 
    show={showUploadDialog} 
    on:close={() => showUploadDialog = false} 
    on:uploaded={() => {
        // Refresh photos after upload
        fetch_photos();
    }}
/>


<!-- Debug Overlay -->
<DebugOverlay bind:this={debugOverlay} />

<!-- Mapillary Cache Status -->
<MapillaryCacheStatus />

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
    
    .upload-button-container {
        position: fixed;
        bottom: 20px;
        right: 20px;
        z-index: 1000;
    }
    
    .floating-upload-button {
        width: 56px;
        height: 56px;
        border-radius: 50%;
        background-color: #4a90e2;
        color: white;
        border: none;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
        cursor: pointer;
        transition: background-color 0.3s, transform 0.2s;
    }
    
    .floating-upload-button:hover {
        background-color: #3a7bc8;
        transform: translateY(-2px);
    }
    
    .floating-upload-button:active {
        transform: translateY(0);
    }
    
    @media (max-width: 768px) {
        .upload-button-container {
            bottom: 16px;
            right: 16px;
        }
        
        .floating-upload-button {
            width: 48px;
            height: 48px;
        }
    }
    
</style>
