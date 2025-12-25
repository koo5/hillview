<script lang="ts">
    import { onDestroy } from 'svelte';
    import { bearingState } from '$lib/mapState';
    import { sensorAccuracy, needsCalibration } from '$lib/compass.svelte.js';
    import { showCalibrationView } from '$lib/data.svelte.js';
    import { ArrowRight } from 'lucide-svelte';
    import CompassButtonInner from './CompassButtonInner.svelte';

    // Track how long accuracy has been good for auto-dismiss
    let goodAccuracyStart: number | null = null;
    let autoDismissTimeout: ReturnType<typeof setTimeout> | null = null;
    const AUTO_DISMISS_DELAY = 1500; // Wait 1.5 seconds of good accuracy before dismissing

    // Convert numeric accuracy to string
    function accuracyToString(accuracy: number | null | undefined): string {
        if (accuracy === null || accuracy === undefined) return "UNKNOWN";
        switch (accuracy) {
            case 3: return "HIGH";
            case 2: return "MEDIUM";
            case 1: return "LOW";
            case 0: return "UNRELIABLE";
            default: return "UNKNOWN";
        }
    }

    // Get accuracy color class
    function getAccuracyClass(accuracy: number | null | undefined): string {
        if (accuracy === null || accuracy === undefined) return "unknown";
        switch (accuracy) {
            case 3: return "high";
            case 2: return "medium";
            case 1: return "low";
            case 0: return "unreliable";
            default: return "unknown";
        }
    }

    // Watch needsCalibration for auto-dismiss
    $: {
        if (!$needsCalibration) {
            // Calibration no longer needed - schedule auto-dismiss
            if (goodAccuracyStart === null) {
                goodAccuracyStart = Date.now();
                if (autoDismissTimeout) clearTimeout(autoDismissTimeout);
                autoDismissTimeout = setTimeout(() => {
                    if (!$needsCalibration) {
                        showCalibrationView.set(false);
                    }
                }, AUTO_DISMISS_DELAY);
            }
        } else {
            // Still needs calibration, reset timer
            goodAccuracyStart = null;
            if (autoDismissTimeout) {
                clearTimeout(autoDismissTimeout);
                autoDismissTimeout = null;
            }
        }
    }

    function handleClose() {
        showCalibrationView.set(false);
    }

    onDestroy(() => {
        if (autoDismissTimeout) {
            clearTimeout(autoDismissTimeout);
        }
    });
</script>

<div class="calibration-overlay" data-testid="compass-calibration-overlay">
    <div class="calibration-content">
        <div class="calibration-inner">
            <button class="close-button" on:click={handleClose} aria-label="Close calibration" data-testid="calibration-close-btn">
                &times;
            </button>

            <h4 class="calibration-title">Calibrate Compass</h4>

        <!-- Figure-8 Animation and instruction on same line -->
        <div class="instruction-row">
            <div class="figure8-animation">
                <svg viewBox="0 0 100 60" class="figure8-svg">
                    <path
                        d="M50 30 C50 10, 80 10, 80 30 C80 50, 50 50, 50 30 C50 10, 20 10, 20 30 C20 50, 50 50, 50 30"
                        fill="none"
                        stroke-width="2"
                    />
                    <circle class="moving-dot" r="4">
                        <animateMotion
                            dur="3s"
                            repeatCount="indefinite"
                            path="M50 30 C50 10, 80 10, 80 30 C80 50, 50 50, 50 30 C50 10, 20 10, 20 30 C20 50, 50 50, 50 30"
                        />
                    </circle>
                </svg>
            </div>
            <p class="calibration-instruction">
                Move your phone in a <strong>figure-8 pattern</strong> several times
            </p>
        </div>

        <!-- Real-time Accuracy Display -->
        <div class="accuracy-display">
            <span class="accuracy-label">Compass Accuracy:</span>
            <span class="accuracy-value accuracy-{getAccuracyClass($bearingState.accuracy)}">
                {accuracyToString($bearingState.accuracy)}
            </span>
            {#if !$needsCalibration}
                <div class="accuracy-good-message">
                    Accuracy is good! Closing soon...
                </div>
            {/if}
        </div>

        <!-- Sensor Details (optional, for debugging) -->
        {#if $sensorAccuracy.magnetometer}
            <div class="sensor-details">
                <span class="sensor-label">Magnetometer:</span>
                <span class="sensor-value accuracy-{$sensorAccuracy.magnetometer?.toLowerCase()}">{$sensorAccuracy.magnetometer}</span>
            </div>
        {/if}

        <!-- Car Mode Hint -->
        <div class="car-mode-hint" data-testid="car-mode-hint">
            <div class="hint-title">In a vehicle?</div>
            <div class="hint-text">Switch to Car Mode for GPS-based heading:</div>
            <div class="mode-switch-visual">
                <div class="compass-button-preview">
                    <CompassButtonInner bearingMode="walking" />
                </div>
                <div class="arrow-icon">
                    <ArrowRight size={24} />
                </div>
                <div class="compass-button-preview target">
                    <CompassButtonInner bearingMode="car" />
                </div>
            </div>
        </div>
        </div>
    </div>

</div>

<style>
    .calibration-overlay {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        z-index: 500;
        overflow: hidden;
        display: flex;
        flex-direction: column;
    }

    .calibration-content {
        flex: 1;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        align-items: center;
    }

    .calibration-content > :global(*) {
        flex-shrink: 0;
    }

    .calibration-inner {
        border-radius: 16px;
        text-align: center;
        position: relative;
		max-width: 95%;

    }

    .close-button {
        position: absolute;
        top: 8px;
        right: 12px;
        background: none;
        border: none;
        font-size: 48px;
        cursor: pointer;
        padding: 4px 8px;
        line-height: 1;
        transition: opacity 0.2s;
        opacity: 0.5;
    }

    .close-button:hover {
        opacity: 1;
    }

    .calibration-title {
        font-size: 1rem;
        font-weight: 600;
    }

    .instruction-row {
        display: flex;
        align-items: center;
        gap: 12px;
        margin: 12px 0;
    }

    .figure8-animation {
        width: 120px;
        height: 80px;
        flex-shrink: 0;
    }

    .figure8-svg {
        width: 100%;
        height: 100%;
    }

    .figure8-svg path {
        stroke: currentColor;
        opacity: 0.3;
    }

    .figure8-svg circle {
        fill: #4a90e2;
    }

    .calibration-instruction {
        margin: 0;
        font-size: 0.9rem;
        line-height: 1.4;
        text-align: left;
    }

    .accuracy-display {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        flex-wrap: wrap;
        margin: 12px 0;
        padding: 8px 12px;
        background: rgba(0, 0, 0, 0.05);
        border-radius: 8px;
    }

    .accuracy-label {
        font-size: 0.9rem;
    }

    .accuracy-value {
        font-size: 0.9rem;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 6px;
        display: inline-block;
    }

    .accuracy-high {
        background: #4caf50;
        color: white;
    }

    .accuracy-medium {
        background: #ffc107;
        color: black;
    }

    .accuracy-low {
        background: #ff9800;
        color: white;
    }

    .accuracy-unreliable {
        background: #f44336;
        color: white;
        animation: pulse-warning 1s infinite;
    }

    .accuracy-unknown {
        background: #9e9e9e;
        color: white;
    }

    @keyframes pulse-warning {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }

    .accuracy-good-message {
        margin-top: 12px;
        font-size: 0.9rem;
        color: #4caf50;
        animation: fade-in-out 1s infinite;
    }

    @keyframes fade-in-out {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }

    .sensor-details {
        margin-top: 8px;
        font-size: 0.8rem;
        opacity: 0.6;
    }

    .sensor-label {
        margin-right: 8px;
    }

    .sensor-value {
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
    }

    .car-mode-hint {
        padding: 8px;
		margin: 8px 0;
        background: rgba(0, 0, 0, 0.03);
        border: 1px solid rgba(0, 0, 0, 0.1);
        border-radius: 12px;
        text-align: center;
    }

    .hint-title {
        font-weight: 600;
        font-size: 0.95rem;
        margin-bottom: 8px;
    }

    .hint-text {
        font-size: 0.85rem;
        opacity: 0.8;
        margin-bottom: 16px;
    }

    .mode-switch-visual {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 12px;
    }

    .compass-button-preview {
        border: 2px solid #ddd;
        border-radius: 4px;
        padding: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .compass-button-preview.target {
        background: #4285F4;
        border-color: #4285F4;
        color: white;
        /*animation: pulse-hint 2s infinite;*/
    }

    @keyframes pulse-hint {
        0%, 100% {
            box-shadow: 0 0 0 0 rgba(66, 133, 244, 0.4);
        }
        50% {
            box-shadow: 0 0 0 8px rgba(66, 133, 244, 0);
        }
    }

    .arrow-icon {
        opacity: 0.5;
    }
</style>
