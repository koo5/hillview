import { photoWorkerService } from './photoWorkerService';
import type { BearingResult } from './photoWorkerService';
import { PhotoProcessingQueue, EVENT_CONFIGS } from './photoProcessingQueue';
import type { ProcessingEvent } from './photoProcessingQueue';

// Adapter with restored queueing and debouncing
class PhotoProcessingAdapter {
  private webWorkerCallbacks: Map<string, (result: any) => void> = new Map();
  private isInitialized = false;
  private currentCenter = { lat: 0, lng: 0 };
  private processingQueue!: PhotoProcessingQueue; // Initialized in constructor
  
  constructor() {
    this.setupWebWorkerCallbacks();
    this.setupProcessingQueue();
  }
  
  private setupProcessingQueue(): void {
    this.processingQueue = new PhotoProcessingQueue({
      maxQueueSize: 50,
      debounceMs: 50, // Default, but each event type can override
      enablePreemption: true,
      onProcess: async (event: ProcessingEvent) => {
        // Process based on event type
        switch (event.type) {
          case 'filter_area':
            const { bounds, range, sourcesConfig } = event.data;
            this.currentCenter = {
              lat: (bounds.top_left.lat + bounds.bottom_right.lat) / 2,
              lng: (bounds.top_left.lng + bounds.bottom_right.lng) / 2
            };
            
            await this.ensureInitialized();
            
            // Check if operation was aborted
            if (event.abortSignal?.aborted) {
              console.log('PhotoProcessingAdapter: filter_area aborted');
              return;
            }
            
            await photoWorkerService.updateMapBounds(bounds);
            await photoWorkerService.updateSources(sourcesConfig);
            break;
            
          case 'update_bearing_and_center':
            const { bearing, center, photoIds } = event.data;
            await this.ensureInitialized();
            
            // Check if operation was aborted
            if (event.abortSignal?.aborted) {
              console.log('PhotoProcessingAdapter: update_bearing_and_center aborted');
              return;
            }
            
            await photoWorkerService.updateBearingAndCenter(bearing, center);
            break;
        }
      }
    });
  }
  
  private setupWebWorkerCallbacks(): void {
    // Set up callbacks for web worker mode
    photoWorkerService.onPhotosUpdate((photos: any[]) => {
      // Convert to legacy format for compatibility
      const result = {
        hillviewPhotosInArea: photos.filter(p => p.source?.id === 'hillview'),
        mapillaryPhotosInArea: photos.filter(p => p.source?.id === 'mapillary'),
        photosInArea: photos
      };
      
      // Trigger area filter callback
      const areaCallback = this.webWorkerCallbacks.get('filter_area');
      if (areaCallback) {
        areaCallback(result);
      }
    });
    
    photoWorkerService.onBearingUpdate((result: any) => {
      const callback = this.webWorkerCallbacks.get('update_bearing_and_center');
      if (callback) {
        callback(result);
      }
    });

    // Handle worker errors
    photoWorkerService.onError?.((error: any) => {
      console.error('PhotoProcessingAdapter: Worker error', error);
    });
  }
  
  async ensureInitialized(): Promise<void> {
    if (this.isInitialized) return;
    
    await photoWorkerService.initialize();
    this.isInitialized = true;
  }
  
  // Legacy API methods for compatibility
  queueAreaFilter(bounds: any, range: number, sourcesConfig: any[]): void {
    console.log('PhotoProcessingAdapter: queueAreaFilter called', { bounds, range, sourcesConfig: sourcesConfig.map(s => ({ id: s.id, enabled: s.enabled })) });
    
    // Use the queue with proper debouncing
    this.processingQueue.enqueue('filter_area', {
      bounds,
      range,
      sourcesConfig
    }, {
      priority: 'normal',
      mode: 'replace' // Replace previous area filter requests
    });
  }
  
  queueBearingUpdate(bearing: number, photoIds: string[], priority: 'high' | 'normal' | 'low' = 'high'): void {
    // Use the queue with proper debouncing
    this.processingQueue.enqueue('update_bearing_and_center', {
      bearing,
      center: this.currentCenter,
      photoIds
    }, {
      priority,
      mode: 'replace' // Replace previous bearing update requests
    });
  }

  onResult(type: string, callback: (result: any) => void): void {
    this.webWorkerCallbacks.set(type, callback);
  }
  
  updatePhotoStore(photos: any[]): void {
    this.ensureInitialized().then(() => {
      photoWorkerService.loadPhotos(photos);
    });
  }
  
  updateBearingAndCenter(bearing: number, center: any): void {
    // Store current center
    this.currentCenter = center;
    
    // Use the queue to debounce bearing updates
    this.processingQueue.enqueue('update_bearing_and_center', {
      bearing,
      center,
      photoIds: []
    }, {
      priority: 'high',
      mode: 'replace' // Replace previous bearing update requests
    });
  }
  
  async updateConfig(config: { recalculateBearingDiffForAllPhotosInArea?: boolean }): Promise<void> {
    await this.ensureInitialized();
    await photoWorkerService.updateConfig(config);
  }
  
  getCurrentData(): any | null {
    return photoWorkerService.getCurrentBearingData() || null;
  }
  
  terminate(): void {
    // Clean up callbacks
    this.webWorkerCallbacks.clear();
    
    // Destroy the processing queue (cleans up timers and pending tasks)
    this.processingQueue.destroy();
    
    // Terminate worker service
    photoWorkerService.terminate();
    
    this.isInitialized = false;
  }
  
  // Utility methods
  isUsingWebWorker(): boolean {
    return true; // Always true now
  }
  
  getQueueStatus(): any {
    const queueStatus = this.processingQueue.getStatus();
    const workerStatus = photoWorkerService.getWorkerStatus();
    
    return { 
      isWebWorker: true, 
      initialized: this.isInitialized,
      queue: queueStatus,
      worker: workerStatus
    };
  }
  
  // Emergency queue clear for debugging
  clearQueue(): void {
    console.warn('PhotoProcessingAdapter: Emergency queue clear requested');
    this.processingQueue.clearQueue();
  }
}

// Export singleton instance
export const photoProcessingAdapter = new PhotoProcessingAdapter();