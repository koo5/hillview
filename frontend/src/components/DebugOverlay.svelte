<script lang="ts">
    import { getBuildInfo } from '$lib/build-info';
    import { onMount } from 'svelte';
    
    let showDebug = false;
    let buildInfo = getBuildInfo();
    let currentTime = new Date().toLocaleTimeString();
    
    onMount(() => {
        // Update time every second
        const interval = setInterval(() => {
            currentTime = new Date().toLocaleTimeString();
        }, 1000);
        
        // Check for debug mode in localStorage or URL params
        const urlParams = new URLSearchParams(window.location.search);
        const debugParam = urlParams.get('debug');
        const storedDebug = localStorage.getItem('debugMode');
        
        showDebug = debugParam === 'true' || storedDebug === 'true' || buildInfo.debugMode;
        
        return () => clearInterval(interval);
    });
    
    function toggleDebug() {
        showDebug = !showDebug;
        localStorage.setItem('debugMode', showDebug.toString());
    }
    
    // Keyboard shortcut to toggle debug
    function handleKeydown(e: KeyboardEvent) {
        if (e.ctrlKey && e.shiftKey && e.key === 'D') {
            toggleDebug();
        }
    }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if showDebug}
    <div class="debug-overlay">
        <div class="debug-header">
            <span>Debug Info</span>
            <button on:click={toggleDebug} aria-label="Close debug">×</button>
        </div>
        <div class="debug-content">
            <div><strong>Build Time:</strong> {buildInfo.formattedTime}</div>
            <div><strong>Build Version:</strong> {buildInfo.buildVersion}</div>
            <div><strong>Current Time:</strong> {currentTime}</div>
            <div><strong>Debug Mode:</strong> {buildInfo.debugMode ? 'ON' : 'OFF'}</div>
            <div><strong>User Agent:</strong> {navigator.userAgent}</div>
            <div class="debug-note">Press Ctrl+Shift+D to toggle</div>
        </div>
    </div>
{:else}
    <button 
        class="debug-toggle-button" 
        on:click={toggleDebug}
        aria-label="Show debug info"
        title="Show debug info (Ctrl+Shift+D)"
    >
        🐛
    </button>
{/if}

<style>
    .debug-overlay {
        position: fixed;
        top: 10px;
        right: 10px;
        background: rgba(0, 0, 0, 0.9);
        color: #0f0;
        font-family: monospace;
        font-size: 12px;
        padding: 0;
        border-radius: 5px;
        z-index: 10000;
        min-width: 300px;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.5);
    }
    
    .debug-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 12px;
        background: rgba(0, 255, 0, 0.1);
        border-bottom: 1px solid #0f0;
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
        padding: 12px;
    }
    
    .debug-content div {
        margin: 4px 0;
        word-break: break-all;
    }
    
    .debug-content strong {
        color: #0f0;
    }
    
    .debug-note {
        margin-top: 8px;
        padding-top: 8px;
        border-top: 1px solid rgba(0, 255, 0, 0.3);
        font-size: 11px;
        opacity: 0.7;
    }
    
    .debug-toggle-button {
        position: fixed;
        bottom: 10px;
        right: 10px;
        background: rgba(0, 0, 0, 0.7);
        border: 1px solid #333;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        z-index: 9999;
        font-size: 20px;
        transition: all 0.2s;
    }
    
    .debug-toggle-button:hover {
        background: rgba(0, 0, 0, 0.9);
        border-color: #666;
        transform: scale(1.1);
    }
    
    @media (max-width: 600px) {
        .debug-overlay {
            top: 5px;
            right: 5px;
            left: 5px;
            min-width: auto;
        }
    }
</style>