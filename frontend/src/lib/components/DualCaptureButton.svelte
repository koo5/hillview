<script lang="ts">
    import { createEventDispatcher, onDestroy, onMount } from 'svelte';
    import { Camera, Zap, Turtle } from 'lucide-svelte';
	import {frontendBusy} from "$lib/data.svelte.js";

    export let disabled = false;
    export let slowInterval = 10000;
    export let fastInterval = 2000; // ms

    const dispatch = createEventDispatcher();

    let slowPressed = false;
    let fastPressed = false;
    let captureInterval: number | null = null;
    let captureCount = 0;
    let showAllButtons = false;
    let longPressTimer: number | null = null;
    let hideTimer: number | null = null;
    let isLongPress = false;
    let touchStartX = 0;
    let touchStartY = 0;
    let currentDragX = 0;
    let dragThreshold = 30;
    let selectedMode: 'slow' | 'fast' | null = null;
    let isPointerDown = false;
    let slowButtonEl: HTMLElement | null = null;
    let fastButtonEl: HTMLElement | null = null;
    let singleButtonEl: HTMLButtonElement | null = null;
    let hoveredButton: 'slow' | 'fast' | null = null;
    let activeMode: 'slow' | 'fast' | null = null;

    function startCapture(mode: 'slow' | 'fast') {

		stopCapture();

        activeMode = mode;
        const interval = mode === 'slow' ? slowInterval : fastInterval;

        // Emit capture start event
        dispatch('captureStart', { mode });

        // Capture immediately
        dispatch('capture', { mode });
        captureCount++;

        // Start interval for continuous capture
        captureInterval = window.setInterval(() => {
            dispatch('capture', { mode });
            captureCount++;
        }, interval);
    }

    function stopCapture() {
        if (captureInterval) {
            clearInterval(captureInterval);
            captureInterval = null;
        }
        captureCount = 0;
        activeMode = null;
    }

    function handleSlowStart(e?: Event) {
        if (e) e.preventDefault();
        if (disabled) return;
        slowPressed = true;
        dispatch('captureStart', { mode: 'slow' });
        startCapture('slow');
    }

    function handleSlowEnd() {
        slowPressed = false;
        stopCapture();
        dispatch('captureEnd', { mode: 'slow', count: captureCount });
        captureCount = 0;
    }

    function handleFastStart(e?: Event) {
        if (e) e.preventDefault();
        if (disabled) return;
        fastPressed = true;
        dispatch('captureStart', { mode: 'fast' });
        startCapture('fast');
    }

    function handleFastEnd() {
        fastPressed = false;
        stopCapture();
        dispatch('captureEnd', { mode: 'fast', count: captureCount });
        captureCount = 0;
    }

    function handleSlowClick() {
        if (disabled) return;
        dispatch('capture', { mode: 'slow' });
    }

    function handleFastClick() {
        if (disabled) return;
        dispatch('capture', { mode: 'fast' });
    }

    function handleSingleCapture() {
        if (disabled) return;

        // If a mode is active, stop it
        if (activeMode) {
            stopCapture();
            dispatch('captureEnd', { mode: activeMode, count: captureCount });
        } else {
            // Otherwise, do a single capture
            dispatch('capture', { mode: 'single' });
        }
    }

    function showButtons() {
        showAllButtons = true;
        if (hideTimer) {
            clearTimeout(hideTimer);
            hideTimer = null;
        }
    }

    function hideButtons() {
        showAllButtons = false;
        if (hideTimer) {
            clearTimeout(hideTimer);
            hideTimer = null;
        }
    }

    function handleSinglePointerDown(e: PointerEvent | MouseEvent) {
        if (disabled) return;

        e.preventDefault();
        isPointerDown = true;
        touchStartX = e.clientX;
        touchStartY = e.clientY;
        currentDragX = 0;
        isLongPress = false;
        selectedMode = null;

        // Clear any existing timer
        if (longPressTimer) {
            clearTimeout(longPressTimer);
        }

        // Start long press timer to show buttons
        longPressTimer = window.setTimeout(() => {
            isLongPress = true;
            showButtons();
        }, 300); // Shorter timeout for quicker response
    }

    function handleSinglePointerUp(e: PointerEvent | MouseEvent) {
        if (disabled) return;
        if (!isPointerDown) return; // Ignore if we weren't tracking

        isPointerDown = false;

        // Clear long press timer
        if (longPressTimer) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
        }

        // Check what element we're over for the final selection
        if (isLongPress && showAllButtons) {
            const target = document.elementFromPoint(e.clientX, e.clientY);

            if (slowButtonEl && slowButtonEl.contains(target as Node)) {
                // Start slow continuous capture
                startCapture('slow');
            } else if (fastButtonEl && fastButtonEl.contains(target as Node)) {
                // Start fast continuous capture
                startCapture('fast');
            }
            // If not over any button, no capture
        } else if (!isLongPress) {
            // Short press - single capture
            handleSingleCapture();
        }

        // Reset state and hide buttons immediately
        isLongPress = false;
        selectedMode = null;
        hoveredButton = null;
        hideButtons();
    }

    function handleSinglePointerMove(e: PointerEvent | MouseEvent) {
        if (disabled) return;

        const deltaX = e.clientX - touchStartX;
        const deltaY = e.clientY - touchStartY;
        const distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY);

        currentDragX = deltaX;

        // If we're in long press mode
        if (isLongPress && showAllButtons) {
            // Check which button element the pointer is over
            const target = document.elementFromPoint(e.clientX, e.clientY);

            if (slowButtonEl && slowButtonEl.contains(target as Node)) {
                hoveredButton = 'slow';
                selectedMode = 'slow';
            } else if (fastButtonEl && fastButtonEl.contains(target as Node)) {
                hoveredButton = 'fast';
                selectedMode = 'fast';
            } else {
                hoveredButton = null;
                selectedMode = null;
            }
        } else if (longPressTimer && distance > 15) {
            // If we moved before long press activated, cancel it
            clearTimeout(longPressTimer);
            longPressTimer = null;
        }
    }

    function handleSinglePointerLeave() {
        if (longPressTimer) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
        }

        // Only hide if we're not actively pressing
        if (!isPointerDown) {
            if (showAllButtons) {
                hideButtons();
            }
            isLongPress = false;
            selectedMode = null;
        }
    }

    function handleGlobalPointerMove(e: PointerEvent) {
        if (isPointerDown && isLongPress) {
            handleSinglePointerMove(e);
        }
    }

    function handleGlobalPointerUp(e: PointerEvent) {
        if (isPointerDown) {
            handleSinglePointerUp(e);
        }
    }

    onMount(() => {
        // Add global pointer listeners to track movement and releases anywhere
        document.addEventListener('pointermove', handleGlobalPointerMove);
        document.addEventListener('mousemove', handleGlobalPointerMove as any);
        document.addEventListener('pointerup', handleGlobalPointerUp);
        document.addEventListener('mouseup', handleGlobalPointerUp as any);
    });

    onDestroy(() => {
        stopCapture();
        if (longPressTimer) {
            clearTimeout(longPressTimer);
        }
        if (hideTimer) {
            clearTimeout(hideTimer);
        }
        document.removeEventListener('pointermove', handleGlobalPointerMove);
        document.removeEventListener('mousemove', handleGlobalPointerMove as any);
        document.removeEventListener('pointerup', handleGlobalPointerUp);
        document.removeEventListener('mouseup', handleGlobalPointerUp as any);
    });
</script>

<div class="capture-button-container" class:expanded={showAllButtons} style="cursor: {isPointerDown && isLongPress ? 'pointer' : 'default'}">
    {#if showAllButtons}
        <div
            bind:this={slowButtonEl}
            class="capture-button slow-mode"
            class:pressed={slowPressed}
            class:selected={selectedMode === 'slow'}
            class:hovered={hoveredButton === 'slow'}
            data-testid="slow-capture-button"
        >
            <Turtle size={24} />
            <span class="mode-label">Slow</span>
        </div>

        <div class="button-divider"></div>
    {/if}

    <button
        bind:this={singleButtonEl}
        class="capture-button single-mode"
        class:long-pressed={isLongPress}
        class:slow-active={activeMode === 'slow'}
        class:fast-active={activeMode === 'fast'}
        disabled={disabled || $frontendBusy > 0}
        on:pointerdown={handleSinglePointerDown}
        on:pointerup={handleSinglePointerUp}
        on:pointermove={handleSinglePointerMove}
        on:pointerleave={handleSinglePointerLeave}
        on:mousedown={handleSinglePointerDown}
        on:mouseup={handleSinglePointerUp}
        on:mousemove={handleSinglePointerMove}
        on:mouseleave={handleSinglePointerLeave}
        data-testid="single-capture-button"
    >
        <Camera size={24} />
        <span class="mode-label">{activeMode ? 'Stop' : ''}</span>
    </button>

    {#if showAllButtons}
        <div class="button-divider"></div>

        <div
            bind:this={fastButtonEl}
            class="capture-button fast-mode"
            class:pressed={fastPressed}
            class:selected={selectedMode === 'fast'}
            class:hovered={hoveredButton === 'fast'}
            data-testid="fast-capture-button"
        >
            <Zap size={24} />
            <span class="mode-label">Fast</span>
        </div>
    {/if}

    {#if captureCount > 0}
        <div class="capture-counter">
            {captureCount}
        </div>
    {/if}
</div>

<style>
    .capture-button-container {
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(0, 0, 0, 0.5);
        border-radius: 40px;
        padding: 4px;
        transition: all 0.3s ease;
        /*overflow: hidden;*/
    }

    .capture-button-container:not(.expanded) {
        width: 78px; /* Just enough for single button */
    }

    .capture-button-container.expanded {
        width: auto; /* Allow expansion */
        animation: expandContainer 0.3s ease;
    }

    .capture-button {
        width: 70px;
        height: 70px;
        border-radius: 50%;
        border: none;
        cursor: pointer;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        transition: all 0.2s ease;
        color: white;
        position: relative;
        touch-action: none;
        user-select: none;
        -webkit-user-select: none;
        -webkit-touch-callout: none;
    }

    .capture-button:not(button) {
        pointer-events: all;
    }

    .capture-button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .slow-mode {
        background: linear-gradient(135deg, #4CAF50, #45a049);
    }

    .slow-mode.pressed {
        transform: scale(0.9);
        background: linear-gradient(135deg, #3d8b40, #357a38);
    }

    .slow-mode.selected,
    .slow-mode.hovered {
        transform: scale(1.1);
        background: linear-gradient(135deg, #66BB6A, #4CAF50);
        box-shadow: 0 0 20px rgba(76, 175, 80, 0.6);
        border: 2px solid #81C784;
    }

    .fast-mode {
        background: linear-gradient(135deg, #ff6b6b, #ff5252);
    }

    .fast-mode.pressed {
        transform: scale(0.9);
        background: linear-gradient(135deg, #ff4141, #ff3030);
    }

    .fast-mode.selected,
    .fast-mode.hovered {
        transform: scale(1.1);
        background: linear-gradient(135deg, #FF7043, #ff6b6b);
        box-shadow: 0 0 20px rgba(255, 107, 107, 0.6);
        border: 2px solid #FF8A65;
    }

    .single-mode {
        background: linear-gradient(135deg, #2196F3, #1976D2);
    }

    .single-mode:hover:not(:disabled) {
        background: linear-gradient(135deg, #1976D2, #1565C0);
    }

    .single-mode:active {
        transform: scale(0.5);
        background: linear-gradient(135deg, #1565C0, #0D47A1);
    }

    .single-mode.long-pressed {
        transform: scale(1.05);
        background: linear-gradient(135deg, #1976D2, #1565C0);
        box-shadow: 0 0 20px rgba(33, 150, 243, 0.5);
    }

    .single-mode.slow-active {
        background: linear-gradient(135deg, #4CAF50, #45a049) !important;
        animation: pulse-slow 2s ease-in-out infinite;
    }

    .single-mode.slow-active:hover {
        background: linear-gradient(135deg, #45a049, #3d8b40) !important;
    }

    .single-mode.fast-active {
        background: linear-gradient(135deg, #ff6b6b, #ff5252) !important;
        animation: pulse-fast 0.8s ease-in-out infinite;
    }

    .single-mode.fast-active:hover {
        background: linear-gradient(135deg, #ff5252, #ff4141) !important;
    }

    .button-divider {
        width: 2px;
        height: 50px;
        background: rgba(255, 255, 255, 0.3);
        margin: 0 8px;
    }

    .mode-label {
        font-size: 11px;
        margin-top: 2px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .capture-counter {
        position: absolute;
        top: -10px;
        right: -10px;
        background: #2196F3;
        color: white;
        border-radius: 20px;
        padding: 4px 12px;
        font-size: 14px;
        font-weight: bold;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
        animation: pulse 0.5s ease;
    }

    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.1); }
        100% { transform: scale(1); }
    }

    @keyframes pulse-slow {
        0% {
            transform: scale(1);
            box-shadow: 0 0 0 rgba(76, 175, 80, 0);
        }
        50% {
            transform: scale(1.05);
            box-shadow: 0 0 20px rgba(76, 175, 80, 0.5);
        }
        100% {
            transform: scale(1);
            box-shadow: 0 0 0 rgba(76, 175, 80, 0);
        }
    }

    @keyframes pulse-fast {
        0% {
            transform: scale(1);
            box-shadow: 0 0 0 rgba(255, 107, 107, 0);
        }
        50% {
            transform: scale(1.05);
            box-shadow: 0 0 20px rgba(255, 107, 107, 0.5);
        }
        100% {
            transform: scale(1);
            box-shadow: 0 0 0 rgba(255, 107, 107, 0);
        }
    }

    @keyframes expandContainer {
        0% {
            width: 78px;
        }
        100% {
            width: auto;
        }
    }
</style>
