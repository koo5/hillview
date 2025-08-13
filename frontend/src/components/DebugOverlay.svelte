<script lang="ts">
    import {getBuildInfo} from '$lib/build-info';
    import {onMount} from 'svelte';
    import {photoInFront, photosInRange, photoToLeft, photoToRight, spatialState, visualState, visiblePhotos} from '$lib/mapState';
    import {gpsCoordinates, locationError, locationTracking} from '$lib/location.svelte';
    import {captureLocation, captureLocationWithCompassBearing} from '$lib/captureLocation';
    import {app, mapillary_cache_status, sources, sourceLoadingStatus} from '$lib/data.svelte';
    import {
        compassAvailable,
        compassData,
        currentHeading,
        currentSensorMode,
        deviceOrientation,
        switchSensorMode
    } from '$lib/compass.svelte';
    import {invoke} from '@tauri-apps/api/core';
    import {SensorMode, TAURI} from '$lib/tauri';

    // Detect sensor type
    let sensorType: 'tauri-rotation-vector' | 'device-orientation' | 'none' = 'none';
    let actualSensorSource: string | null = null;
    let isTauriAndroid = false;

    let buildInfo = getBuildInfo();
    let currentTime: string | undefined;
    let buildCommitHash: string | undefined;
    let buildBranch: string | undefined;
    let buildTimestamp: string | undefined;
    let debugPosition: 'left' | 'right' = 'left'; // Default to left to avoid photo thumbnails

    onMount(() => {
        // Detect sensor type
        isTauriAndroid = TAURI && /Android/i.test(navigator.userAgent);

        // Subscribe to compass data to detect which sensor is active
        const unsubscribe = compassData.subscribe(data => {
            if (data && isTauriAndroid) {
                sensorType = 'tauri-rotation-vector';
                // Extract sensor source from the data if available
                actualSensorSource = data.source || null;
            } else if (data && !isTauriAndroid) {
                sensorType = 'device-orientation';
                actualSensorSource = null;
            } else if (!$compassAvailable) {
                sensorType = 'none';
                actualSensorSource = null;
            }
        });

        // Update time every second
        const interval = setInterval(() => {
            currentTime = new Date().toLocaleTimeString(undefined, {hour12: false});
        }, 1000);

        // Check for debug mode in localStorage or URL params
        const urlParams = new URLSearchParams(window.location.search);
        const debugParam = urlParams.get('debug');
        const storedDebug = localStorage.getItem('debugMode');

        if (!!storedDebug) {
            app.update(a => ({...a, debug: parseInt(storedDebug)}));
        }

        if (!!debugParam) {
            app.update(a => ({...a, debug: parseInt(debugParam)}));
        }

        // Load saved position preference
        const savedPosition = localStorage.getItem('debugPosition');
        if (savedPosition === 'left' || savedPosition === 'right') {
            debugPosition = savedPosition;
        }

        // Fetch build information from Tauri commands
        invoke<string>('get_build_commit_hash').then((hash) => {
            buildCommitHash = hash;
        }).catch((err) => {
            console.log('Failed to get build commit hash:', err.message);
        });

        invoke<string>('get_build_branch').then((branch) => {
            buildBranch = branch;
        }).catch((err) => {
            console.log('Failed to get build branch:', err.message);
        });

        invoke<string>('get_build_ts').then((ts) => {
            buildTimestamp = ts;
        }).catch((err) => {
            console.log('Failed to get build timestamp:', err.message);
        });

        return () => {
            clearInterval(interval);
            unsubscribe();
        };
    });

    export function toggleDebug() {
        app.update(a => {
            const newDebug = ((a.debug || 0) + 1) % 4;
            return {...a, debug: newDebug};
        });
        console.log(`Debug mode toggled to ${$app.debug}`);
    }

    // Keyboard shortcut to toggle debug
    function handleKeydown(e: KeyboardEvent) {
        if (e.ctrlKey && e.shiftKey && e.key === 'D') {
            toggleDebug();
        }
        // Ctrl+Shift+L to toggle position
        if (e.ctrlKey && e.shiftKey && e.key === 'L' && $app.debug > 0) {
            debugPosition = debugPosition === 'left' ? 'right' : 'left';
            localStorage.setItem('debugPosition', debugPosition);
        }
    }
</script>

<svelte:window on:keydown={handleKeydown}/>

{#if $app.debug > 0}
    <div class="debug-overlay" class:left-position={debugPosition === 'left'}>
        <div class="debug-header">
            <span>Debug Info</span>
            <button on:click={toggleDebug} aria-label="Close debug">×</button>
        </div>
        <div class="debug-content">
            {#if $app.debug === 1}

                <div class="compact-row">
                    <span><strong>Build:</strong> {buildInfo.formattedTime}</span>
                    <span><strong>Now:</strong> {currentTime}</span>
                </div>

                {#if buildCommitHash || buildBranch}
                    <div class="compact-row">
                        <span>{buildBranch || 'Loading...'} @ {buildCommitHash?.slice(0, 7) || '...'}</span>
                    </div>
                {/if}

                <div class="debug-section">
                    <div><strong>Map View:</strong></div>
                    <div>Center: {$spatialState.center.lat.toFixed(4)}, {$spatialState.center.lng.toFixed(4)}</div>
                    <div>Zoom: {$spatialState.zoom.toFixed(1)} | Bearing: {$visualState.bearing.toFixed(0)}°</div>
                </div>

                {#if $gpsCoordinates}
                    <div class="debug-section">
                        <div><strong>GPS Location {$locationTracking ? '📍 Active' : '⭕ Inactive'}:</strong></div>
                        <div>Position: {$gpsCoordinates.latitude.toFixed(4)}
                            , {$gpsCoordinates.longitude.toFixed(4)}</div>
                        <div>Accuracy: ±{$gpsCoordinates.accuracy?.toFixed(0)}m
                            {#if $gpsCoordinates.altitude !== null && $gpsCoordinates.altitude !== undefined}
                                | Altitude: {$gpsCoordinates.altitude?.toFixed(0)}m
                            {/if}
                        </div>
                        <div>GPS Heading: {$gpsCoordinates.heading?.toFixed(0) || 'No movement'}°
                            {#if $gpsCoordinates.speed !== null && $gpsCoordinates.speed !== undefined}
                                | Speed: {($gpsCoordinates.speed * 3.6).toFixed(1)}km/h
                            {/if}
                        </div>
                        {#if $locationError}
                            <div class="error">Error: {$locationError}</div>
                        {/if}
                    </div>
                {:else}
                    <div class="debug-section">
                        <div><strong>GPS Location:</strong> {$locationTracking ? 'Waiting for signal...' : 'Disabled'}
                        </div>
                        {#if $locationError}
                            <div class="error">Error: {$locationError}</div>
                        {/if}
                    </div>
                {/if}

                {#if $captureLocation}
                    <div class="debug-section">
                        <div><strong>Capture Location (Source: <span
                                class="source-badge">{$captureLocation.source}</span>):</strong>
                        </div>
                        <div>Position: {$captureLocation.latitude.toFixed(4)}
                            , {$captureLocation.longitude.toFixed(4)}</div>
                        <div>Raw Heading: {$captureLocation?.heading?.toFixed(1) || 'None'}° | Accuracy:
                            ±{$captureLocation?.accuracy?.toFixed(0)}m
                            {#if $captureLocation.altitude !== undefined}
                                | Alt: {$captureLocation?.altitude?.toFixed(0)}m
                            {/if}
                        </div>
                        <div style="font-size: 9px; opacity: 0.7">
                            Updated: {new Date($captureLocation.timestamp || 0).toLocaleTimeString()}</div>
                    </div>
                {/if}

                <div class="debug-section sensor-section">

                    {#if isTauriAndroid && $compassAvailable}
                        <div class="sensor-mode-switcher">
                            <div><strong>Sensor Mode:</strong></div>
                            <select
                                    value={$currentSensorMode}
                                    on:change={(e) => switchSensorMode(Number(e.currentTarget.value))}
                                    class="sensor-mode-select"
                            >
                                <option value={SensorMode.ROTATION_VECTOR}>Rotation Vector</option>
                                <option value={SensorMode.GAME_ROTATION_VECTOR}>Game Rotation Vector</option>
                                <option value={SensorMode.MADGWICK_AHRS}>Madgwick AHRS</option>
                                <option value={SensorMode.COMPLEMENTARY_FILTER}>Complementary Filter</option>
                                <option value={SensorMode.UPRIGHT_ROTATION_VECTOR}>Upright Mode (Portrait)</option>
                                <option value={SensorMode.WEB_DEVICE_ORIENTATION}>Web DeviceOrientation API</option>
                            </select>
                        </div>
                    {/if}

                    <div><strong>🧭 Sensor API:</strong>
                        {actualSensorSource} - {sensorType}
                        {#if actualSensorSource}
                            <span class="sensor-type tauri">{actualSensorSource}</span>
                        {:else if sensorType === 'tauri-rotation-vector'}
                            <span class="sensor-type tauri">Android Sensor (waiting...)</span>
                        {:else if sensorType === 'device-orientation'}
                            <span class="sensor-type web">Web DeviceOrientation API</span>
                        {:else}
                            <span class="sensor-type none">Not Available</span>
                        {/if}
                    </div>
                    {#if $compassData}
                        <div><strong>Compass Bearing:</strong> {$compassData.magneticHeading?.toFixed(1) || 'N/A'}°
                        </div>
                        <div style="font-size: 10px; opacity: 0.8">True
                            bearing: {$compassData.trueHeading?.toFixed(1) || 'N/A'}° | Accuracy:
                            ±{$compassData.headingAccuracy?.toFixed(0) || 'N/A'}°
                        </div>
                        {#if sensorType === 'tauri-rotation-vector' && $deviceOrientation}
                            <div style="font-size: 10px; opacity: 0.8">Device tilt -
                                Pitch: {$deviceOrientation.beta?.toFixed(1)}° |
                                Roll: {$deviceOrientation.gamma?.toFixed(1)}
                                °
                            </div>
                        {/if}
                        <div style="font-size: 9px; opacity: 0.7">
                            Updated: {new Date($compassData.timestamp).toLocaleTimeString()}</div>
                    {:else if $compassAvailable}
                        <div style="opacity: 0.6">Waiting for sensor data...</div>
                    {/if}

                </div>

                {#if $currentHeading.heading !== null}
                    <div class="debug-section compass-bearing">
                        <div><strong>🎯 Compass Bearing:</strong></div>
                        <div>Heading: <span class="highlight">{$currentHeading.heading.toFixed(1)}°</span></div>
                        <div>Source: {$currentHeading.source}</div>
                        <div>Accuracy: {$currentHeading.accuracy?.toFixed(0) || 'N/A'}°</div>
                    </div>
                {/if}

                {#if $captureLocationWithCompassBearing}
                    <div class="debug-section photo-bearing">
                        <div><strong>📸 Photo Capture Data (Final):</strong></div>
                        <div>Bearing to be saved: <span
                                class="highlight">{$captureLocationWithCompassBearing.heading?.toFixed(1) || 'None'}
                            °</span>
                        </div>
                        {#if $captureLocationWithCompassBearing.headingSource}
                            <div>Data source: Compass</div>
                            <div>Accuracy: {$captureLocationWithCompassBearing.headingAccuracy?.toFixed(0) || 'N/A'}°
                            </div>
                        {:else}
                            <div>Using raw {$captureLocationWithCompassBearing.source} heading</div>
                        {/if}
                    </div>
                {/if}
            {/if}

            {#if $app.debug === 2}
                <div class="debug-section photo-counts-section">
                    <div><strong>📊 Photo Statistics:</strong></div>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <span class="stat-label">Visible Photos:</span>
                            <span class="stat-value">{$visiblePhotos.length}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Photos in Range:</span>
                            <span class="stat-value">{$photosInRange.length}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Range Area:</span>
                            <span class="stat-value">{($spatialState.range / 1000).toFixed(2)} km</span>
                        </div>
                    </div>
                </div>

                <div class="debug-section sources-section">
                    <div><strong>🔄 Sources Status:</strong></div>
                    {#each $sources as source}
                        <div class="source-status">
                            <div class="source-header">
                                <span class="source-name" style="color: {source.color}">{source.name}</span>
                                <span class="source-enabled" class:enabled={source.enabled}>
                                    {source.enabled ? '✅' : '❌'}
                                </span>
                            </div>
                            
                            {#if source.enabled}
                                <div class="source-details">
                                    <div class="source-type">Type: {source.type}</div>
                                    
                                    {#if source.type === 'stream'}
                                        {@const loadingStatus = $sourceLoadingStatus[source.id]}
                                        {#if loadingStatus}
                                            <div class="loading-status">
                                                {#if loadingStatus.isLoading}
                                                    <span class="loading-indicator">
                                                        <span class="spinner-small"></span>
                                                        Loading
                                                    </span>
                                                    {#if loadingStatus.progress}
                                                        <div class="progress-text">{loadingStatus.progress}</div>
                                                    {/if}
                                                {:else}
                                                    <span class="status-ready">Ready</span>
                                                {/if}
                                                {#if loadingStatus.error}
                                                    <div class="error-text">{loadingStatus.error}</div>
                                                {/if}
                                            </div>
                                        {/if}
                                    {:else if source.type === 'device'}
                                        <div class="device-status">
                                            {#if source.requests && source.requests.length > 0}
                                                <span class="loading-indicator">
                                                    <span class="spinner-small"></span>
                                                    Processing ({source.requests.length} requests)
                                                </span>
                                            {:else}
                                                <span class="status-ready">Ready</span>
                                            {/if}
                                        </div>
                                    {/if}
                                    
                                    {#if source.url}
                                        <div class="source-url">URL: {source.url}</div>
                                    {/if}
                                </div>
                            {/if}
                        </div>
                    {/each}
                </div>

                <div class="debug-section mapillary-section">
                    <div><strong>🗺️ Mapillary Stream Status:</strong></div>
                    <div class="cache-status-grid">
                        <div class="cache-stat">
                            <span class="cache-label">Status:</span>
                            {#if $mapillary_cache_status.is_streaming}
                                <span class="cache-streaming">
                                    <span class="spinner"></span>
                                    Streaming
                                </span>
                            {:else}
                                <span class="cache-complete">Ready</span>
                            {/if}
                        </div>
                        
                        <div class="cache-stat">
                            <span class="cache-label">Total Photos:</span>
                            <span class="cache-value">{$mapillary_cache_status.total_live_photos || 0}</span>
                        </div>
                        
                        <div class="cache-stat">
                            <span class="cache-label">Stream Phase:</span>
                            <span class="cache-value">{$mapillary_cache_status.stream_phase || 'idle'}</span>
                        </div>
                    </div>
                    
                    {#if $mapillary_cache_status.last_bounds}
                        <div class="bounds-info">
                            <div class="cache-label">Last Request Area:</div>
                            <div class="bounds-details">
                                NW: {$mapillary_cache_status.last_bounds.topLeftLat?.toFixed(4)}, {$mapillary_cache_status.last_bounds.topLeftLon?.toFixed(4)}<br>
                                SE: {$mapillary_cache_status.last_bounds.bottomRightLat?.toFixed(4)}, {$mapillary_cache_status.last_bounds.bottomRightLon?.toFixed(4)}
                            </div>
                        </div>
                    {/if}
                </div>

                <div class="debug-section photos-section">
                    <div><strong>📸 Visible Photos ({$visiblePhotos.length}):</strong></div>
                    {#if $visiblePhotos.length > 0}
                        <div class="photos-list">
                            {#each $visiblePhotos.slice(0, 10) as photo, index}
                                <div class="photo-item">
                                    <div class="photo-header">
                                        <span class="photo-index">#{index + 1}</span>
                                        <span class="photo-id">{photo.id}</span>
                                        <span class="photo-source" style="color: {photo.source?.color || '#888'}">{photo.source?.name || 'Unknown'}</span>
                                    </div>
                                    <div class="photo-location">
                                        📍 {photo.coord.lat.toFixed(6)}, {photo.coord.lng.toFixed(6)}
                                    </div>
                                    <div class="photo-details">
                                        🧭 {photo.bearing.toFixed(1)}° 
                                        {#if photo.altitude}| ⛰️ {photo.altitude.toFixed(0)}m{/if}
                                        {#if photo.captured_at}| 📅 {new Date(photo.captured_at).toLocaleDateString()}{/if}
                                    </div>
                                    {#if photo.file}
                                        <div class="photo-file">{photo.file}</div>
                                    {/if}
                                </div>
                            {/each}
                            {#if $visiblePhotos.length > 10}
                                <div class="photos-truncated">
                                    ... and {$visiblePhotos.length - 10} more photos
                                </div>
                            {/if}
                        </div>
                    {:else}
                        <div class="no-photos">No photos currently visible</div>
                    {/if}
                </div>
            {/if}

            {#if $app.debug === 3}

                <div class="debug">
                    <b>Debug Information</b><br>
                    <b>Bearing:</b>  {$visualState.bearing}<br>
                    <b>Pos.center:</b> {$spatialState.center}<br>
                    <b>Left:</b>  {$photoToLeft?.file}<br>
                    <b>Front:</b> {$photoInFront?.file}<br>
                    <b>Right:</b>  {$photoToRight?.file}<br>
                    <b>Photos in range:</b> {$photosInRange.length}<br>
                    <b>Range:</b> {$spatialState.range / 1000} km<br>
                    <b>Photos to left:</b>
                    {JSON.stringify([], null, 2)}
                    <!--            <ul>-->
                    <!--            {#each [] as photo}-->
                    <!--                <li>{photo.id},{photo.file}-->
                    <!--                    {JSON.stringify(photo.sizes, null, 2)}-->
                    <!--                </li>-->
                    <!--            {/each}-->
                    <!--            </ul>-->
                    <b>Photos to right:</b>
                    <ul>
                        {#each $photoToRight ? [$photoToRight] : [] as photo}
                            <li>{photo.id},{photo.file}
                                {JSON.stringify(photo.sizes, null, 2)}
                            </li>
                        {/each}
                    </ul>

                    <!--            <details>-->
                    <!--                <summary><b>photos_to_left:</b></summary>-->
                    <!--                <pre>{JSON.stringify($photos_to_left, null, 2)}</pre>-->
                    <!--                >-->
                    <!--            </details>-->
                    <!--            <details>-->
                    <!--                <summary><b>photos_to_right:</b></summary>-->
                    <!--                <pre>{JSON.stringify($photos_to_right, null, 2)}</pre>-->
                    <!--            </details>-->
                </div>

            {/if}

            <div class="debug-note">
                Press Ctrl+Shift+D to cycle debug (State {$app.debug}/2)<br/>
                Press Ctrl+Shift+L to move {debugPosition === 'left' ? 'right' : 'left'}
            </div>
        </div>
    </div>
{/if}

<style>
    .debug-overlay {
        position: fixed;
        top: 100px;
        right: 10px;
        background: rgba(0, 0, 0, 0.7);
        color: #0f0;
        font-family: monospace;
        font-size: 11px;
        padding: 0;
        border-radius: 5px;
        z-index: 999999;
        min-width: 280px;
        max-width: 350px;
        max-height: calc(100vh - 120px);
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.5);
        display: flex;
        flex-direction: column;
    }

    .debug-overlay.left-position {
        top: 100px;
        left: 10px;
        right: auto;
        max-height: calc(100vh - 120px);
    }

    .debug-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 4px 8px;
        background: rgba(0, 255, 0, 0.1);
        border-bottom: 1px solid #0f0;
        font-size: 10px;
    }

    .debug-header button {
        background: none;
        border: none;
        color: #0f0;
        font-size: 20px;
        cursor: pointer;
        padding: 0;
        width: 20px;
        height: 20px;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .debug-header button:hover {
        color: #0f0;
        background: rgba(0, 255, 0, 0.2);
    }

    .debug-content {
        padding: 6px;
        overflow-y: auto;
        flex: 1;
    }

    .debug-content div {
        margin: 2px 0;
        word-break: break-all;
        line-height: 1.3;
    }

    .compact-row {
        display: flex;
        gap: 8px;
        font-size: 10px;
        opacity: 0.9;
    }

    .compact-row span {
        white-space: nowrap;
    }

    .debug-content strong {
        color: #0f0;
    }

    .debug-note {
        margin-top: 4px;
        padding-top: 4px;
        border-top: 1px solid rgba(0, 255, 0, 0.3);
        font-size: 9px;
        opacity: 0.6;
        line-height: 1.2;
    }

    .debug-section {
        margin: 4px 0;
        padding: 4px 0;
        border-top: 1px solid rgba(0, 255, 0, 0.2);
    }

    .debug-section:first-of-type {
        border-top: none;
        padding-top: 0;
    }

    .error {
        color: #ff6666;
        font-style: italic;
    }

    .source-badge {
        background: rgba(0, 255, 0, 0.2);
        padding: 1px 4px;
        border-radius: 2px;
        font-size: 9px;
        margin-left: 2px;
        text-transform: uppercase;
    }

    .sensor-type {
        display: inline-block;
        padding: 2px 6px;
        border-radius: 3px;
        font-size: 10px;
        margin-left: 4px;
        font-weight: bold;
    }

    .sensor-type.tauri {
        background: rgba(76, 175, 80, 0.3);
        color: #81c784;
        border: 1px solid #4caf50;
    }

    .sensor-type.web {
        background: rgba(255, 152, 0, 0.3);
        color: #ffb74d;
        border: 1px solid #ff9800;
    }

    .sensor-type.none {
        background: rgba(244, 67, 54, 0.3);
        color: #ef5350;
        border: 1px solid #f44336;
    }

    .sensor-section {
        border-color: rgba(79, 195, 247, 0.5);
        background: rgba(3, 169, 244, 0.05);
    }


    .highlight {
        color: #4fc3f7;
        font-weight: bold;
    }

    .compass-bearing {
        border-color: #4fc3f7;
        background: rgba(79, 195, 247, 0.05);
        padding: 2px 0;
    }

    .photo-bearing {
        border-color: #81c784;
        background: rgba(129, 199, 132, 0.05);
        padding: 2px 0;
    }

    .sensor-mode-switcher {
        margin-top: 8px;
        padding-top: 8px;
        border-top: 1px solid rgba(79, 195, 247, 0.3);
    }

    .sensor-mode-select {
        margin-top: 4px;
        background: rgba(0, 0, 0, 0.5);
        color: #0f0;
        border: 1px solid #0f0;
        border-radius: 3px;
        padding: 4px 8px;
        font-size: 11px;
        font-family: monospace;
        width: 100%;
        cursor: pointer;
    }

    .sensor-mode-select:hover {
        background: rgba(0, 255, 0, 0.1);
    }

    .sensor-mode-select:focus {
        outline: 1px solid #4fc3f7;
        outline-offset: 1px;
    }

    .mapillary-section {
        border-color: rgba(255, 165, 0, 0.5);
        background: rgba(255, 165, 0, 0.05);
    }

    .cache-streaming {
        color: #ffa500;
        display: flex;
        align-items: center;
        gap: 4px;
    }

    .cache-partial {
        color: #ffff00;
    }

    .cache-complete {
        color: #00ff00;
    }

    .live-photos-count {
        font-size: 10px;
        color: #aaa;
        margin-top: 2px;
    }

    .spinner {
        width: 10px;
        height: 10px;
        border: 2px solid transparent;
        border-top: 2px solid #ffa500;
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

    /* Photo Statistics Section */
    .photo-counts-section {
        border-color: rgba(76, 175, 80, 0.5);
        background: rgba(76, 175, 80, 0.05);
    }

    .stats-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 4px;
        margin-top: 4px;
    }

    .stat-item {
        display: flex;
        justify-content: space-between;
        font-size: 10px;
        padding: 2px;
    }

    .stat-label {
        opacity: 0.8;
    }

    .stat-value {
        color: #4caf50;
        font-weight: bold;
    }

    /* Sources Section */
    .sources-section {
        border-color: rgba(33, 150, 243, 0.5);
        background: rgba(33, 150, 243, 0.05);
    }

    .source-status {
        margin: 4px 0;
        padding: 4px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 3px;
        background: rgba(0, 0, 0, 0.2);
    }

    .source-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 2px;
    }

    .source-name {
        font-weight: bold;
        font-size: 11px;
    }

    .source-enabled {
        font-size: 12px;
    }

    .source-details {
        margin-left: 8px;
        font-size: 9px;
        opacity: 0.8;
    }

    .source-type {
        margin: 2px 0;
        text-transform: uppercase;
        font-size: 8px;
        color: #888;
    }

    .source-url {
        margin: 2px 0;
        word-break: break-all;
        font-family: monospace;
        font-size: 8px;
        color: #666;
    }

    .loading-status, .device-status {
        margin: 2px 0;
    }

    .loading-indicator {
        display: flex;
        align-items: center;
        gap: 4px;
        color: #ffa500;
        font-size: 9px;
    }

    .spinner-small {
        width: 8px;
        height: 8px;
        border: 1px solid transparent;
        border-top: 1px solid #ffa500;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }

    .status-ready {
        color: #4caf50;
        font-size: 9px;
    }

    .progress-text {
        font-size: 8px;
        color: #aaa;
        margin-top: 1px;
        font-style: italic;
    }

    .error-text {
        font-size: 8px;
        color: #ff6666;
        margin-top: 1px;
    }

    /* Mapillary Cache Section */
    .cache-status-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 4px;
        margin-top: 4px;
    }

    .cache-stat {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 9px;
    }

    .cache-label {
        opacity: 0.8;
        font-size: 9px;
    }

    .cache-value {
        color: #ffa500;
        font-weight: bold;
    }

    .bounds-info {
        margin-top: 6px;
        padding-top: 4px;
        border-top: 1px solid rgba(255, 165, 0, 0.3);
    }

    .bounds-details {
        font-family: monospace;
        font-size: 8px;
        margin-top: 2px;
        color: #ccc;
        line-height: 1.2;
    }

    /* Photos Section */
    .photos-section {
        border-color: rgba(156, 39, 176, 0.5);
        background: rgba(156, 39, 176, 0.05);
    }

    .photos-list {
        margin-top: 4px;
    }

    .photo-item {
        margin: 4px 0;
        padding: 4px;
        border: 1px solid rgba(156, 39, 176, 0.3);
        border-radius: 3px;
        background: rgba(0, 0, 0, 0.2);
        font-size: 8px;
    }

    .photo-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 2px;
    }

    .photo-index {
        color: #9c27b0;
        font-weight: bold;
        font-size: 9px;
    }

    .photo-id {
        color: #e1bee7;
        font-family: monospace;
        font-size: 8px;
        flex: 1;
        text-align: center;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .photo-source {
        font-size: 7px;
        text-transform: uppercase;
        font-weight: bold;
    }

    .photo-location {
        margin: 2px 0;
        font-family: monospace;
        color: #ba68c8;
        font-size: 8px;
    }

    .photo-details {
        margin: 2px 0;
        color: #ce93d8;
        font-size: 7px;
        display: flex;
        gap: 4px;
        flex-wrap: wrap;
    }

    .photo-file {
        margin-top: 2px;
        font-family: monospace;
        font-size: 7px;
        color: #666;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .photos-truncated {
        margin-top: 4px;
        text-align: center;
        font-style: italic;
        color: #aaa;
        font-size: 8px;
    }

    .no-photos {
        margin-top: 4px;
        text-align: center;
        font-style: italic;
        color: #666;
        font-size: 9px;
    }

    @media (max-width: 600px) {
        .debug-overlay {
            top: 50px;
            right: 5px;
            left: 5px;
            min-width: auto;
        }

        .debug-overlay.left-position {
            top: 50px;
            left: 5px;
            right: 5px;
        }
    }
</style>