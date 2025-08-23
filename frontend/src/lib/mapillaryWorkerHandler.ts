/// <reference lib="webworker" />

import type { MapillaryPhoto, StreamMessage } from './mapillaryStreamService';
import type { PhotoData } from './photoWorkerTypes';

export interface MapillaryStatus {
  isStreaming: boolean;
  currentUrl?: string;
  totalPhotos: number;
  lastRequestTime?: number;
  lastResponseTime?: number;
  lastBounds?: {
    topLeftLat: number;
    topLeftLon: number;
    bottomRightLat: number;
    bottomRightLon: number;
  };
  streamPhase: 'idle' | 'connecting' | 'receiving_cached' | 'receiving_live' | 'complete' | 'error';
  lastError?: string;
  uncachedRegions?: number;
  completedRegions: string[];
}

export interface MapillaryWorkerCallbacks {
  onPhotosAdded: (photos: PhotoData[]) => void;
  onStreamComplete: () => void;
  onError: (error: string) => void;
  onStatusUpdate: (status: MapillaryStatus) => void;
}

export class MapillaryWorkerHandler {
  private eventSource: EventSource | null = null;
  private isStreaming = false;
  private photos: PhotoData[] = [];
  private callbacks: MapillaryWorkerCallbacks;
  
  // Status tracking
  private currentUrl?: string;
  private lastRequestTime?: number;
  private lastResponseTime?: number;
  private lastBounds?: {
    topLeftLat: number;
    topLeftLon: number;
    bottomRightLat: number;
    bottomRightLon: number;
  };
  private streamPhase: 'idle' | 'connecting' | 'receiving_cached' | 'receiving_live' | 'complete' | 'error' = 'idle';
  private lastError?: string;
  private uncachedRegions?: number;
  private completedRegions: string[] = [];
  
  // Photo culling settings
  private readonly MAX_PHOTOS = 2000;
  private currentBounds?: {
    topLeftLat: number;
    topLeftLon: number;
    bottomRightLat: number;
    bottomRightLon: number;
  };
  
  constructor(callbacks: MapillaryWorkerCallbacks) {
    this.callbacks = callbacks;
  }
  
  private emitStatusUpdate(): void {
    const status: MapillaryStatus = {
      isStreaming: this.isStreaming,
      currentUrl: this.currentUrl,
      totalPhotos: this.photos.length,
      lastRequestTime: this.lastRequestTime,
      lastResponseTime: this.lastResponseTime,
      lastBounds: this.lastBounds,
      streamPhase: this.streamPhase,
      lastError: this.lastError,
      uncachedRegions: this.uncachedRegions,
      completedRegions: [...this.completedRegions]
    };
    
    console.log('🢄Worker: Mapillary status update:', status);
    this.callbacks.onStatusUpdate(status);
  }
  
  async startStream(
    topLeftLat: number,
    topLeftLon: number,
    bottomRightLat: number,
    bottomRightLon: number,
    clientId: string,
    backendUrl: string
  ): Promise<void> {
    if (this.isStreaming) {
      console.log('🢄Worker: Stopping previous Mapillary stream before starting new one');
      this.stopStream();
    }
    
    // Update status tracking
    this.lastBounds = { topLeftLat, topLeftLon, bottomRightLat, bottomRightLon };
    this.currentBounds = { topLeftLat, topLeftLon, bottomRightLat, bottomRightLon };
    this.lastRequestTime = Date.now();
    this.lastResponseTime = undefined;
    this.lastError = undefined;
    this.completedRegions = [];
    this.streamPhase = 'connecting';
    
    const url = `${backendUrl}/mapillary` +
      `?top_left_lat=${topLeftLat}` +
      `&top_left_lon=${topLeftLon}` +
      `&bottom_right_lat=${bottomRightLat}` +
      `&bottom_right_lon=${bottomRightLon}` +
      `&client_id=${clientId}`;
    
    this.currentUrl = url;
    console.log('🢄Worker: Starting Mapillary stream:', url);
    this.emitStatusUpdate();
    
    this.eventSource = new EventSource(url);
    this.isStreaming = true;
    this.emitStatusUpdate(); // Emit status update immediately when streaming starts
    
    this.eventSource.onmessage = (event) => {
      try {
        this.lastResponseTime = Date.now();
        const data: StreamMessage = JSON.parse(event.data);
        this.handleStreamMessage(data);
      } catch (error) {
        console.error('🢄Worker: Error parsing Mapillary stream message:', error);
        this.streamPhase = 'error';
        this.lastError = 'Error parsing stream data';
        this.emitStatusUpdate();
        this.callbacks.onError('Error parsing stream data');
      }
    };
    
    this.eventSource.onerror = (error) => {
      console.error('🢄Worker: Mapillary stream error:', error);
      this.streamPhase = 'error';
      this.lastError = 'Stream connection error';
      this.emitStatusUpdate();
      this.callbacks.onError('Stream connection error');
      this.stopStream();
    };
    
    this.eventSource.onopen = () => {
      console.log('🢄Worker: Mapillary stream opened');
      this.streamPhase = 'receiving_cached';
      this.emitStatusUpdate();
    };
  }
  
  private handleStreamMessage(data: StreamMessage): void {
    switch (data.type) {
      case 'cached_photos':
        if (data.photos) {
          console.log(`Worker: Received ${data.photos.length} cached Mapillary photos`);
          this.addMapillaryPhotos(data.photos);
          this.emitStatusUpdate();
        }
        break;
        
      case 'live_photos_batch':
        if (data.photos) {
          console.log(`Worker: Received ${data.photos.length} live Mapillary photos from region ${data.region}`);
          this.streamPhase = 'receiving_live';
          this.addMapillaryPhotos(data.photos);
          this.emitStatusUpdate();
        }
        break;
        
      case 'stream_complete':
        console.log(`Worker: Mapillary stream complete, total photos: ${data.total_live_photos}`);
        this.streamPhase = 'complete';
        this.emitStatusUpdate();
        this.callbacks.onStreamComplete();
        this.stopStream();
        break;
        
      case 'cache_status':
        console.log(`Worker: Mapillary cache status - uncached regions: ${data.uncached_regions}`);
        this.uncachedRegions = data.uncached_regions;
        this.emitStatusUpdate();
        break;
        
      case 'region_complete':
        console.log(`Worker: Mapillary region ${data.region} complete, photos: ${data.photos_count}`);
        if (data.region) {
          this.completedRegions.push(data.region);
          this.emitStatusUpdate();
        }
        break;
        
      case 'error':
        console.error('🢄Worker: Mapillary stream error:', data.message);
        this.streamPhase = 'error';
        this.lastError = data.message || 'Unknown stream error';
        this.emitStatusUpdate();
        this.callbacks.onError(data.message || 'Unknown stream error');
        break;
        
      default:
        console.warn('🢄Worker: Unknown Mapillary stream message type:', data.type);
    }
  }
  
  private addMapillaryPhotos(newPhotos: MapillaryPhoto[]): void {
    const convertedPhotos: PhotoData[] = newPhotos.map(photo => {
      const lat = photo.geometry.coordinates[1];
      const lng = photo.geometry.coordinates[0];
      
      return {
        id: photo.id,
        coord: { lat: lat, lng: lng },
        bearing: photo.computed_compass_angle || photo.compass_angle || 0,
        url: photo.thumb_1024_url || '',
        file: `mapillary_${photo.id}`,
        source_type: 'mapillary',
        altitude: photo.computed_altitude || 0,
        sizes: photo.thumb_1024_url ? {
          1024: {
            url: photo.thumb_1024_url,
            width: 1024,
            height: 768
          },
          full: {
            url: photo.thumb_1024_url,
            width: 1024,
            height: 768
          }
        } : undefined,
        captured_at: photo.captured_at,
        is_pano: photo.is_pano
      };
    });
    
    // Add to our local photos array
    this.photos.push(...convertedPhotos);
    
    // Cull photos if we have too many
    const culledCount = this.cullPhotosIfNeeded();
    
    console.log(`Worker: Added ${convertedPhotos.length} Mapillary photos, total: ${this.photos.length}${culledCount > 0 ? `, culled ${culledCount} photos outside visible area` : ''}`);
    
    // Notify the worker about new photos
    this.callbacks.onPhotosAdded(convertedPhotos);
    
    // Status is updated by caller
  }
  
  private isPhotoInBounds(photo: PhotoData, bounds: { topLeftLat: number; topLeftLon: number; bottomRightLat: number; bottomRightLon: number }): boolean {
    return photo.coord.lat <= bounds.topLeftLat &&
           photo.coord.lat >= bounds.bottomRightLat &&
           photo.coord.lng >= bounds.topLeftLon &&
           photo.coord.lng <= bounds.bottomRightLon;
  }
  
  private cullPhotosIfNeeded(): number {
    if (this.photos.length <= this.MAX_PHOTOS || !this.currentBounds) {
      return 0;
    }
    
    console.log(`Worker: Culling Mapillary photos (${this.photos.length} > ${this.MAX_PHOTOS})`);
    
    // Keep photos that are within current visible bounds
    const photosInBounds: PhotoData[] = [];
    const photosOutsideBounds: PhotoData[] = [];
    
    for (const photo of this.photos) {
      if (this.isPhotoInBounds(photo, this.currentBounds)) {
        photosInBounds.push(photo);
      } else {
        photosOutsideBounds.push(photo);
      }
    }
    
    // If we still have too many photos, keep recent ones within bounds and some outside
    let finalPhotos = [...photosInBounds];
    
    if (finalPhotos.length > this.MAX_PHOTOS * 0.8) {
      // Keep 80% from visible area
      finalPhotos = photosInBounds.slice(-Math.floor(this.MAX_PHOTOS * 0.8));
    }
    
    // Add some photos from outside bounds to reach target count
    const remainingSlots = this.MAX_PHOTOS - finalPhotos.length;
    if (remainingSlots > 0 && photosOutsideBounds.length > 0) {
      // Keep most recent photos from outside bounds
      finalPhotos.push(...photosOutsideBounds.slice(-remainingSlots));
    }
    
    const culledCount = this.photos.length - finalPhotos.length;
    this.photos = finalPhotos;
    
    return culledCount;
  }
  
  stopStream(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    this.isStreaming = false;
    this.currentUrl = undefined;
    if (this.streamPhase !== 'complete' && this.streamPhase !== 'error') {
      this.streamPhase = 'idle';
    }
    console.log('🢄Worker: Mapillary stream stopped');
    this.emitStatusUpdate();
  }
  
  clearPhotos(): void {
    const previousCount = this.photos.length;
    this.photos = [];
    console.log(`Worker: Cleared ${previousCount} Mapillary photos`);
    this.emitStatusUpdate();
  }
  
  getPhotos(): PhotoData[] {
    return [...this.photos];
  }
  
  getIsStreaming(): boolean {
    return this.isStreaming;
  }
  
  getStatus(): MapillaryStatus {
    return {
      isStreaming: this.isStreaming,
      currentUrl: this.currentUrl,
      totalPhotos: this.photos.length,
      lastRequestTime: this.lastRequestTime,
      lastResponseTime: this.lastResponseTime,
      lastBounds: this.lastBounds,
      streamPhase: this.streamPhase,
      lastError: this.lastError,
      uncachedRegions: this.uncachedRegions,
      completedRegions: [...this.completedRegions]
    };
  }
  
  updateBounds(bounds: { topLeftLat: number; topLeftLon: number; bottomRightLat: number; bottomRightLon: number }): void {
    this.currentBounds = bounds;
    
    // Cull photos if we have too many now that bounds changed
    const culledCount = this.cullPhotosIfNeeded();
    
    if (culledCount > 0) {
      console.log(`Worker: Bounds updated, culled ${culledCount} Mapillary photos outside new visible area`);
      this.emitStatusUpdate();
    }
  }
}