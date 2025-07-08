<script lang="ts">
  import { USE_WEBWORKER } from './photoProcessingConfig';
  import { photoProcessingAdapter } from './photoProcessingAdapter';
  
  let isWebWorkerMode = false;
  
  // Subscribe to the store
  USE_WEBWORKER.subscribe(value => {
    isWebWorkerMode = value;
  });
  
  function toggleMode() {
    USE_WEBWORKER.set(!isWebWorkerMode);
    
    // Log the switch
    console.log(`Switched to ${!isWebWorkerMode ? 'Web Worker' : 'Main Thread'} mode`);
    
    // Show queue status
    setTimeout(() => {
      console.log('Queue status:', photoProcessingAdapter.getQueueStatus());
    }, 100);
  }
  
  // Get current status
  $: currentMode = isWebWorkerMode ? 'Web Worker' : 'Main Thread';
  $: queueStatus = photoProcessingAdapter.getQueueStatus();
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
      on:click={() => !isWebWorkerMode || toggleMode()}
    >
      Main Thread
    </button>
    
    <button 
      class="toggle-btn" 
      class:active={isWebWorkerMode}
      on:click={() => isWebWorkerMode || toggleMode()}
    >
      Web Worker
    </button>
  </div>
  
  <div class="mode-info">
    {#if isWebWorkerMode}
      <div class="info-item">
        <strong>Web Worker Mode:</strong> Heavy photo filtering runs in background thread
      </div>
      <div class="info-item">
        Status: {queueStatus.initialized ? 'Initialized' : 'Initializing...'}
      </div>
    {:else}
      <div class="info-item">
        <strong>Main Thread Mode:</strong> Photo processing uses queue system
      </div>
      {#if queueStatus.pending}
        <div class="info-item">
          Queue: {queueStatus.pending} pending tasks
        </div>
      {/if}
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
  
  .mode-info {
    font-size: 13px;
    color: #666;
  }
  
  .info-item {
    margin: 4px 0;
  }
</style>