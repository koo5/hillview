<script lang="ts">
    import {createEventDispatcher, onDestroy, onMount} from 'svelte';
    import {get} from 'svelte/store';
    import {photoCaptureSettings} from '$lib/stores';
    import {app} from "$lib/data.svelte";
    import DualCaptureButton from './DualCaptureButton.svelte';
    import CaptureQueueStatus from './CaptureQueueStatus.svelte';
    import CaptureQueueIndicator from './CaptureQueueIndicator.svelte';
    import CameraOverlay from './CameraOverlay.svelte';
    import AutoUploadPrompt from './AutoUploadPrompt.svelte';
    import {captureQueue } from '$lib/captureQueue';
    import {injectPlaceholder, removePlaceholder} from '$lib/placeholderInjector';
    import {generateTempId, type PlaceholderLocation} from '$lib/utils/placeholderUtils';
    import {bearingState, spatialState} from '$lib/mapState';
    import { createPermissionManager } from '$lib/permissionManager';
    import {
        availableCameras,
        selectedCameraId,
        cameraEnumerationSupported,
        enumerateCameraDevices,
        type CameraDevice
    } from '$lib/cameraDevices.svelte';
    import { tauriCamera, isCameraPermissionCheckAvailable } from '$lib/tauri';
    import { addPluginListener, type PluginListener } from '@tauri-apps/api/core';

    const dispatch = createEventDispatcher();


    const permissionManager = createPermissionManager('camera');

    // Store unlisten function for cleanup
    let cameraPermissionUnlisten: PluginListener | null = null;

	// show or hide the whole capture UI, parent component controls this
    export let show = false;


	// updated with $bearingState && $spatialState
	let locationData: {
        latitude?: number;
        longitude?: number;
        altitude?: number | null;
        accuracy?: number;
        heading?: number | null;
        locationSource: 'gps' | 'map';
        bearingSource: string;
    } | null = null;


    // TODO - this should be set if location tracking fails, but we need to figure out the exact semantics
    //  - we know that location tracking is automatically enabled when the camera modal is opened,
    // and the location tracking service should be able to produce errors if it can't get a fix.
    // but it should be nulled when location is set by map panning.
	let locationError: string | null = null;

	// TODO - this is probably redundant
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
    let cameraPermissionPollInterval: ReturnType<typeof setInterval> | null = null;
    let hasRequestedPermission = false;
    let retryCount = 0;
    let maxRetries = 5;
    let retryDelay = 1000; // Start with 1 second
    let retryTimeout: number | null = null;
    let permissionRetryInterval: number | null = null;
    let showCameraSelector = false;
    let photoCapturedCount = 0; // Track captures for auto-upload prompt

    async function checkCameraPermission(): Promise<PermissionState | null> {
        try {
            if ('permissions' in navigator && 'query' in navigator.permissions) {
                const result = await navigator.permissions.query({name: 'camera' as PermissionName});
                return result.state;
            }
        } catch (error) {
            console.log('🢄Permission API not supported or error:', error);
        }
        return null;
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
        console.log('🢄[CAMERA] Checking camera permission before auto-start...');

        // Check camera permission status using Tauri if available
        if (isCameraPermissionCheckAvailable() && tauriCamera) {
                const hasPermission = await tauriCamera.checkCameraPermission();
                console.log('🢄[CAMERA] Camera permission status from Tauri:', hasPermission);

                if (hasPermission) {
                    console.log('🢄[CAMERA] Permission granted, starting camera immediately');
                    await startCamera();
                    return;
                } else {
                    console.log('🢄[CAMERA] Permission not granted, showing Enable Camera button');
                    cameraError = 'Camera access required';
                    needsPermission = true;
                    return;
                }
        }

        // Try to acquire permission lock first
        const lockAcquired = await permissionManager.acquireLock();
        if (!lockAcquired) {
            console.log('🢄[CAMERA] Permission system busy (location tracking?), will retry later');
            // Schedule retry with interval
            if (!permissionRetryInterval) {
                permissionRetryInterval = window.setInterval(() => {
                    if (show && !stream && !cameraReady) {
                        checkAndStartCamera();
                    } else {
                        // Clean up interval if conditions no longer apply
                        if (permissionRetryInterval) {
                            clearInterval(permissionRetryInterval);
                            permissionRetryInterval = null;
                        }
                    }
                }, 1000);
            }
            return;
        }

        // Clear retry interval since we successfully acquired the lock
        if (permissionRetryInterval) {
            clearInterval(permissionRetryInterval);
            permissionRetryInterval = null;
        }

        await startCamera();

        await permissionManager.releaseLock();

    }

    async function startCamera() {
        console.log('🢄[CAMERA] Starting camera...');
        try {
            // Check for camera support
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                throw new Error('Camera API not supported');
            }

            // Stop any existing stream
            if (stream) {
                console.log('🢄[CAMERA] Stopping existing stream');
                stream.getTracks().forEach(track => track.stop());
                stream = null;
            }

            // Clear any previous errors
            cameraError = null;

            // Mark that we're about to request permission
            hasRequestedPermission = true;

            // Use probe-then-enumerate pattern for better compatibility
            let constraints: MediaStreamConstraints;

            const selectedId = get(selectedCameraId);
            if (selectedId) {
                // Use explicitly selected camera with exact deviceId
                constraints = {
                    video: {
                        deviceId: { exact: selectedId },
                        width: { min: 1280, ideal: 3840 },  // 4K ideal, 720p minimum
                        height: { min: 720, ideal: 2160 }
                    }
                };
                console.log('🢄[CAMERA] Using selected camera device:', selectedId.slice(0, 8) + '...');
            } else {
                // First attempt: probe with ideal facingMode (not exact) to trigger permission
                constraints = {
                    video: {
                        facingMode: { ideal: facing },  // Use ideal, not exact
                        width: { min: 1280, ideal: 3840 },  // 4K ideal, 720p minimum
                        height: { min: 720, ideal: 2160 }
                    }
                };
                console.log('🢄[CAMERA] Probing with ideal facingMode:', facing);
            }

            console.log('🢄[CAMERA] Requesting camera with constraints:', constraints);
            stream = await navigator.mediaDevices.getUserMedia(constraints);
            console.log('🢄[CAMERA] Got media stream:', stream);

            if (video) {
                console.log('🢄[CAMERA] Setting video source');

                // Set video attributes for mobile compatibility
                video.muted = true;  // Mobile autoplay safety
                video.setAttribute('playsinline', 'true');
                video.srcObject = stream;

                // Wait for metadata to load
                await new Promise((resolve) => {
                    video.onloadedmetadata = () => {
                        console.log('🢄[CAMERA] Video metadata loaded');
                        resolve(undefined);
                    };
                });

                await video.play();
                console.log('🢄[CAMERA] Video playing - clearing error state');
                console.log('🢄[CAMERA] Before clear: cameraError =', cameraError, 'needsPermission =', needsPermission, 'cameraReady =', cameraReady);
                cameraReady = true;
                cameraError = null;
                needsPermission = false;
                retryCount = 0; // Reset retry count on success
                console.log('🢄[CAMERA] After clear: cameraError =', cameraError, 'needsPermission =', needsPermission, 'cameraReady =', cameraReady);

                // Reset permission request flag on success
                hasRequestedPermission = false;

                // Release permission lock on success
                await permissionManager.releaseLock();

                // Clear any pending retries
                if (retryTimeout) {
                    clearTimeout(retryTimeout);
                    retryTimeout = null;
                }

                // Stop camera permission polling since camera stream is verified working
                if (cameraPermissionPollInterval) {
                    console.log('🢄[CAMERA] Camera stream verified working - stopping permission polling interval');
                    clearInterval(cameraPermissionPollInterval);
                    cameraPermissionPollInterval = null;
                }

                // Now enumerate cameras for the selector (after permission granted)
                if (!get(selectedCameraId)) {
                    try {
                        await enumerateCameraDevices();
                        console.log('🢄[CAMERA] Camera enumeration completed');
                    } catch (error) {
                        console.log('🢄[CAMERA] Camera enumeration failed, but stream is working:', error);
                    }
                }

                // Check zoom support
                if (stream && stream.getVideoTracks) {
                    videoTrack = stream.getVideoTracks()[0];
                    if (videoTrack) {
                        const capabilities = videoTrack.getCapabilities() as any;
						console.log('🢄[CAMERA] Video track capabilities:', JSON.stringify(capabilities));
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
                console.error('🢄[CAMERA] Video element not found!');
                throw new Error('Video element not available');
            }
        } catch (error) {
            console.error('🢄[CAMERA] Camera error:', error);
            cameraError = error instanceof Error ? error.message : 'Failed to access camera';
            cameraReady = false;

            // Check if this is a permission error
            if (error instanceof DOMException &&
                (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError')) {
                hasRequestedPermission = true;
                console.log('🢄[CAMERA] Permission denied by user');
                // Release lock - permission dialog is done, user can try again later
                await permissionManager.releaseLock();
            } else {
                // For non-permission errors, release lock and schedule a retry
                await permissionManager.releaseLock();
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
            console.error('🢄Failed to set zoom:', error);
        }
    }

    function handleZoomChange(event: Event) {
        const target = event.target as HTMLInputElement;
        setZoom(parseFloat(target.value));
    }

    async function selectCamera(camera: CameraDevice) {
        console.log('🢄[CAMERA] Selecting camera:', camera.label);

        // Hide the dropdown
        showCameraSelector = false;

        // Set the selected camera in the store
        selectedCameraId.set(camera.deviceId);

        // Restart camera with new device
        if (cameraReady && stream) {
            console.log('🢄[CAMERA] Switching to camera:', camera.label);

            // Stop current stream
            stream.getTracks().forEach(track => track.stop());
            stream = null;
            cameraReady = false;

            // Start with new camera
            try {
                await startCamera();
            } catch (error) {
                console.error('🢄[CAMERA] Failed to switch camera:', error);
                cameraError = `Failed to switch to ${camera.label}`;
            }
        }
    }

    async function handleCapture(event: CustomEvent<{ mode: 'slow' | 'fast' }>) {
        if (!video || !canvas || !cameraReady || !locationData ||
            locationData.latitude === undefined || locationData.longitude === undefined) {
            console.warn('🢄📍 Cannot capture: camera not ready or no location');
            return;
        }

        console.log('🢄Capture event:', JSON.stringify(event.detail));

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
            locationSource: locationData.locationSource,
            bearingSource: locationData.bearingSource,
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
        if (!context)
		{
			console.error('🢄Capture error: Unable to get canvas context');
			return;
		}

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

                    // Trigger auto-upload prompt check
                    photoCapturedCount++;
                }
            }, 'image/jpeg', quality);
        } catch (error) {
            console.error('🢄Capture error:', error);
            // Remove placeholder on error
            removePlaceholder(tempId);
        }
		console.log('🢄Capture process initiated');
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
                console.log('🢄App going to background, stopping camera');
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
                console.log('🢄App returning to foreground, restarting camera');
                // Reset retry count for fresh attempt when returning from background
                retryCount = 0;
                cameraError = null;
                needsPermission = false;
                startCamera();
            }
            wasShowingBeforeHidden = false;
        }
    }

    function handleClickOutside(event: MouseEvent) {
        if (showCameraSelector) {
            const target = event.target as Element;
            const selectorContainer = document.querySelector('.camera-selector-container');

            if (selectorContainer && !selectorContainer.contains(target)) {
                showCameraSelector = false;
            }
        }
    }

    // Try to auto-start camera with permission lock coordination
    $: if (show) {
        if (!stream && !cameraError && !cameraReady && !hasRequestedPermission) {
            console.log('🢄[CAMERA] Modal shown, attempting to start camera with permission coordination');
            retryCount = 0; // Reset retry count when modal opens
            checkAndStartCamera();
        }
    } else if (!show && stream) {
        // Stop camera when modal closes
        console.log('🢄Modal hidden, stopping camera');
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
            locationSource: $spatialState.source || 'unknown',
            bearingSource: $bearingState.source || 'unknown',
        };
        locationReady = true;
        locationError = null;
    }

    onMount(async () => {
        document.addEventListener('visibilitychange', handleVisibilityChange);
        document.addEventListener('click', handleClickOutside);

        // Listen for native camera permission granted event
        if (isCameraPermissionCheckAvailable()) {
                cameraPermissionUnlisten = await addPluginListener('hillview', 'camera-permission-granted', async (event) => {
                    console.log('🢄[CAMERA] CAMERA PERMISSION Event data:', JSON.stringify(event));

                    if (show && cameraError) {
                        console.log('🢄[CAMERA] Conditions met - retrying camera after native permission granted');
                        cameraError = null;
                        needsPermission = false;
                        hasRequestedPermission = false;
                        retryCount = 0;
                        try {
                            await startCamera();
                            console.log('🢄[CAMERA] startCamera() completed after permission event');
                        } catch (err) {
                            console.error('🢄[CAMERA] startCamera() failed after permission event:', err);
                        }
                    } else {
                        console.log('🢄[CAMERA] Not retrying camera - show:', show, 'cameraError:', cameraError);
                    }
                });

                console.log('🢄[CAMERA] Camera permission event listener setup complete');

        } else {
            console.log('🢄[CAMERA] Camera permission check not available - skipping event listener');
        }

        // Start simple permission polling from Kotlin
        if (isCameraPermissionCheckAvailable() && tauriCamera) {
            cameraPermissionPollInterval = setInterval(async () => {
                    const hasPermission = await tauriCamera!.checkCameraPermission();
                    if (hasPermission && cameraError === 'Camera access required') {
                        console.log('🢄[CAMERA POLL] Permission granted, retrying camera');
                        cameraError = null;
                        needsPermission = false;
                        await startCamera();
                    }
            }, 1000);
        }
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
        if (permissionRetryInterval) {
            clearInterval(permissionRetryInterval);
        }
        if (cameraPermissionPollInterval) {
            clearInterval(cameraPermissionPollInterval);
        }
        if (cameraPermissionUnlisten) {
            console.log('🢄[CAMERA] Cleaning up camera permission event listener');
            // Note: PluginListener cleanup is handled automatically by Tauri
            cameraPermissionUnlisten = null;
        }
        document.removeEventListener('visibilitychange', handleVisibilityChange);
        document.removeEventListener('click', handleClickOutside);

        // Clean up permission manager
        permissionManager.cleanup();
    });
</script>

{#if show}
    <div class="camera-container">
        <div class="camera-content">
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
                        <button class="retry-button" on:click={async () => {

                            console.log('🢄[CAMERA] Enable Camera button clicked');

                            // Try native permission request first if available
                            if (isCameraPermissionCheckAvailable() && tauriCamera) {
                                try {
                                    console.log('🢄[CAMERA] Using native permission request');
                                    const permissionResult = await tauriCamera.requestCameraPermission();

                                    if (permissionResult.granted) {
                                        console.log('🢄[CAMERA] Native permission granted, starting camera');
                                        cameraError = null;
                                        needsPermission = false;
                                        hasRequestedPermission = false;
                                        if (permissionCheckInterval) {
                                            clearInterval(permissionCheckInterval);
                                            permissionCheckInterval = null;
                                        }
                                        retryCount = 0;
                                        await startCamera();
                                        return;
                                    } else {
                                        console.log('🢄[CAMERA] Native permission denied:', permissionResult.error);
                                        cameraError = permissionResult.error || 'Camera permission denied';
                                        needsPermission = true;
                                        return;
                                    }
                                } catch (error) {
                                    console.warn('🢄[CAMERA] Native permission request failed, falling back to WebView:', error);
                                }
                            }

                            // Fallback to WebView permission flow
                            console.log('🢄[CAMERA] Using WebView permission flow');

                            // Try to acquire permission lock before starting camera
                            const lockAcquired = await permissionManager.acquireLock();
                            if (!lockAcquired) {
                                console.log('🢄[CAMERA] Permission system busy, cannot start camera right now');
                                return;
                            }

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
                {#if !cameraError}
                    <CameraOverlay
                        {locationData}
                        {locationError}
                        {locationReady}
                    />
                {/if}

                <!-- Auto-upload prompt (shows after photo capture) -->
                <AutoUploadPrompt
                    photoCaptured={photoCapturedCount > 0}
                />
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
                <!-- Camera selector button (lower-left) -->
                {#if cameraReady && $cameraEnumerationSupported && $availableCameras.length > 1}
                    <div class="camera-selector-container">
                        <button
                            class="camera-selector-button"
                            on:click={() => showCameraSelector = !showCameraSelector}
                            aria-label="Select camera"
                        >
                            📷
                        </button>

                        {#if showCameraSelector}
                            <div class="camera-selector-dropdown">
                                {#each $availableCameras as camera}
                                    <button
                                        class="camera-option"
                                        class:selected={$selectedCameraId === camera.deviceId}
                                        on:click={() => selectCamera(camera)}
                                    >
                                        <span class="camera-facing">
                                            {#if camera.facingMode === 'front'}🤳{:else if camera.facingMode === 'back'}📷{:else}📹{/if}
                                        </span>
                                        <span class="camera-label">
                                            {camera.label}
                                            {#if camera.isPreferred}⭐{/if}
                                        </span>
                                    </button>
                                {/each}
                            </div>
                        {/if}
                    </div>
                {/if}

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

            <!-- Capture queue indicator (always visible when queue has items) -->
            <div class="queue-indicator-overlay">
                <CaptureQueueIndicator/>
            </div>
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

    .camera-selector-container {
        position: absolute;
        left: 2rem;
        bottom: 2rem;
    }

    .camera-selector-button {
        background: rgba(255, 255, 255, 0.2);
        border: none;
        color: white;
        cursor: pointer;
        padding: 0.75rem;
        border-radius: 50%;
        font-size: 1.5rem;
        transition: background 0.2s;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.3);
    }

    .camera-selector-button:hover {
        background: rgba(255, 255, 255, 0.3);
    }

    .camera-selector-dropdown {
        position: absolute;
        bottom: 100%;
        left: 0;
        margin-bottom: 0.5rem;
        background: rgba(0, 0, 0, 0.9);
        border-radius: 8px;
        padding: 0.5rem;
        min-width: 200px;
        backdrop-filter: blur(20px);
        border: 1px solid rgba(255, 255, 255, 0.2);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
    }

    .camera-option {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        width: 100%;
        padding: 0.75rem;
        background: transparent;
        border: none;
        color: white;
        cursor: pointer;
        border-radius: 6px;
        transition: background 0.2s;
        text-align: left;
    }

    .camera-option:hover {
        background: rgba(255, 255, 255, 0.1);
    }

    .camera-option.selected {
        background: rgba(74, 144, 226, 0.3);
        border: 1px solid rgba(74, 144, 226, 0.5);
    }

    .camera-facing {
        font-size: 1.2rem;
        flex-shrink: 0;
    }

    .camera-label {
        font-size: 0.9rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        flex: 1;
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

    .queue-indicator-overlay {
        position: absolute;
        bottom: 20px;
        right: 20px;
        z-index: 1001;
    }
</style>
