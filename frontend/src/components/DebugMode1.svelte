<script lang="ts">
    import {getBuildInfo} from '$lib/build-info';
    import {onMount} from 'svelte';
    import {spatialState, visualState} from '$lib/mapState';
    import {gpsCoordinates, locationError, locationTracking} from '$lib/location.svelte';
    import {captureLocation, captureLocationWithCompassBearing} from '$lib/captureLocation';
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
    let actualSensorSource: string | null = null;
    let isTauriAndroid = false;

    onMount(() => {
        // Detect sensor type
        isTauriAndroid = TAURI && /Android/i.test(navigator.userAgent);

        // Subscribe to compass data to detect which sensor is active
        const unsubscribe = compassData.subscribe(data => {
            if (data && isTauriAndroid) {
                sensorType = 'tauri-rotation-vector';
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

        // Fetch backend status
        fetchBackendStatus();

        return () => {
            clearInterval(interval);
            unsubscribe();
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
    <div>Zoom: {$spatialState.zoom?.toFixed(1)} | Bearing: {$visualState.bearing?.toFixed(0)}°</div>
</div>

{#if $gpsCoordinates}
    <div class="debug-section">
        <div><strong>GPS Location {$locationTracking ? '📍 Active' : '⭕ Inactive'}:</strong></div>
        <div>Position: {$gpsCoordinates.latitude?.toFixed(4)}
            , {$gpsCoordinates.longitude?.toFixed(4)}</div>
        <div>Accuracy: ±{$gpsCoordinates.accuracy?.toFixed(0)}m
            {#if $gpsCoordinates.altitude !== null && $gpsCoordinates.altitude !== undefined}
                | Altitude: {$gpsCoordinates.altitude?.toFixed(0)}m
            {/if}
        </div>
        <div>GPS Heading: {$gpsCoordinates.heading?.toFixed(0) || 'No movement'}°
            {#if $gpsCoordinates.speed !== null && $gpsCoordinates.speed !== undefined}
                | Speed: {($gpsCoordinates.speed * 3.6)?.toFixed(1)}km/h
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
        <div>Position: {$captureLocation.latitude?.toFixed(4)}
            , {$captureLocation.longitude?.toFixed(4)}</div>
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
        <div>Heading: <span class="highlight">{$currentHeading.heading?.toFixed(1)}°</span></div>
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