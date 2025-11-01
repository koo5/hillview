<script lang="ts">
    import {getBuildInfo} from '$lib/build-info';
    import {onMount} from 'svelte';
    import {spatialState, bearingState} from '$lib/mapState';
	import {gpsLocation, locationError, locationTracking} from '$lib/location.svelte';

    import {
        compassAvailable,
        compassData,
        currentCompassHeading,
        currentSensorMode,
        deviceOrientation,
        setCompassMode
    } from '$lib/compass.svelte';
    import {invoke} from '@tauri-apps/api/core';
    import {SensorMode, TAURI_MOBILE} from '$lib/tauri';
    import {backendUrl} from "$lib/config";

    // Build and time info
    let buildInfo = getBuildInfo();
    let currentTime: string | undefined;
    let buildCommitHash: string | undefined;
    let buildBranch: string | undefined;
    let buildTimestamp: string | undefined;

    // Backend status
    let backendStatus: any = null;
    let backendError: string | null = null;

    // Sensor detection
    let sensorType: 'tauri-rotation-vector' | 'device-orientation' | 'none' = 'none';

    onMount(() => {

        // Update time every second
        const interval = setInterval(() => {
            currentTime = new Date().toLocaleTimeString(undefined, {hour12: false});
        }, 1000);

        // Fetch build information from Tauri commands
        invoke<string>('get_build_commit_hash').then((hash) => {
            buildCommitHash = hash;
        }).catch((err) => {
            console.log('🢄Failed to get build commit hash:', err.message);
        });

        invoke<string>('get_build_branch').then((branch) => {
            buildBranch = branch;
        }).catch((err) => {
            console.log('🢄Failed to get build branch:', err.message);
        });

        invoke<string>('get_build_ts').then((ts) => {
            buildTimestamp = ts;
        }).catch((err) => {
            console.log('🢄Failed to get build timestamp:', err.message);
        });

        // Fetch backend status
        fetchBackendStatus();

        return () => {
            clearInterval(interval);
        };
    });

    async function fetchBackendStatus() {
        try {
            const response = await fetch(`${backendUrl}/debug`);
            if (response.ok) {
                backendStatus = await response.json();
                backendError = null;
            } else {
                backendError = `HTTP ${response.status}: ${response.statusText}`;
                backendStatus = null;
            }
        } catch (error) {
            backendError = error instanceof Error ? error.message : 'Unknown error';
            backendStatus = null;
        }
    }
</script>

<div class="compact-row">
    <span><strong>Build:</strong> {buildInfo.formattedTime}</span>
    <span><strong>Now:</strong> {currentTime}</span>
</div>

{#if buildCommitHash || buildBranch}
    <div class="compact-row">
        <span>{buildBranch || 'Loading...'} @ {buildCommitHash?.slice(0, 7) || '...'}</span>
    </div>
{/if}

<div class="debug-section backend-section">
    <div><strong>Backend:</strong> {backendUrl}</div>
    {#if backendStatus}
        <div class="backend-status success">✅ Connected</div>
        {#if backendStatus.status}
            <div class="backend-info">Status: {backendStatus.status}</div>
        {/if}
        {#if backendStatus.version}
            <div class="backend-info">Version: {backendStatus.version}</div>
        {/if}
        {#if backendStatus.uptime}
            <div class="backend-info">Uptime: {backendStatus.uptime}</div>
        {/if}
    {:else if backendError}
        <div class="backend-status error">❌ {backendError}</div>
    {:else}
        <div class="backend-status loading">🔄 Checking...</div>
    {/if}
</div>

<div class="debug-section">
    <div><strong>Map View:</strong></div>
    <div>Center: {$spatialState.center.lat?.toFixed(4)}, {$spatialState.center.lng?.toFixed(4)}</div>
    <div>Zoom: {$spatialState.zoom?.toFixed(1)} | Bearing: {$bearingState.bearing?.toFixed(0)}°</div>
    <div>Area: {JSON.stringify($spatialState.bounds, null, 2)}</div>
</div>

{#if $gpsLocation}
    <div class="debug-section">
        <div><strong>GPS Location {$locationTracking ? '📍 Active' : '⭕ Inactive'}:</strong></div>

        <pre>{JSON.stringify($gpsLocation, null, 2)}</pre>

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


<div class="debug-section sensor-section">

    {#if TAURI_MOBILE && $compassAvailable}
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

    {#if $compassData}
        <div><strong>Compass Bearing:</strong> {$compassData.magneticHeading?.toFixed(1) || 'N/A'}°
        </div>
        <div style="font-size: 10px; opacity: 0.8">True
            bearing: {$compassData.trueHeading?.toFixed(1) || 'N/A'}° | Accuracy:
            ±{$compassData.headingAccuracy?.toFixed(0) || 'N/A'}°
        </div>
        {#if $deviceOrientation}
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

{#if $currentCompassHeading.heading !== null}
    <div class="debug-section compass-bearing">
        <div><strong>🎯 Compass Bearing:</strong></div>
        <div>Heading: <span class="highlight">{$currentCompassHeading.heading?.toFixed(1)}°</span></div>
        <div>Source: {$currentCompassHeading.source}</div>
        <div>Accuracy: {$currentCompassHeading.accuracy?.toFixed(0) || 'N/A'}°</div>
    </div>
{/if}


<style>
    .compact-row {
        display: flex;
        gap: 8px;
        font-size: 10px;
        opacity: 0.9;
    }

    .compact-row span {
        white-space: nowrap;
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

    /* Backend Status Section */
    .backend-section {
        border-color: rgba(96, 125, 139, 0.5);
        background: rgba(96, 125, 139, 0.05);
    }

    .backend-status {
        font-size: 10px;
        margin: 2px 0;
        padding: 2px 4px;
        border-radius: 3px;
        font-weight: bold;
    }

    .backend-status.success {
        color: #4caf50;
        background: rgba(76, 175, 80, 0.1);
    }

    .backend-status.error {
        color: #f44336;
        background: rgba(244, 67, 54, 0.1);
    }

    .backend-status.loading {
        color: #ff9800;
        background: rgba(255, 152, 0, 0.1);
    }

    .backend-info {
        font-size: 9px;
        margin: 1px 0;
        color: #bbb;
        margin-left: 8px;
    }
</style>