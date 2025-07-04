<script lang="ts">
    import { getBuildInfo } from '$lib/build-info';
    import { onMount } from 'svelte';
    import { pos, bearing } from '$lib/data.svelte';
    import { gpsLocation, gpsCoordinates, locationTracking, locationError } from '$lib/location.svelte';
    import { captureLocation } from '$lib/captureLocation';
    
    let showDebug = false;
    let buildInfo = getBuildInfo();
    let currentTime: string | undefined;
    
    onMount(() => {
        // Update time every second
        const interval = setInterval(() => {
            currentTime = new Date().toLocaleTimeString(undefined, {hour12: false});
        }, 1000);
        
        // Check for debug mode in localStorage or URL params
        const urlParams = new URLSearchParams(window.location.search);
        const debugParam = urlParams.get('debug');
        const storedDebug = localStorage.getItem('debugMode');
        
        showDebug = debugParam === 'true' || storedDebug === 'true';
        
        return () => {
            clearInterval(interval);
        };
    });
    
    export function toggleDebug() {
        showDebug = !showDebug;
        localStorage.setItem('debugMode', showDebug.toString());
    }
    
    // Keyboard shortcut to toggle debug
    function handleKeydown(e: KeyboardEvent) {
        if (e.ctrlKey && e.shiftKey && e.key === 'D') {
            toggleDebug();
        }
    }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if showDebug}
    <div class="debug-overlay">
        <div class="debug-header">
            <span>Debug Info</span>
            <button on:click={toggleDebug} aria-label="Close debug">×</button>
        </div>
        <div class="debug-content">
            <div><strong>Build Time:</strong> {buildInfo.formattedTime}</div>
            <div><strong>Current Time:</strong> {currentTime}</div>

            <div class="debug-section">
                <div><strong>Map Position:</strong></div>
                <div>Lat: {$pos.center.lat.toFixed(6)}, Lng: {$pos.center.lng.toFixed(6)}</div>
                <div>Zoom: {$pos.zoom.toFixed(1)}</div>
                <div>Bearing: {$bearing.toFixed(1)}°</div>
            </div>
            
            {#if $gpsCoordinates}
                <div class="debug-section">
                    <div><strong>GPS Location:</strong> {$locationTracking ? '📍 Active' : '⭕ Inactive'}</div>
                    <div>Lat: {$gpsCoordinates.latitude.toFixed(6)}</div>
                    <div>Lng: {$gpsCoordinates.longitude.toFixed(6)}</div>

                    {#if $gpsCoordinates.altitude !== null && $gpsCoordinates.altitude !== undefined}
                        <div>Alt: {$gpsCoordinates.altitude?.toFixed(1)}m</div>
                    {/if}

                    <div>Accuracy: ±{$gpsCoordinates.accuracy?.toFixed(1)}m</div>

                    {#if $gpsCoordinates.heading !== null && $gpsCoordinates.heading !== undefined}
                        <div>GPS Heading: {$gpsCoordinates.heading.toFixed(1)}°</div>
                    {:else}
                        <div>GPS Heading: N/A</div>
                    {/if}

                    {#if $gpsCoordinates.speed !== null && $gpsCoordinates.speed !== undefined}
                        <div>Speed: {($gpsCoordinates.speed * 3.6).toFixed(1)} km/h</div>
                    {/if}
                    {#if $locationError}
                        <div class="error">Error: {$locationError}</div>
                    {/if}
                </div>
            {:else}
                <div class="debug-section">
                    <div><strong>GPS:</strong> {$locationTracking ? 'Acquiring...' : 'Not available'}</div>
                    {#if $locationError}
                        <div class="error">Error: {$locationError}</div>
                    {/if}
                </div>
            {/if}
            
            {#if $captureLocation}
                <div class="debug-section">
                    <div><strong>Capture Location:</strong> <span class="source-badge">{$captureLocation.source.toUpperCase()}</span></div>
                    <div>Lat: {$captureLocation.latitude.toFixed(6)}</div>
                    <div>Lng: {$captureLocation.longitude.toFixed(6)}</div>
                    {#if $captureLocation.altitude !== undefined}
                        <div>Alt: {$captureLocation.altitude.toFixed(1)}m</div>
                    {/if}
                    <div>Heading: {$captureLocation.heading.toFixed(1)}°</div>
                    <div>Accuracy: ±{$captureLocation.accuracy.toFixed(1)}m</div>
                    <div class="timestamp">Updated: {new Date($captureLocation.timestamp).toLocaleTimeString()}</div>
                </div>
            {:else}
                <div class="debug-section">
                    <div><strong>Capture Location:</strong> Not initialized</div>
                </div>
            {/if}
            
            <div class="debug-note">Press Ctrl+Shift+D to toggle</div>
        </div>
    </div>
{/if}

<style>
    .debug-overlay {
        position: fixed;
        top: 10px;
        right: 10px;
        background: rgba(0, 0, 0, 0.9);
        color: #0f0;
        font-family: monospace;
        font-size: 12px;
        padding: 0;
        border-radius: 5px;
        z-index: 10000;
        min-width: 300px;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.5);
    }
    
    .debug-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 12px;
        background: rgba(0, 255, 0, 0.1);
        border-bottom: 1px solid #0f0;
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
        padding: 12px;
    }
    
    .debug-content div {
        margin: 4px 0;
        word-break: break-all;
    }
    
    .debug-content strong {
        color: #0f0;
    }
    
    .debug-note {
        margin-top: 8px;
        padding-top: 8px;
        border-top: 1px solid rgba(0, 255, 0, 0.3);
        font-size: 11px;
        opacity: 0.7;
    }
    
    .debug-section {
        margin: 8px 0;
        padding: 8px 0;
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
    

    .debug-toggle-button {
        position: fixed;
        bottom: 10px;
        right: 10px;
        background: rgba(0, 0, 0, 0.7);
        border: 1px solid #333;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        z-index: 9999;
        font-size: 20px;
        transition: all 0.2s;
    }
    
    .debug-toggle-button:hover {
        background: rgba(0, 0, 0, 0.9);
        border-color: #666;
        transform: scale(1.1);
    }
    
    @media (max-width: 600px) {
        .debug-overlay {
            top: 5px;
            right: 5px;
            left: 5px;
            min-width: auto;
        }
    }
</style>