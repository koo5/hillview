import { get } from 'svelte/store';
import { USE_WEBWORKER, type PhotoProcessingServiceInterface } from './photoProcessingConfig';
import { photoProcessingService } from './photoProcessingService';
import { photoWorkerService } from './photoWorkerService';
import type { AreaFilterResult, DistanceResult, BearingResult } from './photoProcessingService';

// Adapter that wraps both services with a unified interface
class PhotoProcessingAdapter implements PhotoProcessingServiceInterface {
  private isWebWorkerMode = false;
  private currentService: any;
  private webWorkerCallbacks: Map<string, (result: any) => void> = new Map();
  private isInitialized = false;
  private currentCenter = { lat: 0, lng: 0 };
  
  constructor() {
    this.updateService();
    
    // Watch for configuration changes
    USE_WEBWORKER.subscribe(useWebWorker => {
      if (useWebWorker !== this.isWebWorkerMode) {
        this.updateService();
      }
    });
  }
  
  private updateService(): void {
    this.isWebWorkerMode = get(USE_WEBWORKER);
    
    if (this.isWebWorkerMode) {
      // Terminate old service if switching
      if (this.currentService === photoProcessingService) {
        this.currentService?.cancelOperations?.();
      }
      
      this.currentService = photoWorkerService;
      console.log('Switched to PhotoWorkerService');
      
      // Set up web worker callbacks
      this.setupWebWorkerCallbacks();
    } else {
      // Terminate web worker if switching
      if (this.currentService === photoWorkerService) {
        this.currentService?.terminate?.();
      }
      
      this.currentService = photoProcessingService;
      console.log('Switched to PhotoProcessingService');
    }
    
    this.isInitialized = false;
  }
  
  private setupWebWorkerCallbacks(): void {
    if (this.currentService !== photoWorkerService) return;
    
    // Set up callbacks for web worker mode
    this.currentService.onPhotosUpdate((photos: any[]) => {
      // Convert to legacy format for compatibility
      const result: AreaFilterResult = {
        hillviewPhotosInArea: photos.filter(p => p.source?.id === 'hillview'),
        mapillaryPhotosInArea: photos.filter(p => p.source?.id === 'mapillary'),
        photosInArea: photos
      };
      
      const callback = this.webWorkerCallbacks.get('filter_area');
      if (callback) {
        callback(result);
      }
    });
    
    this.currentService.onBearingUpdate((result: any) => {
      const callback = this.webWorkerCallbacks.get('update_bearings');
      if (callback) {
        callback(result);
      }
    });
    
    // Also handle distance updates from web worker
    this.currentService.onPhotosUpdate((photos: any[]) => {
      const callback = this.webWorkerCallbacks.get('calculate_distances');
      if (callback) {
        // Web worker includes distance data in photos
        const result = {
          photosInRange: photos.filter(p => p.range_distance !== null && p.range_distance !== undefined)
        };
        callback(result);
      }
    });
  }
  
  async ensureInitialized(): Promise<void> {
    if (this.isInitialized) return;
    
    if (this.isWebWorkerMode && this.currentService.initialize) {
      await this.currentService.initialize();
    }
    
    this.isInitialized = true;
  }
  
  // Legacy PhotoProcessingService methods
  queueAreaFilter(bounds: any, range: number, sourcesConfig: any[]): void {
    if (this.isWebWorkerMode) {
      // Update current center for bearing calculations
      this.currentCenter = {
        lat: (bounds.top_left.lat + bounds.bottom_right.lat) / 2,
        lng: (bounds.top_left.lng + bounds.bottom_right.lng) / 2
      };
      
      this.ensureInitialized().then(() => {
        this.currentService.updateMapBounds?.(bounds);
        this.currentService.updateRange?.(range);
        this.currentService.updateSources?.(sourcesConfig);
      });
    } else {
      this.currentService.queueAreaFilter?.(bounds, range, sourcesConfig);
    }
  }
  
  queueBearingUpdate(bearing: number, photoIds: string[], priority: string = 'high'): void {
    if (this.isWebWorkerMode) {
      this.ensureInitialized().then(() => {
        this.currentService.updateBearing?.(bearing, this.currentCenter);
      });
    } else {
      this.currentService.queueBearingUpdate?.(bearing, photoIds, priority);
    }
  }
  
  queueDistanceCalculation(photoIds: string[], center: any, range: number): void {
    if (this.isWebWorkerMode) {
      this.ensureInitialized().then(() => {
        this.currentService.updateRange?.(range);
        // Distance calculation is handled automatically in web worker
      });
    } else {
      this.currentService.queueDistanceCalculation?.(photoIds, center, range);
    }
  }
  
  onResult(type: string, callback: (result: any) => void): void {
    if (this.isWebWorkerMode) {
      this.webWorkerCallbacks.set(type, callback);
    } else {
      this.currentService.onResult?.(type, callback);
    }
  }
  
  updatePhotoStore(photos: any[]): void {
    if (this.isWebWorkerMode) {
      this.ensureInitialized().then(() => {
        this.currentService.loadPhotos?.(photos);
      });
    } else {
      this.currentService.updatePhotoStore?.(photos);
    }
  }
  
  // New PhotoWorkerService methods (passthrough)
  async initialize(): Promise<void> {
    return this.currentService.initialize?.();
  }
  
  async loadPhotos(photos: any[]): Promise<void> {
    return this.currentService.loadPhotos?.(photos);
  }
  
  async updateMapBounds(bounds: any): Promise<void> {
    return this.currentService.updateMapBounds?.(bounds);
  }
  
  async updateRange(range: number): Promise<void> {
    return this.currentService.updateRange?.(range);
  }
  
  async updateSources(sources: any[]): Promise<void> {
    return this.currentService.updateSources?.(sources);
  }
  
  async updateBearing(bearing: number, center: any): Promise<void> {
    return this.currentService.updateBearing?.(bearing, center);
  }
  
  onPhotosUpdate(callback: (photos: any[]) => void): void {
    return this.currentService.onPhotosUpdate?.(callback);
  }
  
  onBearingUpdate(callback: (result: any) => void): void {
    return this.currentService.onBearingUpdate?.(callback);
  }
  
  getCurrentBearingData(): any | null {
    return this.currentService.getCurrentBearingData?.() || null;
  }
  
  terminate(): void {
    this.currentService.terminate?.();
  }
  
  // Utility methods
  isUsingWebWorker(): boolean {
    return this.isWebWorkerMode;
  }
  
  getQueueStatus(): any {
    if (this.isWebWorkerMode) {
      return { isWebWorker: true, initialized: this.isInitialized };
    } else {
      return this.currentService.getQueueStatus?.() || {};
    }
  }
  
  cancelOperations(type?: string): void {
    if (!this.isWebWorkerMode) {
      this.currentService.cancelOperations?.(type);
    }
  }
}

// Export singleton instance
export const photoProcessingAdapter = new PhotoProcessingAdapter();