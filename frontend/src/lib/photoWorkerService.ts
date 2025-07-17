import { photoWorker } from './photoWorker';
import type { PhotoData, Bounds, SourceConfig, PhotosUpdateData, BearingUpdateData, WorkerError } from './photoWorkerTypes';
import { 
  updatePhotoBearings, 
  sortPhotosByAngularDistance,
  type PhotoWithBearing
} from './photoProcessing';
import { buildNavigationStructure } from './utils/photoNavigationUtils';

export interface BearingResult {
  photoInFront: PhotoData | null;
  photoToLeft: PhotoData | null;
  photoToRight: PhotoData | null;
  photosToLeft: PhotoData[];
  photosToRight: PhotoData[];
  photosInRange: PhotoData[];
}

export class PhotoWorkerService {
  private initialized = false;
  private currentBearing: number = 0;
  private currentCenter: { lat: number; lng: number } = { lat: 0, lng: 0 };
  private currentBounds: Bounds | null = null;
  private onPhotosUpdateCallback: ((photos: PhotoData[]) => void) | null = null;
  private onBearingUpdateCallback: ((result: BearingResult) => void) | null = null;
  private onErrorCallback: ((error: WorkerError) => void) | null = null;
  private lastBearingData: BearingUpdateData | null = null;
  private lastPhotosData: PhotosUpdateData | null = null;

  constructor() {
    this.setupWorkerCallbacks();
  }

  private setupWorkerCallbacks(): void {
    // Handle photos update from worker
    photoWorker.onPhotosUpdate((data: PhotosUpdateData) => {
      this.lastPhotosData = data;
      
      if (this.onPhotosUpdateCallback) {
        this.onPhotosUpdateCallback(data.photos);
      }
    });

    // Handle bearing update from worker
    photoWorker.onBearingUpdate((data: BearingUpdateData) => {
      this.lastBearingData = data;
      
      if (this.onBearingUpdateCallback) {
        // Process bearing data to create navigation structure
        const result = this.processBearingData(data.photosInRange, data.bearing);
        this.onBearingUpdateCallback(result);
      }
    });

    // Handle worker errors
    photoWorker.onError((error: WorkerError) => {
      console.error('PhotoWorkerService: Worker error', error);
      
      if (this.onErrorCallback) {
        this.onErrorCallback(error);
      }
      
      // Attempt recovery on certain errors
      if (error.operation === 'runtime') {
        this.handleWorkerCrash();
      }
    });
  }

  private async handleWorkerCrash(): Promise<void> {
    console.log('PhotoWorkerService: Handling worker crash...');
    
    this.initialized = false;
    
    // Give worker time to restart
    setTimeout(async () => {
      try {
        await this.initialize();
        
        // Reload data if we have it
        if (this.lastPhotosData) {
          await this.loadPhotos(this.lastPhotosData.photos);
        }
        
        console.log('PhotoWorkerService: Recovery successful');
      } catch (error) {
        console.error('PhotoWorkerService: Recovery failed', error);
      }
    }, 2000);
  }

  private processBearingData(photosInRange: PhotoData[], bearing: number): BearingResult {
    if (photosInRange.length === 0) {
      return {
        photoInFront: null,
        photoToLeft: null,
        photoToRight: null,
        photosToLeft: [],
        photosToRight: [],
        photosInRange: []
      };
    }

    // Use main thread for bearing sorting logic as requested
    const withBearings = updatePhotoBearings(photosInRange, bearing);
    const sorted = sortPhotosByAngularDistance(withBearings as PhotoWithBearing[], bearing);
    
    // Use the navigation utility to build the structure
    const navigationResult = buildNavigationStructure(sorted, withBearings);
    
    return {
      ...navigationResult,
      photosInRange: photosInRange
    };
  }

  async initialize(): Promise<void> {
    if (this.initialized) return;
    
    await photoWorker.initialize();
    this.initialized = true;
    console.log('PhotoWorkerService initialized');
  }

  async loadPhotos(photos: PhotoData[]): Promise<void> {
    await this.initialize();
    await photoWorker.loadPhotos(photos);
  }

  async updateMapBounds(bounds: Bounds): Promise<void> {
    await this.initialize();
    this.currentBounds = bounds;
    await photoWorker.updateBounds(bounds);
  }

  getCurrentBounds(): Bounds | null {
    return this.currentBounds;
  }

  async updateRange(range: number): Promise<void> {
    await this.initialize();
    await photoWorker.updateRange(range);
  }

  async updateSources(sources: SourceConfig[]): Promise<void> {
    await this.initialize();
    await photoWorker.updateSources(sources);
  }

  async updateBearing(bearing: number, center: { lat: number; lng: number }): Promise<void> {
    await this.initialize();
    this.currentBearing = bearing;
    this.currentCenter = center;
    await photoWorker.getBearingPhotos(bearing, center);
  }

  async updateConfig(config: { recalculateBearingDistances?: boolean }): Promise<void> {
    await this.initialize();
    await photoWorker.updateConfig(config);
  }

  // Event handlers
  onPhotosUpdate(callback: (photos: PhotoData[]) => void): void {
    this.onPhotosUpdateCallback = callback;
  }

  onBearingUpdate(callback: (result: BearingResult) => void): void {
    this.onBearingUpdateCallback = callback;
  }

  onError(callback: (error: WorkerError) => void): void {
    this.onErrorCallback = callback;
  }

  // Get current state (for components that need immediate data)
  getCurrentBearingData(): BearingResult | null {
    if (!this.lastBearingData) return null;
    return this.processBearingData(this.lastBearingData.photosInRange, this.lastBearingData.bearing);
  }

  getCurrentPhotosData(): PhotosUpdateData | null {
    return this.lastPhotosData;
  }

  getWorkerStatus(): {
    initialized: boolean;
    pendingOperations: number;
    ready: boolean;
  } {
    return photoWorker.getStatus();
  }

  isReady(): boolean {
    return this.initialized && photoWorker.isReady();
  }

  terminate(): void {
    photoWorker.terminate();
    this.initialized = false;
    this.lastBearingData = null;
    this.lastPhotosData = null;
  }
}

// Singleton instance
export const photoWorkerService = new PhotoWorkerService();