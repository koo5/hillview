import { photoWorkerService } from './photoWorkerService';
import type { BearingResult } from './photoWorkerService';

// Simplified adapter that only uses the web worker service
class PhotoProcessingAdapter {
  private webWorkerCallbacks: Map<string, (result: any) => void> = new Map();
  private isInitialized = false;
  private currentCenter = { lat: 0, lng: 0 };
  
  constructor() {
    this.setupWebWorkerCallbacks();
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
      
      // Also trigger distance calculation callback since web worker includes distance data
      const distanceCallback = this.webWorkerCallbacks.get('calculate_distances');
      if (distanceCallback) {
        const photosInRange = photos.filter(p => p.range_distance !== null && p.range_distance !== undefined);
        distanceCallback({ photosInRange });
      }
    });
    
    photoWorkerService.onBearingUpdate((result: any) => {
      const callback = this.webWorkerCallbacks.get('update_bearings');
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
    
    // Update current center for bearing calculations
    this.currentCenter = {
      lat: (bounds.top_left.lat + bounds.bottom_right.lat) / 2,
      lng: (bounds.top_left.lng + bounds.bottom_right.lng) / 2
    };
    
    this.ensureInitialized().then(() => {
      console.log('PhotoProcessingAdapter: Calling worker updateMapBounds');
      photoWorkerService.updateMapBounds(bounds);
      photoWorkerService.updateRange(range);
      photoWorkerService.updateSources(sourcesConfig);
    });
  }
  
  queueBearingUpdate(bearing: number, photoIds: string[], priority: string = 'high'): void {
    this.ensureInitialized().then(() => {
      photoWorkerService.updateBearing(bearing, this.currentCenter);
    });
  }
  
  queueDistanceCalculation(photoIds: string[], center: any, range: number): void {
    this.ensureInitialized().then(() => {
      photoWorkerService.updateRange(range);
      // Distance calculation is handled automatically in web worker
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
  
  updateBearing(bearing: number, center: any): void {
    this.ensureInitialized().then(() => {
      photoWorkerService.updateBearing(bearing, center);
    });
  }
  
  getCurrentBearingData(): any | null {
    return photoWorkerService.getCurrentBearingData() || null;
  }
  
  terminate(): void {
    // Clean up callbacks
    this.webWorkerCallbacks.clear();
    
    // Terminate worker service
    photoWorkerService.terminate();
    
    this.isInitialized = false;
  }
  
  // Utility methods
  isUsingWebWorker(): boolean {
    return true; // Always true now
  }
  
  getQueueStatus(): any {
    return { isWebWorker: true, initialized: this.isInitialized };
  }
}

// Export singleton instance
export const photoProcessingAdapter = new PhotoProcessingAdapter();