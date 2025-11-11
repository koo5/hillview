<script lang="ts">
    import { captureQueue, type QueueStats } from '$lib/captureQueue';
    
    let stats: QueueStats;
    
    captureQueue.stats.subscribe(value => {
        stats = value;
    });
</script>

{#if stats}
    <div class="queue-status" data-testid="capture-queue-status">
        <div class="stat-row">
            <span class="label">Queue:</span>
            <span class="value" class:warning={stats.size > 30} class:danger={stats.size > 40}>
                {stats.size}/50
            </span>
            {#if stats.processingCount > 0}
                <span class="processing-indicator">⚡ {stats.processingCount}</span>
            {/if}
        </div>
        
        <div class="stat-row">
            <span class="label">Captured:</span>
            <span class="value">{stats.totalCaptured}</span>
        </div>
        
        <div class="stat-row">
            <span class="label">Processed:</span>
            <span class="value success">{stats.totalProcessed}</span>
            {#if stats.totalFailed > 0}
                <span class="value danger">({stats.totalFailed} failed)</span>
            {/if}
        </div>
        
        <div class="stat-row">
            <span class="label">Mode:</span>
            <span class="value slow">S:{stats.slowModeCount}</span>
            <span class="value fast">F:{stats.fastModeCount}</span>
        </div>
    </div>
{/if}

<style>
    .queue-status {
        background: rgba(0, 0, 0, 0.8);
        color: white;
        padding: 12px;
        border-radius: 8px;
        font-size: 13px;
        font-family: monospace;
        display: flex;
        flex-direction: column;
        gap: 6px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    }
    
    .stat-row {
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    .label {
        opacity: 0.8;
        min-width: 50px;
    }
    
    .value {
        font-weight: bold;
        color: #4CAF50;
    }
    
    .value.success {
        color: #4CAF50;
    }
    
    .value.warning {
        color: #ff9800;
    }
    
    .value.danger {
        color: #f44336;
    }
    
    .value.slow {
        color: #4CAF50;
    }
    
    .value.fast {
        color: #ff6b6b;
    }
    
    .processing-indicator {
        animation: blink 0.5s infinite;
    }
    
    @keyframes blink {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.3; }
    }
</style>