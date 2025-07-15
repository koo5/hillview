<script lang="ts">
	import {createEventDispatcher} from 'svelte';
	import {Camera} from 'lucide-svelte';

	export let disabled = false;
	export let size = 32;
	export let captureInterval = 500;

	const dispatch = createEventDispatcher();

	let isCapturing = false;
	let longPressTimer: ReturnType<typeof setTimeout> | null = null;
	let continuousCaptureInterval: ReturnType<typeof setInterval> | null = null;
	let isCaptureInProgress = false;

	function startContinuousCapture() {
		if (isCapturing) {
			console.log('CaptureButton: already capturing');
			return;
		}

		isCapturing = true;
		dispatch('captureStart');

		// Capture immediately
		triggerCapture();

		// Then capture at specified interval
		continuousCaptureInterval = setInterval(() => {
			console.log('CaptureButton: continuous capture interval, isCapturing:', isCapturing, 'isCaptureInProgress:', isCaptureInProgress);
			if (isCapturing && !isCaptureInProgress) {
				triggerCapture();
			}
		}, captureInterval);
	}

	function triggerCapture() {
		console.log('CaptureButton: trigger capture, isCapturing:', isCapturing, 'isCaptureInProgress:', isCaptureInProgress);

		if (isCaptureInProgress) return;

		isCaptureInProgress = true;
		dispatch('capture');

		// Reset the flag after a reasonable timeout (2 seconds)
		// This prevents permanent blocking if capture callback doesn't complete
		setTimeout(() => {
			isCaptureInProgress = false;
		}, 2000);
	}

	function stopContinuousCapture() {
		console.log('CaptureButton: stop continuous capture, isCapturing:', isCapturing, 'isCaptureInProgress:', isCaptureInProgress);
		isCapturing = false;
		if (continuousCaptureInterval) {
			clearInterval(continuousCaptureInterval);
			continuousCaptureInterval = null;
		}
		dispatch('captureStop');
	}

	function handlePointerDown(event: PointerEvent) {
		console.log('CaptureButton: pointerdown event', event.type, event.pointerId);
		event.preventDefault();

		if (isCapturing) {
			stopContinuousCapture();
		} else {
		}

		// Clear any existing timer
		if (longPressTimer) {
			clearTimeout(longPressTimer);
		}

		// Start a timer for long press detection (500ms)
		longPressTimer = setTimeout(() => {
			console.log('CaptureButton: long press detected, starting continuous capture');
			startContinuousCapture();
		}, 500);
	}

	function handlePointerUp(event: PointerEvent) {
		console.log('CaptureButton: pointerup event', event.type, 'isCapturing:', isCapturing);

		// Clear the long press timer
		if (longPressTimer) {
			clearTimeout(longPressTimer);
			longPressTimer = null;
		}

		if (isCapturing) {
		} else {
			// It was a short press, take single photo
			triggerCapture();
		}
	}

	function handlePointerLeave() {
		// Clean up if pointer leaves the button
		if (longPressTimer) {
			clearTimeout(longPressTimer);
			longPressTimer = null;
		}
		if (isCapturing) {
			//    stopContinuousCapture();
		}
	}

	// Cleanup
	$: if (disabled && isCapturing) {
		stopContinuousCapture();
	}

	// Allow parent to signal when capture is complete
	export function captureComplete() {
		isCaptureInProgress = false;
	}
</script>

<button
        class="capture-button {isCapturing ? 'capturing' : ''}"
        on:pointerdown={handlePointerDown}
        on:pointerup={handlePointerUp}
        on:pointerleave={handlePointerLeave}
        {disabled}
        aria-label="{isCapturing ? 'Stop continuous capture' : 'Capture photo (hold for continuous)'}"
>
    <Camera {size}/>
</button>

<style>
    .capture-button {
        width: 72px;
        height: 72px;
        border-radius: 50%;
        background: white;
        border: 4px solid rgba(255, 255, 255, 0.3);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s;
        color: black;
        position: relative;
        touch-action: none;
        user-select: none;
        -webkit-user-select: none;
        -webkit-touch-callout: none;
    }

    .capture-button:hover:not(:disabled) {
        transform: scale(1.1);
        border-color: rgba(255, 255, 255, 0.5);
    }

    .capture-button:active:not(:disabled) {
        transform: scale(0.95);
    }

    .capture-button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .capture-button.capturing {
        animation: pulse 1s ease-in-out infinite;
        border-color: #ff4444;
        background: #ffeeee;
    }

    .capture-button.capturing::before {
        content: '';
        position: absolute;
        top: -8px;
        left: -8px;
        right: -8px;
        bottom: -8px;
        border-radius: 50%;
        border: 2px solid #ff4444;
        animation: ripple 1s linear infinite;
    }

    @keyframes pulse {
        0%, 100% {
            transform: scale(1);
        }
        50% {
            transform: scale(1.05);
        }
    }

    @keyframes ripple {
        0% {
            transform: scale(1);
            opacity: 1;
        }
        100% {
            transform: scale(1.2);
            opacity: 0;
        }
    }

    @media (max-width: 600px) {
        .capture-button {
            width: 60px;
            height: 60px;
        }
    }
</style>