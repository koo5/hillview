<script lang="ts">
    import {createEventDispatcher, onDestroy, onMount} from 'svelte';
    import {X} from 'lucide-svelte';
    import {photoCaptureSettings} from '$lib/stores';
    import {app, cameraOverlayOpacity} from "$lib/data.svelte";
    import DualCaptureButton from './DualCaptureButton.svelte';
    import CaptureQueueStatus from './CaptureQueueStatus.svelte';
    import {captureQueue } from '$lib/captureQueue';
    import {injectPlaceholder, removePlaceholder} from '$lib/placeholderInjector';
    import {generateTempId, type PlaceholderLocation} from '$lib/utils/placeholderUtils';
    import {bearingState, spatialState} from '$lib/mapState';

    const dispatch = createEventDispatcher();

    export let show = false;


	// TODO - add location data
	let locationData: {
        latitude?: number;
        longitude?: number;
        altitude?: number | null;
        accuracy?: number;
        heading?: number | null;
    } | null = null;
    // TODO
	let locationError: string | null = null;
	// TODO
    let locationReady = false;

    let video: HTMLVideoElement;
    let canvas: HTMLCanvasElement;
    let stream: MediaStream | null = null;
    let facing: 'user' | 'environment' = 'environment';
    let cameraReady = false;
    let cameraError: string | null = null;
    let zoomSupported = false;
    let zoomLevel = 1;
    let minZoom = 1;
    let maxZoom = 1;
    let videoTrack: MediaStreamTrack | null = null;
    let wasShowingBeforeHidden = false;
    let permissionCheckInterval: number | null = null;
    let hasRequestedPermission = false;
    let retryCount = 0;
    let maxRetries = 5;
    let retryDelay = 1000; // Start with 1 second
    let retryTimeout: number | null = null;

    // Toggle overlay opacity through 6 levels: 0 (fully transparent) to 5 (most opaque)
    function toggleOverlayOpacity() {
        cameraOverlayOpacity.update(current => (current + 1) % 6);
    }

    async function checkCameraPermission(): Promise<PermissionState | null> {
        try {
            if ('permissions' in navigator && 'query' in navigator.permissions) {
                const result = await navigator.permissions.query({name: 'camera' as PermissionName});
                return result.state;
            }
        } catch (error) {
            console.log('Permission API not supported or error:', error);
        }
        return null;
    }

    async function startPermissionMonitoring() {
        // Clear any existing interval
        if (permissionCheckInterval) {
            clearInterval(permissionCheckInterval);
        }

        console.log('Starting permission monitoring...');
        // Check permission state periodically when we have an error
        permissionCheckInterval = window.setInterval(async () => {
            if (cameraError && (hasRequestedPermission || cameraError.includes('Camera access required'))) {
                const state = await checkCameraPermission();
                console.log('Monitoring camera permission:', state, 'hasRequestedPermission:', hasRequestedPermission);

                if (state === 'granted') {
                    console.log('Camera permission granted during monitoring, starting camera...');
                    clearInterval(permissionCheckInterval!);
                    permissionCheckInterval = null;
                    hasRequestedPermission = false;
                    cameraError = null; // Clear the error
                    startCamera();
                }
            }
        }, 500); // Check more frequently
    }

    function scheduleRetry() {
        if (retryTimeout) {
            clearTimeout(retryTimeout);
        }

        if (retryCount < maxRetries && show) {
            retryCount++;
            const delay = Math.min(retryDelay * retryCount, 5000); // Cap at 5 seconds
            console.log(`Scheduling camera retry ${retryCount}/${maxRetries} in ${delay}ms`);

            retryTimeout = window.setTimeout(() => {
                if (show && !stream) {
                    startCamera();
                }
            }, delay);
        }
    }

    let needsPermission = false;

    async function checkAndStartCamera() {
        console.log('[CAMERA] Checking camera permission before auto-start...');
        const permissionState = await checkCameraPermission();
        console.log('[CAMERA] Permission state returned:', permissionState);
        
        if (permissionState === 'granted') {
            console.log('[CAMERA] Permission already granted, starting camera automatically');
            startCamera();
        } else if (permissionState === 'prompt' || permissionState === null) {
            // For 'prompt' state or when Permissions API not available, try direct camera access
            // 'prompt' often means permission is set to "While using the app" which should work
            console.log('[CAMERA] Permission state is prompt/null, attempting direct camera access...');
            try {
                // Quick test to see if we can access camera without showing permission UI
                const testStream = await navigator.mediaDevices.getUserMedia({ 
                    video: { facingMode: facing } 
                });
                testStream.getTracks().forEach(track => track.stop());
                console.log('[CAMERA] Direct camera access successful, starting camera');
                startCamera();
            } catch (error) {
                console.log('[CAMERA] Direct camera access failed, showing enable button:', error);
                needsPermission = true;
                cameraError = 'Camera access required. Tap "Enable Camera" to continue.';
            }
        } else {
            console.log('[CAMERA] Permission explicitly denied, showing enable button');
            needsPermission = true;
            cameraError = 'Camera access required. Tap "Enable Camera" to continue.';
        }
    }

    async function startCamera() {
        console.log('[CAMERA] Starting camera...');
        try {
            // Check for camera support
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                throw new Error('Camera API not supported');
            }

            // Stop any existing stream
            if (stream) {
                console.log('[CAMERA] Stopping existing stream');
                stream.getTracks().forEach(track => track.stop());
                stream = null;
            }

            // Clear any previous errors
            cameraError = null;


            // Request camera access
            const constraints: MediaStreamConstraints = {
                video: {
                    facingMode: facing,
                    width: {ideal: 1920},
                    height: {ideal: 1080}
                }
            };

            console.log('[CAMERA] Requesting camera with constraints:', constraints);
            stream = await navigator.mediaDevices.getUserMedia(constraints);
            console.log('[CAMERA] Got media stream:', stream);

            if (video) {
                console.log('[CAMERA] Setting video source');
                video.srcObject = stream;

                // Wait for metadata to load
                await new Promise((resolve) => {
                    video.onloadedmetadata = () => {
                        console.log('[CAMERA] Video metadata loaded');
                        resolve(undefined);
                    };
                });

                await video.play();
                console.log('[CAMERA] Video playing - clearing error state');
                console.log('[CAMERA] Before clear: cameraError =', cameraError, 'needsPermission =', needsPermission, 'cameraReady =', cameraReady);
                cameraReady = true;
                cameraError = null;
                needsPermission = false;
                retryCount = 0; // Reset retry count on success
                console.log('[CAMERA] After clear: cameraError =', cameraError, 'needsPermission =', needsPermission, 'cameraReady =', cameraReady);

                // Clear any pending retries
                if (retryTimeout) {
                    clearTimeout(retryTimeout);
                    retryTimeout = null;
                }

                // Check zoom support
                if (stream && stream.getVideoTracks) {
                    videoTrack = stream.getVideoTracks()[0];
                    if (videoTrack) {
                        const capabilities = videoTrack.getCapabilities() as any;
                        if ('zoom' in capabilities && capabilities.zoom) {
                            zoomSupported = true;
                            minZoom = capabilities.zoom.min || 1;
                            maxZoom = capabilities.zoom.max || 1;
                            const settings = videoTrack.getSettings() as any;
                            zoomLevel = settings.zoom || 1;
                        }
                    }
                }
            } else {
                console.error('[CAMERA] Video element not found!');
                throw new Error('Video element not available');
            }
        } catch (error) {
            console.error('[CAMERA] Camera error:', error);
            cameraError = error instanceof Error ? error.message : 'Failed to access camera';
            cameraReady = false;

            // Check if this is a permission error
            if (error instanceof DOMException &&
                (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError')) {
                hasRequestedPermission = true;
                console.log('[CAMERA] Permission denied by user');
            } else {
                // For non-permission errors, schedule a retry
                scheduleRetry();
            }
        }
    }


    async function setZoom(level: number) {
        if (!videoTrack || !zoomSupported) return;

        try {
            await videoTrack.applyConstraints({
                advanced: [{zoom: level} as any]
            } as MediaTrackConstraints);
            zoomLevel = level;
        } catch (error) {
            console.error('Failed to set zoom:', error);
        }
    }

    function handleZoomChange(event: Event) {
        const target = event.target as HTMLInputElement;
        setZoom(parseFloat(target.value));
    }

    async function handleCapture(event: CustomEvent<{ mode: 'slow' | 'fast' }>) {
        if (!video || !canvas || !cameraReady || !locationData ||
            locationData.latitude === undefined || locationData.longitude === undefined) {
            console.warn('📍 Cannot capture: camera not ready or no location');
            return;
        }

        console.log('Capture event:', event.detail);

        const {mode} = event.detail;
        const timestamp = Date.now();
        const tempId = generateTempId();

        // Inject placeholder for immediate display
        const validLocation: PlaceholderLocation = {
            latitude: locationData.latitude!,
            longitude: locationData.longitude!,
            altitude: locationData.altitude,
            accuracy: locationData.accuracy || 1,
            heading: locationData.heading,
        };
        injectPlaceholder(validLocation, tempId);

        // Dispatch capture start event
        dispatch('captureStart', {
            location: locationData,
            timestamp,
            mode,
            tempId
        });

        const context = canvas.getContext('2d');
        if (!context) return;

        try {
            // Set canvas size to match video
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;

            // Draw video frame to canvas
            context.drawImage(video, 0, 0);

            // Convert canvas to blob with quality based on mode
            const quality = mode === 'fast' ? 0.7 : 0.9;

            canvas.toBlob(async (blob) => {
                if (blob) {
                    // Add to capture queue
                    await captureQueue.add({
                        id: `capture_${timestamp}`,
                        blob,
                        location: validLocation,
                        timestamp,
                        mode,
                        placeholderId: tempId
                    });
                }
            }, 'image/jpeg', quality);
        } catch (error) {
            console.error('Capture error:', error);
            // Remove placeholder on error
            removePlaceholder(tempId);
        }
    }

    function close() {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            stream = null;
        }
        cameraReady = false;
        cameraError = null;
        needsPermission = false;

        // Clear permission monitoring
        if (permissionCheckInterval) {
            clearInterval(permissionCheckInterval);
            permissionCheckInterval = null;
        }
        hasRequestedPermission = false;

        // Clear retry timeout
        if (retryTimeout) {
            clearTimeout(retryTimeout);
            retryTimeout = null;
        }
        retryCount = 0;

        show = false;
        dispatch('close');
    }

    function handleVisibilityChange() {
        if (document.hidden) {
            // App is going to background
            wasShowingBeforeHidden = show && !!stream;
            if (stream) {
                console.log('App going to background, stopping camera');
                stream.getTracks().forEach(track => track.stop());
                stream = null;
                cameraReady = false;
            }
            // Clear any pending retries when going to background
            if (retryTimeout) {
                clearTimeout(retryTimeout);
                retryTimeout = null;
            }
        } else {
            // App is coming back to foreground
            if (wasShowingBeforeHidden && show) {
                console.log('App returning to foreground, restarting camera');
                // Reset retry count for fresh attempt when returning from background
                retryCount = 0;
                cameraError = null;
                needsPermission = false;
                startCamera();
            }
            wasShowingBeforeHidden = false;
        }
    }

    // Check permission and conditionally start camera when modal opens
    $: if (show) {
        if (!stream && !cameraError && !cameraReady) {
            console.log('[CAMERA] Modal shown, checking camera permission');
            retryCount = 0; // Reset retry count when modal opens
            checkAndStartCamera();
        }
    } else if (!show && stream) {
        // Stop camera when modal closes
        console.log('Modal hidden, stopping camera');
        stream.getTracks().forEach(track => track.stop());
        stream = null;
        cameraReady = false;
        cameraError = null;
        needsPermission = false;
        hasRequestedPermission = false;
        if (permissionCheckInterval) {
            clearInterval(permissionCheckInterval);
            permissionCheckInterval = null;
        }
        if (retryTimeout) {
            clearTimeout(retryTimeout);
            retryTimeout = null;
        }
        retryCount = 0;
    }

    // Subscribe to bearingState and spatialState to update locationData
    $: if ($bearingState && $spatialState) {
        locationData = {
            latitude: $spatialState.center.lat,
            longitude: $spatialState.center.lng,
            altitude: null,
            accuracy: undefined,
            heading: $bearingState.bearing,
        };
        locationReady = true;
        locationError = null;
    }

    onMount(() => {
        document.addEventListener('visibilitychange', handleVisibilityChange);
    });

    onDestroy(() => {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }
        if (permissionCheckInterval) {
            clearInterval(permissionCheckInterval);
        }
        if (retryTimeout) {
            clearTimeout(retryTimeout);
        }
        document.removeEventListener('visibilitychange', handleVisibilityChange);
    });
</script>

{#if show}
    <div class="camera-container">
        <div class="camera-content">
            <div class="camera-header">
                <h2>Take Photo</h2>
                <button class="close-button" on:click={close} aria-label="Close">
                    <X size={24}/>
                </button>
            </div>

            <div class="camera-view">
                <!-- Debug: cameraError = {cameraError}, needsPermission = {needsPermission}, cameraReady = {cameraReady} -->
                
                <!-- Always render video element so it's available for binding -->
                <video bind:this={video} class="camera-video" playsinline style:display={cameraError ? 'none' : 'block'}>
                    <track kind="captions"/>
                </video>
                <canvas bind:this={canvas} style="display: none;"></canvas>

                {#if cameraError}
                    <div class="camera-error">
                        <p>📷 {cameraError}</p>
                        <button class="retry-button" on:click={() => {
                            cameraError = null;
                            needsPermission = false;
                            hasRequestedPermission = false;
                            if (permissionCheckInterval) {
                                clearInterval(permissionCheckInterval);
                                permissionCheckInterval = null;
                            }
                            retryCount = 0;
                            startCamera();
                        }}>
                            {needsPermission ? 'Enable Camera' : 'Try Again'}
                        </button>
                    </div>
                {/if}

                <!-- Location overlay -->
                <div 
                    class="location-overlay {locationReady ? 'ready' : ''} {locationError ? 'error' : ''}" 
                    class:opacity-0={$cameraOverlayOpacity === 0}
                    class:opacity-1={$cameraOverlayOpacity === 1}
                    class:opacity-2={$cameraOverlayOpacity === 2}
                    class:opacity-3={$cameraOverlayOpacity === 3}
                    class:opacity-4={$cameraOverlayOpacity === 4}
                    class:opacity-5={$cameraOverlayOpacity === 5}
                    style:display={cameraError ? 'none' : 'block'}
                    on:click={toggleOverlayOpacity}
                    on:keydown={(e) => e.key === 'Enter' && toggleOverlayOpacity()}
                    role="button"
                    tabindex="0"
                    aria-label="Toggle overlay transparency"
                    data-testid="location-overlay"
                >
                        {#if locationError}
                            <div class="location-row">
                                <span class="icon">⚠️</span>
                                <span>{locationError}</span>
                            </div>
                        {:else if locationData}
                                                        <div class="location-row">
                                                            <span class="icon">📍</span>
                                                            <span>{locationData.latitude?.toFixed(6)}°, {locationData.longitude?.toFixed(6)}°</span>
                                                        </div>
                                                        {#if locationData.heading !== null && locationData.heading !== undefined}
                                                            <div class="location-row">
                                                                <span class="icon">🧭</span>
                                                                <span>{locationData.heading.toFixed(1)}°</span>
                                                            </div>
                                                        {/if}
                                                        {#if locationData.altitude !== null && locationData.altitude !== undefined}
                                                            <div class="location-row">
                                                                <span class="icon">⛰️</span>
                                                                <span>{locationData.altitude.toFixed(1)}m</span>
                                                            </div>
                                                        {/if}
                            {#if locationData.accuracy}
                                <div class="location-row">
                                    <span class="icon">🎯</span>
                                    <span>±{locationData.accuracy.toFixed(0)}m</span>
                                </div>
                            {/if}
                        {:else}
                            <div class="location-row">
                                <span class="spinner"></span>
                                <span>Getting location...</span>
                            </div>
                        {/if}
                    </div>
            </div>

            {#if zoomSupported && cameraReady}
                <div class="zoom-control">
                    <label for="zoom-slider" class="zoom-label">
                        {zoomLevel.toFixed(1)}x
                    </label>
                    <input
                            id="zoom-slider"
                            type="range"
                            min={minZoom}
                            max={maxZoom}
                            step="0.1"
                            value={zoomLevel}
                            on:input={handleZoomChange}
                            class="zoom-slider"
                            aria-label="Camera zoom"
                    />
                </div>
            {/if}

            {#if $app.debug === 1}
                <!-- Save to Gallery toggle -->
                <div class="settings-control">
                    <label class="toggle-label">
                        <input
                                type="checkbox"
                                bind:checked={$photoCaptureSettings.hideFromGallery}
                                class="toggle-checkbox"
                        />
                        <span class="toggle-text">Hide from Gallery</span>
                    </label>
                </div>
            {/if}

            <div class="camera-controls">
                <DualCaptureButton
                        disabled={!cameraReady || !locationData}
                        on:capture={handleCapture}
                />
            </div>

            {#if $app.debug === 5}
                <div class="queue-status-overlay">
                    <CaptureQueueStatus/>
                </div>
            {/if}
        </div>
    </div>
{/if}

<style>
    .camera-container {
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        background: black;
    }

    .camera-content {
        background: black;
        width: 100%;
        height: 100%;
        max-width: 100vw;
        max-height: 100vh;
        display: flex;
        flex-direction: column;
        position: relative;
    }

    .camera-header {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem;
        background: linear-gradient(to bottom, rgba(0, 0, 0, 0.8), transparent);
        z-index: 10;
    }

    .camera-header h2 {
        margin: 0;
        color: white;
        font-size: 1.25rem;
    }

    .close-button {
        background: rgba(255, 255, 255, 0.2);
        border: none;
        color: white;
        cursor: pointer;
        padding: 0.5rem;
        border-radius: 50%;
        transition: background 0.2s;
    }

    .close-button:hover {
        background: rgba(255, 255, 255, 0.3);
    }

    .camera-view {
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        position: relative;
        overflow: hidden;
    }

    .camera-video {
        width: 100%;
        height: 100%;
        object-fit: contain;
    }

    .camera-error {
        text-align: center;
        color: white;
        padding: 2rem;
    }

    .camera-error p {
        margin-bottom: 1rem;
        font-size: 1.1rem;
    }

    .retry-button {
        padding: 0.75rem 1.5rem;
        background: #4a90e2;
        color: white;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-size: 1rem;
        transition: background 0.2s;
    }

    .retry-button:hover {
        background: #3a7bc8;
    }

    .camera-controls {
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 2rem;
        padding: 2rem;
        background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent);
    }


    .location-overlay {
        position: absolute;
        top: 80px;
        left: 1rem;
        padding: 0.25rem;
        border-radius: 8px;
        font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
        font-size: 0.85rem;
        max-width: 90%;
        cursor: pointer;
        transition: background 0.3s ease, border 0.3s ease, backdrop-filter 0.3s ease;
    }

    /* Opacity level 0: Fully transparent */
    .location-overlay.opacity-0 {
        background: transparent;
        border: none;
        backdrop-filter: none;
    }

    /* Opacity level 1: Very light */
    .location-overlay.opacity-1 {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(1px);
    }

    /* Opacity level 2: Light */
    .location-overlay.opacity-2 {
        background: rgba(255, 255, 255, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.15);
        backdrop-filter: blur(2px);
    }

    /* Opacity level 3: Medium (default) */
    .location-overlay.opacity-3 {
        background: rgba(255, 255, 255, 0.15);
        border: 1px solid rgba(255, 255, 255, 0.2);
        backdrop-filter: blur(3px);
    }

    /* Opacity level 4: Strong */
    .location-overlay.opacity-4 {
        background: rgba(255, 255, 255, 0.2);
        border: 1px solid rgba(255, 255, 255, 0.3);
        backdrop-filter: blur(4px);
    }

    /* Opacity level 5: Most opaque */
    .location-overlay.opacity-5 {
        background: rgba(255, 255, 255, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.4);
        backdrop-filter: blur(5px);
    }

    .location-overlay.ready {
        border-color: #4caf50;
    }

    .location-overlay.error {
        border-color: #f44336;
        background: rgba(244, 67, 54, 0.2);
    }

    .location-row {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin: 0.25rem 0;
        white-space: nowrap;
    }

    .location-row .icon {
        font-size: 1rem;
        width: 1.2rem;
        text-align: center;
    }

    .spinner {
        display: inline-block;
        width: 0.8rem;
        height: 0.8rem;
        border: 2px solid rgba(255, 255, 255, 0.3);
        border-top: 2px solid white;
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

    .zoom-control {
        position: absolute;
        right: 1rem;
        top: 50%;
        transform: translateY(-50%);
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 0.5rem;
        padding: 1rem;
        background: rgba(0, 0, 0, 0.6);
        border-radius: 8px;
        backdrop-filter: blur(10px);
    }

    .zoom-label {
        color: white;
        font-size: 0.9rem;
        font-weight: 500;
        min-width: 3em;
        text-align: center;
    }

    .zoom-slider {
        width: 150px;
        transform: rotate(-90deg);
        transform-origin: center;
        margin: 60px 0;
        cursor: pointer;
    }

    .zoom-slider::-webkit-slider-track {
        background: rgba(255, 255, 255, 0.3);
        height: 4px;
        border-radius: 2px;
    }

    .zoom-slider::-webkit-slider-thumb {
        -webkit-appearance: none;
        appearance: none;
        width: 16px;
        height: 16px;
        background: white;
        border-radius: 50%;
        cursor: pointer;
    }

    .zoom-slider::-moz-range-track {
        background: rgba(255, 255, 255, 0.3);
        height: 4px;
        border-radius: 2px;
    }

    .zoom-slider::-moz-range-thumb {
        width: 16px;
        height: 16px;
        background: white;
        border-radius: 50%;
        border: none;
        cursor: pointer;
    }

    .settings-control {
        position: absolute;
        bottom: 120px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(0, 0, 0, 0.6);
        padding: 0.75rem 1.5rem;
        border-radius: 8px;
        backdrop-filter: blur(10px);
    }

    .toggle-label {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        cursor: pointer;
        color: white;
        font-size: 0.95rem;
    }

    .toggle-checkbox {
        width: 18px;
        height: 18px;
        cursor: pointer;
    }

    .toggle-text {
        user-select: none;
    }

    @media (max-width: 600px) {
        .camera-header h2 {
            font-size: 1rem;
        }

        .camera-controls {
            padding: 1rem;
            gap: 1rem;
        }

        .zoom-control {
            right: 0.5rem;
            padding: 0.5rem;
        }

        .zoom-slider {
            width: 100px;
            margin: 40px 0;
        }
    }

    .queue-status-overlay {
        position: absolute;
        top: 80px;
        right: 20px;
        z-index: 1001;
    }
</style>