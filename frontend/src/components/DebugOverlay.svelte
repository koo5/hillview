<script lang="ts">
    import {getBuildInfo} from '$lib/build-info';
    import {onMount} from 'svelte';
    import {bearing, pos} from '$lib/data.svelte';
    import {gpsCoordinates, locationError, locationTracking} from '$lib/location.svelte';
    import {captureLocation, captureLocationWithCompassBearing} from '$lib/captureLocation';
    import {compassData, deviceOrientation, compassAvailable, compassPermission, compassHeading} from '$lib/compass.svelte';
    import {invoke} from '@tauri-apps/api/core';

    let showDebug = false;
    let buildInfo = getBuildInfo();
    let currentTime: string | undefined;
    let buildCommitHash: string | undefined;
    let buildBranch: string | undefined;
    let buildTimestamp: string | undefined;
    let debugPosition: 'left' | 'right' = 'left'; // Default to left to avoid photo thumbnails

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
        // Ctrl+Shift+L to toggle position
        if (e.ctrlKey && e.shiftKey && e.key === 'L' && showDebug) {
            debugPosition = debugPosition === 'left' ? 'right' : 'left';
            localStorage.setItem('debugPosition', debugPosition);
        }
    }
</script>

<svelte:window on:keydown={handleKeydown}/>

{#if showDebug}
    <div class="debug-overlay" class:left-position={debugPosition === 'left'}>
        <div class="debug-header">
            <span>Debug Info</span>
            <button on:click={toggleDebug} aria-label="Close debug">×</button>
        </div>
        <div class="debug-content">
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
                <div>Center: {$pos.center.lat.toFixed(4)}, {$pos.center.lng.toFixed(4)}</div>
                <div>Zoom: {$pos.zoom.toFixed(1)} | Bearing: {$bearing.toFixed(0)}°</div>
            </div>

            {#if $gpsCoordinates}
                <div class="debug-section">
                    <div><strong>GPS Location {$locationTracking ? '📍 Active' : '⭕ Inactive'}:</strong></div>
                    <div>Position: {$gpsCoordinates.latitude.toFixed(4)}, {$gpsCoordinates.longitude.toFixed(4)}</div>
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
                    <div><strong>GPS Location:</strong> {$locationTracking ? 'Waiting for signal...' : 'Disabled'}</div>
                    {#if $locationError}
                        <div class="error">Error: {$locationError}</div>
                    {/if}
                </div>
            {/if}

            {#if $captureLocation}
                <div class="debug-section">
                    <div><strong>Capture Location (Source: <span class="source-badge">{$captureLocation.source}</span>):</strong></div>
                    <div>Position: {$captureLocation.latitude.toFixed(4)}, {$captureLocation.longitude.toFixed(4)}</div>
                    <div>Raw Heading: {$captureLocation?.heading?.toFixed(1) || 'None'}° | Accuracy: ±{$captureLocation?.accuracy?.toFixed(0)}m
                        {#if $captureLocation.altitude !== undefined}
                            | Alt: {$captureLocation?.altitude?.toFixed(0)}m
                        {/if}
                    </div>
                    <div style="font-size: 9px; opacity: 0.7">Updated: {new Date($captureLocation.timestamp || 0).toLocaleTimeString()}</div>
                </div>
            {/if}

            <div class="debug-section">
                <div><strong>Compass/Magnetometer:</strong> {$compassAvailable ? '✓ Available' : '✗ Not Available'}</div>
                {#if $compassAvailable}
                    <div>Permission: {$compassPermission || 'Unknown'}</div>
                {/if}
                {#if $compassData}
                    <div>Magnetic Heading: {$compassData.magneticHeading?.toFixed(0) || 'N/A'}°</div>
                    <div>True Heading: {$compassData.trueHeading?.toFixed(0) || 'N/A'}° | Accuracy: ±{$compassData.headingAccuracy?.toFixed(0) || 'N/A'}°</div>
                {:else if $compassAvailable}
                    <div>No compass data received</div>
                {/if}
            </div>

            {#if $deviceOrientation}
                <div class="debug-section">
                    <div><strong>Device Orientation (Gyroscope):</strong></div>
                    <div>Alpha (Z-axis): {$deviceOrientation.alpha?.toFixed(0) || 'N/A'}° | Beta (X-axis): {$deviceOrientation.beta?.toFixed(0) || 'N/A'}°</div>
                    <div>Gamma (Y-axis): {$deviceOrientation.gamma?.toFixed(0) || 'N/A'}° | Type: {$deviceOrientation.absolute ? 'Absolute' : 'Relative'}</div>
                </div>
            {/if}

            {#if $compassHeading}
                <div class="debug-section compass-bearing">
                    <div><strong>🎯 Compass Bearing:</strong></div>
                    <div>Heading: <span class="highlight">{$compassHeading.heading.toFixed(1)}°</span></div>
                    <div>Source: {$compassHeading.source}</div>
                    <div>Accuracy: {$compassHeading.accuracy?.toFixed(0) || 'N/A'}°</div>
                </div>
            {/if}

            {#if $captureLocationWithCompassBearing}
                <div class="debug-section photo-bearing">
                    <div><strong>📸 Photo Capture Data (Final):</strong></div>
                    <div>Bearing to be saved: <span class="highlight">{$captureLocationWithCompassBearing.heading?.toFixed(1) || 'None'}°</span></div>
                    {#if $captureLocationWithCompassBearing.headingSource}
                        <div>Data source: Compass</div>
                        <div>Accuracy: {$captureLocationWithCompassBearing.headingAccuracy?.toFixed(0) || 'N/A'}°</div>
                    {:else}
                        <div>Using raw {$captureLocationWithCompassBearing.source} heading</div>
                    {/if}
                </div>
            {/if}

            <div class="debug-note">
                Press Ctrl+Shift+D to toggle<br/>
                Press Ctrl+Shift+L to move {debugPosition === 'left' ? 'right' : 'left'}
            </div>
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
        font-size: 11px;
        padding: 0;
        border-radius: 5px;
        z-index: 999999;
        min-width: 280px;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.5);
    }
    
    .debug-overlay.left-position {
        left: 10px;
        right: auto;
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

    @media (max-width: 600px) {
        .debug-overlay {
            top: 5px;
            right: 5px;
            left: 5px;
            min-width: auto;
        }
        
        .debug-overlay.left-position {
            left: 5px;
            right: 5px;
        }
    }
</style>