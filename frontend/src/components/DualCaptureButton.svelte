<script lang="ts">
    import { createEventDispatcher, onDestroy } from 'svelte';
    import { Camera, Zap, Turtle } from 'lucide-svelte';
    
    export let disabled = false;
    export let slowInterval = 1000; // 1 second between captures in slow mode
    export let fastInterval = 100; // 100ms between captures in fast mode
    
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
    let swipeThreshold = 50;
    
    function startCapture(mode: 'slow' | 'fast') {
        const interval = mode === 'slow' ? slowInterval : fastInterval;
        
        // Capture immediately
        /*dispatch('capture', { mode });
        captureCount++;*/
        
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
        dispatch('capture', { mode: 'single' });
    }

    function showButtons() {
        showAllButtons = true;
        if (hideTimer) {
            clearTimeout(hideTimer);
            hideTimer = null;
        }
        // Auto-hide after 3 seconds of inactivity
        hideTimer = window.setTimeout(() => {
            hideButtons();
        }, 3000);
    }

    function hideButtons() {
        showAllButtons = false;
        if (hideTimer) {
            clearTimeout(hideTimer);
            hideTimer = null;
        }
    }

    function handleSinglePointerDown(e: PointerEvent | MouseEvent) {
        console.log('handleSinglePointerDown called', e.type);
        if (disabled) return;
        
        e.preventDefault();
        touchStartX = e.clientX;
        touchStartY = e.clientY;
        isLongPress = false;

        // Clear any existing timer
        if (longPressTimer) {
            clearTimeout(longPressTimer);
        }

        // Start long press timer
        longPressTimer = window.setTimeout(() => {
            console.log('Long press timer triggered, showing buttons');
            isLongPress = true;
            showButtons();
        }, 500); // 500ms for long press
    }

    function handleSinglePointerUp(e: PointerEvent) {
        if (disabled) return;

        // Clear long press timer
        if (longPressTimer) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
        }

        if (!isLongPress) {
            // Short press - single capture
            handleSingleCapture();
        }
        
        isLongPress = false;
    }

    function handleSinglePointerMove(e: PointerEvent) {
        if (disabled || !longPressTimer) return;

        const deltaX = e.clientX - touchStartX;
        const deltaY = e.clientY - touchStartY;
        const distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY);

        // If moved too much, cancel long press
        if (distance > 20) {
            if (longPressTimer) {
                clearTimeout(longPressTimer);
                longPressTimer = null;
            }

            // Check for horizontal swipe
            if (Math.abs(deltaX) > swipeThreshold && Math.abs(deltaY) < swipeThreshold) {
                if (deltaX > 0) {
                    // Swipe right - fast capture
                    handleFastClick();
                } else {
                    // Swipe left - slow capture
                    handleSlowClick();
                }
            }
        }
    }

    function handleSinglePointerLeave() {
        if (longPressTimer) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
        }
        isLongPress = false;
    }
    
    onDestroy(() => {
        stopCapture();
        if (longPressTimer) {
            clearTimeout(longPressTimer);
        }
        if (hideTimer) {
            clearTimeout(hideTimer);
        }
    });
</script>

<div class="capture-button-container" class:expanded={showAllButtons}>
    {#if showAllButtons}
        <button
            class="capture-button slow-mode"
            class:pressed={slowPressed}
            {disabled}
            on:mousedown={handleSlowStart}
            on:mouseup={handleSlowEnd}
            on:mouseleave={handleSlowEnd}
            on:touchstart={handleSlowStart}
            on:touchend={handleSlowEnd}
            on:click={handleSlowClick}
            data-testid="slow-capture-button"
        >
            <Turtle size={24} />
            <span class="mode-label">Slow</span>
        </button>
        
        <div class="button-divider"></div>
    {/if}
    
    <button
        class="capture-button single-mode"
        class:long-pressed={isLongPress}
        {disabled}
        on:pointerdown={handleSinglePointerDown}
        on:pointerup={handleSinglePointerUp}
        on:pointermove={handleSinglePointerMove}
        on:pointerleave={handleSinglePointerLeave}
        data-testid="single-capture-button"
    >
        <Camera size={24} />
        <span class="mode-label">Single</span>
    </button>
    
    {#if showAllButtons}
        <div class="button-divider"></div>
        
        <button
            class="capture-button fast-mode"
            class:pressed={fastPressed}
            {disabled}
            on:mousedown={handleFastStart}
            on:mouseup={handleFastEnd}
            on:mouseleave={handleFastEnd}
            on:touchstart={handleFastStart}
            on:touchend={handleFastEnd}
            on:click={handleFastClick}
            data-testid="fast-capture-button"
        >
            <Zap size={24} />
            <span class="mode-label">Fast</span>
        </button>
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
        overflow: hidden;
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
    
    .capture-button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }
    
    .slow-mode {
        background: linear-gradient(135deg, #4CAF50, #45a049);
    }
    
    .slow-mode:hover:not(:disabled) {
        background: linear-gradient(135deg, #45a049, #3d8b40);
    }
    
    .slow-mode.pressed {
        transform: scale(0.9);
        background: linear-gradient(135deg, #3d8b40, #357a38);
    }
    
    .fast-mode {
        background: linear-gradient(135deg, #ff6b6b, #ff5252);
    }
    
    .fast-mode:hover:not(:disabled) {
        background: linear-gradient(135deg, #ff5252, #ff4141);
    }
    
    .fast-mode.pressed {
        transform: scale(0.9);
        background: linear-gradient(135deg, #ff4141, #ff3030);
    }
    
    .single-mode {
        background: linear-gradient(135deg, #2196F3, #1976D2);
    }
    
    .single-mode:hover:not(:disabled) {
        background: linear-gradient(135deg, #1976D2, #1565C0);
    }
    
    .single-mode:active {
        transform: scale(0.9);
        background: linear-gradient(135deg, #1565C0, #0D47A1);
    }

    .single-mode.long-pressed {
        transform: scale(1.05);
        background: linear-gradient(135deg, #1976D2, #1565C0);
        box-shadow: 0 0 20px rgba(33, 150, 243, 0.5);
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

    @keyframes expandContainer {
        0% { 
            width: 78px;
        }
        100% { 
            width: auto;
        }
    }
</style>