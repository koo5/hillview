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
    
    onDestroy(() => {
        stopCapture();
    });
</script>

<div class="capture-button-container">
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
    
    <button
        class="capture-button single-mode"
        {disabled}
        on:click={handleSingleCapture}
        data-testid="single-capture-button"
    >
        <Camera size={24} />
        <span class="mode-label">Single</span>
    </button>
    
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
</style>