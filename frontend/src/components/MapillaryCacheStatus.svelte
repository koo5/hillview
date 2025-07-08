<script lang="ts">
    import { mapillary_cache_status } from '../lib/data.svelte';
    
    $: status = $mapillary_cache_status;
</script>

<div class="cache-status" class:streaming={status.is_streaming}>
    <div class="cache-info">
        <span class="cache-label">Mapillary Cache:</span>
        {#if status.is_streaming}
            <span class="streaming-indicator">
                <span class="spinner"></span>
                Streaming ({status.uncached_regions} regions)
            </span>
        {:else if status.uncached_regions > 0}
            <span class="cache-partial">Partial ({status.uncached_regions} uncached)</span>
        {:else}
            <span class="cache-complete">Complete</span>
        {/if}
    </div>
    
    {#if status.total_live_photos > 0}
        <div class="live-photos-count">
            +{status.total_live_photos} live photos loaded
        </div>
    {/if}
</div>

<style>
    .cache-status {
        position: fixed;
        top: 60px;
        right: 10px;
        background: rgba(0, 0, 0, 0.8);
        color: white;
        padding: 8px 12px;
        border-radius: 4px;
        font-size: 12px;
        z-index: 1000;
        min-width: 150px;
    }
    
    .cache-info {
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    .cache-label {
        font-weight: bold;
    }
    
    .streaming-indicator {
        color: #ffa500;
        display: flex;
        align-items: center;
        gap: 4px;
    }
    
    .cache-partial {
        color: #ffff00;
    }
    
    .cache-complete {
        color: #00ff00;
    }
    
    .live-photos-count {
        font-size: 11px;
        color: #aaa;
        margin-top: 4px;
    }
    
    .spinner {
        width: 12px;
        height: 12px;
        border: 2px solid transparent;
        border-top: 2px solid #ffa500;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }
    
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    
    .streaming {
        background: rgba(255, 165, 0, 0.2);
        border: 1px solid rgba(255, 165, 0, 0.5);
    }
</style>