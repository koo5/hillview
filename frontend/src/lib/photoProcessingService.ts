import { 
  PhotoProcessingQueue, 
  EVENT_CONFIGS,
  type ProcessingEvent,
  type ProcessingEventType
} from './photoProcessingQueue';
import {
  calculatePhotoDistances,
  updatePhotoBearings,
  sortPhotosByAngularDistance,
  fixupBearings,
  type Bounds,
  type PhotoData,
  type PhotoWithDistance,
  type PhotoWithBearing
} from './photoProcessing';

export interface ProcessingResult {
  type: ProcessingEventType;
  data: any;
}

export interface AreaFilterResult {
  hillviewPhotosInArea: PhotoData[];
  mapillaryPhotosInArea: PhotoData[];
  photosInArea: PhotoData[];
}

export interface DistanceResult {
  photosInRange: PhotoWithDistance[];
}

export interface BearingResult {
  photoInFront: PhotoData | null;
  photoToLeft: PhotoData | null;
  photoToRight: PhotoData | null;
  photosToLeft: PhotoData[];
  photosToRight: PhotoData[];
}

export class PhotoProcessingService {
  private queue: PhotoProcessingQueue;
  private maxPhotosInArea = 500;  // Constant limit for all zoom levels
  private maxPhotosInRange = 100;
  private resultCallbacks: Map<ProcessingEventType, (result: any) => void> = new Map();
  
  // Central photo store to avoid stale data
  private photoStore: Map<string, PhotoData> = new Map();
  
  constructor() {
    this.queue = new PhotoProcessingQueue({
      maxQueueSize: 50,
      onProcess: this.processEvent.bind(this)
    });
  }
  
  // Register callbacks for processing results
  onResult(type: ProcessingEventType, callback: (result: any) => void) {
    this.resultCallbacks.set(type, callback);
  }
  
  // Queue operations - now only pass source configurations, not data
  queueAreaFilter(bounds: Bounds, range: number, sourcesConfig: any[]) {
    this.queue.enqueue('filter_area', {
      bounds,
      range,
      sourcesConfig
    }, {
      priority: 'high',
      mode: 'replace'
    });
  }
  
  queueBearingUpdate(bearing: number, photoIds: string[], priority: 'high' | 'normal' | 'low' = 'high') {
    this.queue.enqueue('update_bearings', {
      bearing,
      photoIds
    }, {
      priority,
      mode: 'replace'
    });
  }
  
  queueDistanceCalculation(photoIds: string[], center: { lat: number; lng: number }, range: number) {
    this.queue.enqueue('calculate_distances', {
      photoIds,
      center,
      range
    }, {
      priority: 'normal',
      mode: 'replace'
    });
  }
  
  // Update photo store
  updatePhotoStore(photos: PhotoData[]) {
    // Update central store
    this.photoStore.clear();
    
    for (const photo of photos) {
      this.photoStore.set(photo.id, photo);
    }
  }
  
  private async processEvent(event: ProcessingEvent) {
    console.log(`Processing ${event.type}`, event.data);
    
    try {
      let result: any;
      
      // Check for abort before processing
      if (event.abortSignal?.aborted) {
        console.log(`Task ${event.type} aborted before start`);
        return;
      }
      
      switch (event.type) {
        case 'filter_area':
          result = await this.filterPhotosInArea(
            event.data.bounds,
            event.data.range,
            event.data.sourcesConfig,
            event.abortSignal
          );
          break;
          
        case 'update_bearings':
          result = await this.updateBearingsAndView(
            event.data.bearing,
            event.data.photoIds,
            event.abortSignal
          );
          break;
          
        case 'calculate_distances':
          result = await this.calculateDistances(
            event.data.photoIds,
            event.data.center,
            event.data.range,
            event.abortSignal
          );
          break;
      }
      
      // Check for abort after processing
      if (event.abortSignal?.aborted) {
        console.log(`Task ${event.type} aborted after processing`);
        return;
      }
      
      // Call registered callback with result
      const callback = this.resultCallbacks.get(event.type);
      if (callback && result) {
        callback(result);
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.log(`Task ${event.type} aborted`);
      } else {
        console.error(`Error processing ${event.type}:`, error);
      }
    }
  }
  
  private async filterPhotosInArea(
    bounds: Bounds, 
    range: number,
    sourcesConfig: any[],
    abortSignal?: AbortSignal
  ): Promise<AreaFilterResult> {
    const startTime = performance.now();
    
    const hillviewEnabled = sourcesConfig.find(s => s.id === 'hillview')?.enabled ?? false;
    const mapillaryEnabled = sourcesConfig.find(s => s.id === 'mapillary')?.enabled ?? false;
    
    let hillviewFiltered: PhotoData[] = [];
    let mapillaryFiltered: PhotoData[] = [];
    
    // Early exit if no photos in store
    if (this.photoStore.size === 0) {
      console.log('No photos in store, skipping filter');
      return {
        hillviewPhotosInArea: [],
        mapillaryPhotosInArea: [],
        photosInArea: []
      };
    }
    
    // Normalize longitudes for display
    const normalizeLng = (lng: number) => {
      while (lng > 180) lng -= 360;
      while (lng < -180) lng += 360;
      return lng;
    };
    
    console.log(`Filtering photos in bounds, range: ${range}m`, {
      top_left: `${bounds.top_left.lat}, ${bounds.top_left.lng}`,
      bottom_right: `${bounds.bottom_right.lat}, ${bounds.bottom_right.lng}`,
      top_left_normalized: `${bounds.top_left.lat}, ${normalizeLng(bounds.top_left.lng)}`,
      bottom_right_normalized: `${bounds.bottom_right.lat}, ${normalizeLng(bounds.bottom_right.lng)}`,
      width: bounds.bottom_right.lng - bounds.top_left.lng,
      height: bounds.top_left.lat - bounds.bottom_right.lat,
      crosses_dateline: normalizeLng(bounds.top_left.lng) > normalizeLng(bounds.bottom_right.lng),
      raw_lng_values: {
        tl: bounds.top_left.lng,
        br: bounds.bottom_right.lng
      }
    });
    
    // Filter hillview photos directly
    if (hillviewEnabled) {
      let hillviewPhotos: PhotoData[] = [];
      let checked = 0;
      
      // Collect ALL photos in bounds first
      let outOfBounds = 0;
      const allHillviewInBounds: PhotoData[] = [];
      
      for (const photo of this.photoStore.values()) {
        checked++;
        
        // Yield every 100 photos to prevent blocking
        if (checked % 100 === 0) {
          await new Promise(resolve => setTimeout(resolve, 0));
          
          if (abortSignal?.aborted) {
            const error = new Error('Aborted');
            error.name = 'AbortError';
            throw error;
          }
        }
        
        if (photo.source?.id === 'hillview') {
          if (this.isInBounds(photo, bounds)) {
            allHillviewInBounds.push(photo);
          } else {
            outOfBounds++;
            // Log first few out of bounds photos for debugging
            if (outOfBounds <= 3) {
              const normalizeLng = (lng: number) => {
                while (lng > 180) lng -= 360;
                while (lng < -180) lng += 360;
                return lng;
              };
              console.log(`Photo out of bounds: ${photo.coord.lat}, ${photo.coord.lng} (normalized: ${normalizeLng(photo.coord.lng)})`);
            }
          }
        }
      }
      
      // Separate user/device photos from regular photos first
      const userPhotos = allHillviewInBounds.filter(p => p.isUserPhoto);
      const devicePhotos = allHillviewInBounds.filter(p => p.isDevicePhoto);
      const regularPhotos = allHillviewInBounds.filter(p => !p.isUserPhoto && !p.isDevicePhoto);
      
      // Always include all user and device photos
      hillviewFiltered = [...userPhotos, ...devicePhotos];
      
      // Calculate remaining slots for regular photos
      const remainingSlots = this.maxPhotosInArea - hillviewFiltered.length;
      
      if (remainingSlots > 0 && regularPhotos.length > 0) {
        if (regularPhotos.length <= remainingSlots) {
          // If we have room for all regular photos, add them all
          hillviewFiltered.push(...regularPhotos);
        } else {
          // Sample regular photos evenly by bearing
          regularPhotos.sort((a, b) => a.bearing - b.bearing);
          const step = regularPhotos.length / remainingSlots;
          for (let i = 0; i < remainingSlots; i++) {
            const index = Math.floor(i * step);
            hillviewFiltered.push(regularPhotos[index]);
          }
        }
      }
      
      console.log(`Hillview: ${hillviewFiltered.length} photos (${userPhotos.length} user, ${devicePhotos.length} device, ${hillviewFiltered.length - userPhotos.length - devicePhotos.length} regular) from ${allHillviewInBounds.length} in bounds, ${outOfBounds} out of bounds from ${checked} checked`);
    }
    
    // Filter mapillary photos
    if (mapillaryEnabled) {
      const mapillaryPhotos: PhotoData[] = [];
      
      for (const photo of this.photoStore.values()) {
        if (photo.source?.id === 'mapillary' && this.isInBounds(photo, bounds)) {
          mapillaryPhotos.push(photo);
          
          // Early exit if we have enough
          if (mapillaryPhotos.length >= this.maxPhotosInArea) {
            break;
          }
        }
      }
      
      mapillaryFiltered = mapillaryPhotos;
    }
    
    // Combine and deduplicate by ID
    const combinedMap = new Map<string, PhotoData>();
    
    // Add hillview photos first
    for (const photo of hillviewFiltered) {
      combinedMap.set(photo.id, photo);
    }
    
    // Add mapillary photos (won't overwrite existing IDs)
    for (const photo of mapillaryFiltered) {
      if (!combinedMap.has(photo.id)) {
        combinedMap.set(photo.id, photo);
      }
    }
    
    // Convert back to array
    const combined = Array.from(combinedMap.values());
    fixupBearings(combined);
    
    console.log(`Filtered photos in ${performance.now() - startTime}ms`);
    
    return {
      hillviewPhotosInArea: hillviewFiltered,
      mapillaryPhotosInArea: mapillaryFiltered,
      photosInArea: combined
    };
  }
  
  private async calculateDistances(
    photoIds: string[],
    center: { lat: number; lng: number },
    range: number,
    abortSignal?: AbortSignal
  ): Promise<DistanceResult> {
    // Get photos from store
    const photos: PhotoData[] = [];
    for (const id of photoIds) {
      const photo = this.photoStore.get(id);
      if (photo) {
        photos.push(photo);
      }
    }
    
    const withDistances = calculatePhotoDistances(photos, center, range)
      .slice(0, this.maxPhotosInRange);
    
    return {
      photosInRange: withDistances
    };
  }
  
  private async updateBearingsAndView(
    currentBearing: number,
    photoIds: string[],
    abortSignal?: AbortSignal
  ): Promise<BearingResult> {
    const startTime = performance.now();
    
    // Get photos from store
    const photosInRange: PhotoData[] = [];
    for (const id of photoIds) {
      const photo = this.photoStore.get(id);
      if (photo) {
        photosInRange.push(photo);
      }
    }
    
    // Update bearing info
    const withBearings = updatePhotoBearings(photosInRange, currentBearing);
    
    if (photosInRange.length === 0) {
      return {
        photoInFront: null,
        photoToLeft: null,
        photoToRight: null,
        photosToLeft: [],
        photosToRight: []
      };
    }
    
    // Sort and find photos by direction
    const sorted = sortPhotosByAngularDistance(withBearings as PhotoWithBearing[], currentBearing);
    const front = sorted[0];
    const idx = withBearings.findIndex(p => p.id === front.id);
    
    let result: BearingResult = {
      photoInFront: null,
      photoToLeft: null,
      photoToRight: null,
      photosToLeft: [],
      photosToRight: []
    };
    
    if (idx !== -1) {
      const leftIdx = (idx - 1 + withBearings.length) % withBearings.length;
      const rightIdx = (idx + 1) % withBearings.length;
      
      result.photoInFront = front;
      result.photoToLeft = withBearings[leftIdx];
      result.photoToRight = withBearings[rightIdx];
      
      // Build arrays for left and right
      const phsl: PhotoData[] = [];
      const phsr: PhotoData[] = [];
      
      for (let i = 1; i < 8 && i < withBearings.length / 2; i++) {
        const leftPhotoIdx = (idx - i + withBearings.length * 2) % withBearings.length;
        const rightPhotoIdx = (idx + i) % withBearings.length;
        
        const leftPhoto = withBearings[leftPhotoIdx];
        const rightPhoto = withBearings[rightPhotoIdx];
        
        if (leftPhoto && !phsl.includes(leftPhoto) && !phsr.includes(leftPhoto)) {
          phsl.push(leftPhoto);
        }
        if (rightPhoto && !phsl.includes(rightPhoto) && !phsr.includes(rightPhoto)) {
          phsr.push(rightPhoto);
        }
      }
      
      phsl.reverse();
      result.photosToLeft = phsl;
      result.photosToRight = phsr;
    }
    
    console.log(`Updated bearings in ${performance.now() - startTime}ms`);
    return result;
  }
  
  private isInBounds(photo: PhotoData, bounds: Bounds): boolean {
    // Add some padding to account for edge cases and rounding
    const latPadding = (bounds.top_left.lat - bounds.bottom_right.lat) * 0.1;
    const lngPadding = Math.abs(bounds.bottom_right.lng - bounds.top_left.lng) * 0.1;
    
    const inLat = photo.coord.lat <= bounds.top_left.lat + latPadding && 
                  photo.coord.lat >= bounds.bottom_right.lat - latPadding;
    
    // Normalize longitudes to [-180, 180] range
    const normalizeLng = (lng: number) => {
      while (lng > 180) lng -= 360;
      while (lng < -180) lng += 360;
      return lng;
    };
    
    const photoLng = normalizeLng(photo.coord.lng);
    const leftLng = normalizeLng(bounds.top_left.lng);
    const rightLng = normalizeLng(bounds.bottom_right.lng);
    
    // Handle longitude wrapping at international date line
    let inLng: boolean;
    if (leftLng > rightLng) {
      // Bounds cross the date line
      inLng = photoLng >= leftLng - lngPadding || 
              photoLng <= rightLng + lngPadding;
    } else {
      // Normal bounds
      inLng = photoLng >= leftLng - lngPadding && 
              photoLng <= rightLng + lngPadding;
    }
    
    return inLat && inLng;
  }
  
  getQueueStatus() {
    return this.queue.getStatus();
  }
  
  // Cancel pending operations
  cancelOperations(type?: ProcessingEventType) {
    if (type) {
      this.queue.cancel(type);
    }
  }
}

// Singleton instance
export const photoProcessingService = new PhotoProcessingService();