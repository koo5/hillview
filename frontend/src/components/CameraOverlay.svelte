<script lang="ts">
    import {cameraOverlayOpacity} from "$lib/data.svelte";
	import {get} from "svelte/store";
    import {sensorAccuracy, compassLag} from "$lib/compass.svelte";
    import {bearingState} from "$lib/mapState";

    export let locationData: {
        latitude?: number;
        longitude?: number;
        altitude?: number | null;
        accuracy?: number;
        heading?: number | null;
    } | null = null;

    export let locationError: string | null = null;
    export let locationReady = false;

    // Convert Android sensor accuracy integer to human-readable string
    function accuracyToString(accuracy: number): string {
        switch (accuracy) {
            case 3: return "HIGH";
            case 2: return "MEDIUM";
            case 1: return "LOW";
            case 0: return "UNRELIABLE";
            default: return "UNKNOWN";
        }
    }

    // Get lag color class based on lag value (100ms = good, 400ms = bad)
    function getLagColorClass(lag: number): string {
        if (lag <= 200) return "lag-good";
        if (lag <= 400) return "lag-medium";
        if (lag <= 600) return "lag-poor";
        return "lag-bad";
    }

    // Toggle overlay opacity through 6 levels: 0 (fully transparent) to 5 (most opaque)
    function toggleOverlayOpacity() {
		let next = get(cameraOverlayOpacity) + 2;
		if (next > 5) next = 0;
        cameraOverlayOpacity.set(next);
    }
</script>

<div
    class="location-overlay {locationReady ? 'ready' : ''} {locationError ? 'error' : ''}"
    class:opacity-0={$cameraOverlayOpacity === 0}
    class:opacity-1={$cameraOverlayOpacity === 1}
    class:opacity-2={$cameraOverlayOpacity === 2}
    class:opacity-3={$cameraOverlayOpacity === 3}
    class:opacity-4={$cameraOverlayOpacity === 4}
    class:opacity-5={$cameraOverlayOpacity === 5}
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

    <!-- Sensor Accuracy Information -->
    {#if $sensorAccuracy.timestamp > 0}
        <div class="accuracy-section">
            <div class="location-row accuracy-row">
                <span class="icon">⚙️</span>
                <span class="accuracy-title">Accuracy</span>
            </div>
            <div class="accuracy-details">
                {#if $sensorAccuracy.magnetometer}
                    <div class="location-row accuracy-item">
                        <span class="icon">🧭</span>
                        <span class="sensor-name">Mag:</span>
                        <span class="accuracy-value accuracy-{$sensorAccuracy.magnetometer.toLowerCase()}">{$sensorAccuracy.magnetometer}</span>
                    </div>
                {/if}
                {#if $sensorAccuracy.accelerometer}
                    <div class="location-row accuracy-item">
                        <span class="icon">📈</span>
                        <span class="sensor-name">Acc:</span>
                        <span class="accuracy-value accuracy-{$sensorAccuracy.accelerometer.toLowerCase()}">{$sensorAccuracy.accelerometer}</span>
                    </div>
                {/if}
                {#if $sensorAccuracy.gyroscope}
                    <div class="location-row accuracy-item">
                        <span class="icon">🔄</span>
                        <span class="sensor-name">Gyro:</span>
                        <span class="accuracy-value accuracy-{$sensorAccuracy.gyroscope.toLowerCase()}">{$sensorAccuracy.gyroscope}</span>
                    </div>
                {/if}
            </div>
        </div>
    {/if}

    <!-- Heading Accuracy Information -->
    {#if $bearingState.accuracy !== null && $bearingState.accuracy !== undefined}
        <div class="location-row">
            <span class="icon">🧭</span>
            <span>Compass: <span class="accuracy-value accuracy-{accuracyToString($bearingState.accuracy).toLowerCase()}">{accuracyToString($bearingState.accuracy)}</span></span>
        </div>
    {/if}

    <!-- Compass Lag Information -->
    {#if $compassLag !== null}
        <div class="location-row">
            <span class="icon">⏱️</span>
            <span>Lag: <span class="accuracy-value {getLagColorClass($compassLag)}">{$compassLag}ms</span></span>
        </div>
    {/if}
</div>

<style>
    .location-overlay {
        position: absolute;
        top: 80px;
        left: 0rem;
        padding: 0rem;
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
        background: rgba(255, 255, 255, 0.15);
        border: 1px solid rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(1px);
    }

    /* Opacity level 2: Light */
    .location-overlay.opacity-2 {
        background: rgba(255, 255, 255, 0.31);
        border: 1px solid rgba(255, 255, 255, 0.15);
        backdrop-filter: blur(2px);
    }

    /* Opacity level 3: Medium (default) */
    .location-overlay.opacity-3 {
        background: rgba(255, 255, 255, 0.45);
        border: 1px solid rgba(255, 255, 255, 0.2);
        backdrop-filter: blur(3px);
    }

    /* Opacity level 4: Strong */
    .location-overlay.opacity-4 {
        background: rgba(255, 255, 255, 0.62);
        border: 1px solid rgba(255, 255, 255, 0.3);
        backdrop-filter: blur(4px);
    }

    /* Opacity level 5: Most opaque */
    .location-overlay.opacity-5 {
        background: rgba(255, 255, 255, 0.83);
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

    /* Accuracy section styling */
    .accuracy-section {
        margin-top: 0.5rem;
        padding-top: 0.25rem;
        border-top: 1px solid rgba(255, 255, 255, 0.2);
    }

    .accuracy-row {
        margin-bottom: 0.25rem;
    }

    .accuracy-title {
        font-weight: 500;
        font-size: 0.8rem;
    }

    .accuracy-details {
        margin-left: 0.5rem;
    }

    .accuracy-item {
        margin: 0.1rem 0;
        font-size: 0.75rem;
    }

    .sensor-name {
        min-width: 2.5rem;
        font-weight: 400;
    }

    .accuracy-value {
        font-weight: 500;
        padding: 0.1rem 0.3rem;
        border-radius: 3px;
        font-size: 0.7rem;
        margin-left: 0.2rem;
    }

    /* Accuracy level styling */
    .accuracy-high {
        background: rgba(76, 175, 80, 0.7);
        color: white;
    }

    .accuracy-medium {
        background: rgba(255, 193, 7, 0.7);
        color: black;
    }

    .accuracy-low {
        background: rgba(255, 152, 0, 0.7);
        color: white;
    }

    .accuracy-unreliable {
        background: rgba(244, 67, 54, 0.7);
        color: white;
    }

    .accuracy-unknown {
        background: rgba(158, 158, 158, 0.7);
        color: white;
    }

    /* Lag level styling */
    .lag-good {
        background: rgba(76, 175, 80, 0.7);
        color: white;
    }

    .lag-medium {
        background: rgba(255, 193, 7, 0.7);
        color: black;
    }

    .lag-poor {
        background: rgba(255, 152, 0, 0.7);
        color: white;
    }

    .lag-bad {
        background: rgba(244, 67, 54, 0.7);
        color: white;
    }
</style>
