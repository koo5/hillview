<script lang="ts">
    import { createEventDispatcher, onMount, onDestroy } from 'svelte';
    import { bearingState, bearingMode } from '$lib/mapState';
    import { compassState, sensorAccuracy } from '$lib/compass.svelte.js';
    import { Car } from 'lucide-svelte';

    const dispatch = createEventDispatcher<{
        close: {};
        switchToCarMode: {};
    }>();

    export let visible = false;

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

    // Check if accuracy is considered "good" (HIGH or MEDIUM)
    function isAccuracyGood(accuracy: number | null | undefined): boolean {
        return accuracy !== null && accuracy !== undefined && accuracy >= 2;
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

    // Watch accuracy changes for auto-dismiss
    $: {
        const currentAccuracy = $bearingState.accuracy;
        if (visible && isAccuracyGood(currentAccuracy)) {
            if (goodAccuracyStart === null) {
                goodAccuracyStart = Date.now();
                // Schedule auto-dismiss
                if (autoDismissTimeout) clearTimeout(autoDismissTimeout);
                autoDismissTimeout = setTimeout(() => {
                    if (visible && isAccuracyGood($bearingState.accuracy)) {
                        dispatch('close', {});
                    }
                }, AUTO_DISMISS_DELAY);
            }
        } else {
            // Accuracy went bad, reset timer
            goodAccuracyStart = null;
            if (autoDismissTimeout) {
                clearTimeout(autoDismissTimeout);
                autoDismissTimeout = null;
            }
        }
    }

    function handleSwitchToCarMode() {
        dispatch('switchToCarMode', {});
    }

    function handleClose() {
        dispatch('close', {});
    }

    onDestroy(() => {
        if (autoDismissTimeout) {
            clearTimeout(autoDismissTimeout);
        }
    });
</script>

{#if visible}
    <div class="calibration-overlay" data-testid="compass-calibration-overlay">
        <div class="calibration-content">
            <button class="close-button" on:click={handleClose} aria-label="Close calibration" data-testid="calibration-close-btn">
                &times;
            </button>

            <h2 class="calibration-title">Calibrate Compass</h2>

            <!-- Figure-8 Animation -->
            <div class="figure8-container">
                <div class="figure8-animation">
                    <svg viewBox="0 0 100 60" class="figure8-svg">
                        <path
                            d="M50 30 C50 10, 80 10, 80 30 C80 50, 50 50, 50 30 C50 10, 20 10, 20 30 C20 50, 50 50, 50 30"
                            fill="none"
                            stroke="rgba(255,255,255,0.3)"
                            stroke-width="2"
                        />
                        <circle class="moving-dot" r="4" fill="#4a90e2">
                            <animateMotion
                                dur="3s"
                                repeatCount="indefinite"
                                path="M50 30 C50 10, 80 10, 80 30 C80 50, 50 50, 50 30 C50 10, 20 10, 20 30 C20 50, 50 50, 50 30"
                            />
                        </circle>
                    </svg>
                </div>
            </div>

            <p class="calibration-instruction">
                Move your phone in a <strong>figure-8 pattern</strong> several times
            </p>

            <!-- Real-time Accuracy Display -->
            <div class="accuracy-display">
                <div class="accuracy-label">Compass Accuracy</div>
                <div class="accuracy-value accuracy-{getAccuracyClass($bearingState.accuracy)}">
                    {accuracyToString($bearingState.accuracy)}
                </div>
                {#if isAccuracyGood($bearingState.accuracy)}
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
                <div class="hint-icon"><Car size={20} /></div>
                <div class="hint-content">
                    <div class="hint-title">In a vehicle?</div>
                    <div class="hint-text">Switch to <strong>Car Mode</strong> for GPS-based heading</div>
                    <button class="car-mode-button" on:click={handleSwitchToCarMode} data-testid="switch-to-car-mode-btn">
                        Switch to Car Mode
                    </button>
                </div>
            </div>
        </div>
    </div>
{/if}

<style>
    .calibration-overlay {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.85);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        backdrop-filter: blur(4px);
    }

    .calibration-content {
        position: relative;
        background: rgba(30, 30, 30, 0.95);
        border-radius: 16px;
        padding: 24px;
        max-width: 320px;
        width: 90%;
        text-align: center;
        color: white;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }

    .close-button {
        position: absolute;
        top: 8px;
        right: 12px;
        background: none;
        border: none;
        color: rgba(255, 255, 255, 0.6);
        font-size: 28px;
        cursor: pointer;
        padding: 4px 8px;
        line-height: 1;
        transition: color 0.2s;
    }

    .close-button:hover {
        color: white;
    }

    .calibration-title {
        margin: 0 0 16px 0;
        font-size: 1.4rem;
        font-weight: 600;
    }

    .figure8-container {
        margin: 16px 0;
    }

    .figure8-animation {
        width: 120px;
        height: 80px;
        margin: 0 auto;
    }

    .figure8-svg {
        width: 100%;
        height: 100%;
    }

    .calibration-instruction {
        margin: 16px 0;
        font-size: 1rem;
        color: rgba(255, 255, 255, 0.9);
        line-height: 1.5;
    }

    .accuracy-display {
        margin: 20px 0;
        padding: 16px;
        background: rgba(255, 255, 255, 0.1);
        border-radius: 12px;
    }

    .accuracy-label {
        font-size: 0.85rem;
        color: rgba(255, 255, 255, 0.7);
        margin-bottom: 8px;
    }

    .accuracy-value {
        font-size: 1.5rem;
        font-weight: 700;
        padding: 8px 16px;
        border-radius: 8px;
        display: inline-block;
    }

    .accuracy-high {
        background: rgba(76, 175, 80, 0.8);
        color: white;
    }

    .accuracy-medium {
        background: rgba(255, 193, 7, 0.8);
        color: black;
    }

    .accuracy-low {
        background: rgba(255, 152, 0, 0.8);
        color: white;
    }

    .accuracy-unreliable {
        background: rgba(244, 67, 54, 0.8);
        color: white;
        animation: pulse-warning 1s infinite;
    }

    .accuracy-unknown {
        background: rgba(158, 158, 158, 0.8);
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
        color: rgba(255, 255, 255, 0.6);
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
        margin-top: 24px;
        padding: 16px;
        background: rgba(74, 144, 226, 0.15);
        border: 1px solid rgba(74, 144, 226, 0.3);
        border-radius: 12px;
        display: flex;
        align-items: flex-start;
        gap: 12px;
        text-align: left;
    }

    .hint-icon {
        flex-shrink: 0;
        color: #4a90e2;
        margin-top: 2px;
    }

    .hint-content {
        flex: 1;
    }

    .hint-title {
        font-weight: 600;
        font-size: 0.95rem;
        margin-bottom: 4px;
    }

    .hint-text {
        font-size: 0.85rem;
        color: rgba(255, 255, 255, 0.8);
        margin-bottom: 12px;
    }

    .car-mode-button {
        background: #4a90e2;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 10px 16px;
        font-size: 0.9rem;
        font-weight: 500;
        cursor: pointer;
        transition: background 0.2s;
        width: 100%;
    }

    .car-mode-button:hover {
        background: #3a7bc8;
    }

    .car-mode-button:active {
        background: #2a6bb8;
    }
</style>
