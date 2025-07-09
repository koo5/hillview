<script lang="ts">
  import { USE_WEBWORKER } from './photoProcessingConfig';
  import { photoProcessingAdapter } from './photoProcessingAdapter';
  
  let isWebWorkerMode = false;
  
  // Subscribe to the store
  USE_WEBWORKER.subscribe(value => {
    isWebWorkerMode = value;
  });
  
  let isToggling = false;
  let lastError = '';
  
  async function toggleMode() {
    if (isToggling) return;
    
    isToggling = true;
    lastError = '';
    
    try {
      USE_WEBWORKER.set(!isWebWorkerMode);
      
      // Log the switch
      console.log(`Switched to ${!isWebWorkerMode ? 'Web Worker' : 'Main Thread'} mode`);
      
      // Give some time for the switch to complete
      await new Promise(resolve => setTimeout(resolve, 200));
      
      // Show queue status
      console.log('Queue status:', photoProcessingAdapter.getQueueStatus());
    } catch (error) {
      lastError = error instanceof Error ? error.message : 'Unknown error';
      console.error('Error switching modes:', error);
      
      // Revert the change on error
      USE_WEBWORKER.set(isWebWorkerMode);
    } finally {
      isToggling = false;
    }
  }
  
  // Get current status
  $: currentMode = isWebWorkerMode ? 'Web Worker' : 'Main Thread';
  $: queueStatus = photoProcessingAdapter.getQueueStatus();
  $: statusColor = queueStatus.ready ? '#28a745' : queueStatus.initialized ? '#ffc107' : '#dc3545';
</script>

<div class="photo-processing-toggle">
  <div class="toggle-header">
    <h3>Photo Processing Mode</h3>
    <div class="current-mode">
      Current: <strong>{currentMode}</strong>
    </div>
  </div>
  
  <div class="toggle-controls">
    <button 
      class="toggle-btn" 
      class:active={!isWebWorkerMode}
      class:disabled={isToggling}
      disabled={isToggling}
      on:click={() => !isWebWorkerMode || toggleMode()}
    >
      Main Thread
    </button>
    
    <button 
      class="toggle-btn" 
      class:active={isWebWorkerMode}
      class:disabled={isToggling}
      disabled={isToggling}
      on:click={() => isWebWorkerMode || toggleMode()}
    >
      Web Worker
    </button>
  </div>
  
  {#if lastError}
    <div class="error-message">
      <strong>Error:</strong> {lastError}
    </div>
  {/if}
  
  <div class="mode-info">
    {#if isWebWorkerMode}
      <div class="info-item">
        <strong>Web Worker Mode:</strong> Heavy photo filtering runs in background thread
      </div>
      <div class="info-item">
        <span class="status-indicator" style="color: {statusColor}">●</span>
        Status: {queueStatus.ready ? 'Ready' : queueStatus.initialized ? 'Initialized' : 'Initializing...'}
        {#if queueStatus.pendingOperations > 0}
          ({queueStatus.pendingOperations} pending)
        {/if}
      </div>
    {:else}
      <div class="info-item">
        <strong>Main Thread Mode:</strong> Photo processing uses queue system
      </div>
      {#if queueStatus.pending}
        <div class="info-item">
          <span class="status-indicator" style="color: #ffc107">●</span>
          Queue: {queueStatus.pending} pending tasks
        </div>
      {:else}
        <div class="info-item">
          <span class="status-indicator" style="color: #28a745">●</span>
          Ready
        </div>
      {/if}
    {/if}
    
    {#if isToggling}
      <div class="info-item">
        <em>Switching modes...</em>
      </div>
    {/if}
  </div>
</div>

<style>
  .photo-processing-toggle {
    background: #f5f5f5;
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 16px;
    margin: 16px 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }
  
  .toggle-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }
  
  .toggle-header h3 {
    margin: 0;
    font-size: 16px;
    color: #333;
  }
  
  .current-mode {
    font-size: 14px;
    color: #666;
  }
  
  .toggle-controls {
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
  }
  
  .toggle-btn {
    background: #fff;
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 8px 16px;
    cursor: pointer;
    font-size: 14px;
    transition: all 0.2s;
  }
  
  .toggle-btn:hover {
    background: #f9f9f9;
  }
  
  .toggle-btn.active {
    background: #007bff;
    color: white;
    border-color: #007bff;
  }
  
  .toggle-btn.disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  .error-message {
    background: #f8d7da;
    color: #721c24;
    border: 1px solid #f5c6cb;
    border-radius: 4px;
    padding: 8px 12px;
    margin: 8px 0;
    font-size: 13px;
  }
  
  .mode-info {
    font-size: 13px;
    color: #666;
  }
  
  .info-item {
    margin: 4px 0;
    display: flex;
    align-items: center;
    gap: 4px;
  }
  
  .status-indicator {
    font-size: 12px;
    margin-right: 4px;
  }
</style>