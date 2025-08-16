<script lang="ts">
    import {onMount} from 'svelte';
    import {photoInFront, photosInRange, photoToLeft, photoToRight, spatialState, visualState, visiblePhotos} from '$lib/mapState';
    import {app, mapillary_cache_status, sources, sourceLoadingStatus, toggleDebug, closeDebug} from '$lib/data.svelte';
    import {captureQueue, type QueueStats} from '$lib/captureQueue';
    
    // Access the stats store properly
    $: queueStats = captureQueue.stats;
    import {devicePhotos, photoCaptureSettings} from '$lib/stores';
    import {invoke} from '@tauri-apps/api/core';
    import DebugMode1 from './DebugMode1.svelte';

    let debugPosition: 'left' | 'right' = 'left'; // Default to left to avoid photo thumbnails

    onMount(() => {
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
    });

</script>

<svelte:window/>

{#if $app.debug > 0}
    <div class="debug-overlay" class:left-position={debugPosition === 'left'}>
        <div class="debug-header">
            <span>Debug Info</span>
            <button on:click={closeDebug} aria-label="Close debug">×</button>
        </div>
        <div class="debug-content">
            {#if $app.debug === 1}
                <DebugMode1 />
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
                            <span class="stat-value">{($spatialState.range / 1000)?.toFixed(2)} km</span>
                        </div>
                    </div>
                </div>

                <div class="debug-section sources-section">
                    <div><strong>🔄 Sources Status:</strong></div>
                    {#each $sources as source}
                        <div class="source-status">
                            <div class="source-header">
                                <div class="source-name-container">
                                    <span class="source-color-indicator" style="background-color: {source.color}"></span>
                                    <span class="source-name">{source.name}</span>
                                </div>
                                <span class="source-enabled" class:enabled={source.enabled}>
                                    {source.enabled ? '●' : '○'}
                                </span>
                            </div>
                            
                            {#if source.enabled}
                                <div class="source-details">
                                    <div class="source-type">Type: {source.type}</div>
                                    {#if source.subtype}
                                        <div class="source-url">Subtype: {source.subtype}</div>
                                    {/if}

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
                                        📍 {photo.coord.lat?.toFixed(6)}, {photo.coord.lng?.toFixed(6)}
                                    </div>
                                    <div class="photo-details">
                                        🧭 {photo.bearing?.toFixed(1)}° 
                                        {#if photo.altitude}| ⛰️ {photo.altitude?.toFixed(0)}m{/if}
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

            {#if $app.debug === 4}
                <div class="debug-section capture-system-section">
                    <div><strong>📸 Capture System Status:</strong></div>
                    
                    <!-- Capture Queue Status -->
                    <div class="capture-subsection">
                        <div class="subsection-header">🔄 Queue Status:</div>
                        <div class="capture-stats-grid">
                            <div class="capture-stat">
                                <span class="capture-label">Queue Size:</span>
                                <span class="capture-value">{$queueStats.size}</span>
                            </div>
                            <div class="capture-stat">
                                <span class="capture-label">Processing:</span>
                                <span class="capture-value" class:processing={$queueStats.processing}>
                                    {$queueStats.processing ? '⚡ Active' : '💤 Idle'}
                                </span>
                            </div>
                            <div class="capture-stat">
                                <span class="capture-label">Total Captured:</span>
                                <span class="capture-value">{$queueStats.totalCaptured}</span>
                            </div>
                            <div class="capture-stat">
                                <span class="capture-label">Mode Breakdown:</span>
                                <span class="capture-value">
                                    🐌 {$queueStats.slowModeCount} | ⚡ {$queueStats.fastModeCount}
                                </span>
                            </div>
                        </div>
                    </div>

                    <!-- Capture Settings -->
                    <div class="capture-subsection">
                        <div class="subsection-header">⚙️ Settings:</div>
                        <div class="capture-settings">
                            <div class="setting-item">
                                <span class="setting-label">Hide from Gallery:</span>
                                <span class="setting-value">{$photoCaptureSettings.hideFromGallery ? '✅ Yes' : '❌ No'}</span>
                            </div>
                        </div>
                    </div>

                    <!-- Last Captured Photo -->
                    {#if $devicePhotos.length > 0}
                        {@const lastPhoto = $devicePhotos[$devicePhotos.length - 1]}
                        <div class="capture-subsection">
                            <div class="subsection-header">📷 Last Captured Photo:</div>
                            <div class="last-photo-info">
                                <div class="photo-basic-info">
                                    <div class="photo-filename">📁 {lastPhoto.filename}</div>
                                    <div class="photo-timestamp">🕒 {new Date(lastPhoto.timestamp).toLocaleString()}</div>
                                    <div class="photo-id">🆔 {lastPhoto.id}</div>
                                </div>
                                
                                <div class="photo-location-info">
                                    <div class="photo-coordinates">
                                        📍 {lastPhoto.latitude?.toFixed(6)}, {lastPhoto.longitude?.toFixed(6)}
                                    </div>
                                    {#if lastPhoto.bearing !== null && lastPhoto.bearing !== undefined}
                                        <div class="photo-bearing">🧭 {lastPhoto.bearing?.toFixed(1)}°</div>
                                    {/if}
                                    {#if lastPhoto.altitude !== null && lastPhoto.altitude !== undefined}
                                        <div class="photo-altitude">⛰️ {lastPhoto.altitude?.toFixed(1)}m</div>
                                    {/if}
                                    <div class="photo-accuracy">🎯 ±{lastPhoto.accuracy?.toFixed(0)}m</div>
                                </div>

                                <div class="photo-technical-info">
                                    <div class="photo-dimensions">
                                        📐 {lastPhoto.width}×{lastPhoto.height}px
                                    </div>
                                    <div class="photo-filesize">
                                        💾 {(lastPhoto.file_size / 1024 / 1024)?.toFixed(2)}MB
                                    </div>
                                    <div class="photo-path">
                                        📂 {lastPhoto.path}
                                    </div>
                                </div>
                            </div>
                        </div>
                    {:else}
                        <div class="capture-subsection">
                            <div class="subsection-header">📷 Last Captured Photo:</div>
                            <div class="no-photos-captured">No photos captured yet</div>
                        </div>
                    {/if}

                    <!-- Camera Activity Status -->
                    <div class="capture-subsection">
                        <div class="subsection-header">📹 Camera Status:</div>
                        <div class="camera-status">
                            <div class="camera-activity">
                                Activity: <span class="activity-indicator">{$app.activity === 'capture' ? '🔴 Active' : '⚫ Inactive'}</span>
                            </div>
                            {#if $app.activity === 'capture'}
                                <div class="camera-mode">Mode: Photo Capture</div>
                            {/if}
                        </div>
                    </div>
                </div>
            {/if}

            <div class="debug-note">
                Press 'd' to cycle debug (State {$app.debug}/4)<br/>
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


    .cache-complete {
        color: #00ff00;
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

    .source-name-container {
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .source-color-indicator {
        width: 10px;
        height: 10px;
        border-radius: 2px;
        border: 1px solid rgba(255, 255, 255, 0.3);
        flex-shrink: 0;
    }

    .source-name {
        font-weight: bold;
        font-size: 11px;
        color: #fff;
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

    /* Capture System Section */
    .capture-system-section {
        border-color: rgba(255, 193, 7, 0.5);
        background: rgba(255, 193, 7, 0.05);
    }

    .capture-subsection {
        margin: 6px 0;
        padding: 4px 0;
        border-top: 1px solid rgba(255, 193, 7, 0.2);
    }

    .capture-subsection:first-child {
        border-top: none;
    }

    .subsection-header {
        font-weight: bold;
        color: #ffc107;
        font-size: 10px;
        margin-bottom: 4px;
    }

    .capture-stats-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 4px;
        margin-top: 4px;
    }

    .capture-stat {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 9px;
        padding: 2px;
    }

    .capture-label {
        opacity: 0.8;
        color: #fff3cd;
    }

    .capture-value {
        color: #ffc107;
        font-weight: bold;
    }

    .capture-value.processing {
        color: #28a745;
        animation: pulse-green 1s ease-in-out infinite;
    }

    @keyframes pulse-green {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }

    .capture-settings {
        margin-top: 4px;
    }

    .setting-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 9px;
        padding: 2px;
    }

    .setting-label {
        opacity: 0.8;
        color: #fff3cd;
    }

    .setting-value {
        color: #ffc107;
        font-weight: bold;
    }

    .last-photo-info {
        margin-top: 4px;
        padding: 4px;
        border: 1px solid rgba(255, 193, 7, 0.3);
        border-radius: 3px;
        background: rgba(0, 0, 0, 0.2);
    }

    .photo-basic-info, .photo-location-info, .photo-technical-info {
        margin: 4px 0;
        padding: 2px 0;
    }

    .photo-basic-info {
        border-bottom: 1px solid rgba(255, 193, 7, 0.2);
        padding-bottom: 4px;
    }

    .photo-location-info {
        border-bottom: 1px solid rgba(255, 193, 7, 0.2);
        padding-bottom: 4px;
    }

    .photo-filename, .photo-timestamp, .photo-id,
    .photo-coordinates, .photo-bearing, .photo-altitude, .photo-accuracy,
    .photo-dimensions, .photo-filesize, .photo-path {
        font-size: 8px;
        margin: 1px 0;
        color: #fff3cd;
    }

    .photo-path {
        word-break: break-all;
        font-family: monospace;
        color: #aaa;
    }

    .no-photos-captured {
        font-size: 9px;
        color: #888;
        font-style: italic;
        text-align: center;
        padding: 8px;
    }

    .camera-status {
        margin-top: 4px;
    }

    .camera-activity, .camera-mode {
        font-size: 9px;
        margin: 2px 0;
        color: #fff3cd;
    }

    .activity-indicator {
        font-weight: bold;
        color: #ffc107;
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