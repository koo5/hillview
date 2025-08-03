/// <reference lib="webworker" />

import type { MapillaryPhoto, StreamMessage } from './mapillaryStreamService';
import type { PhotoData } from './photoWorkerTypes';

export interface MapillaryWorkerCallbacks {
  onPhotosAdded: (photos: PhotoData[]) => void;
  onStreamComplete: () => void;
  onError: (error: string) => void;
}

export class MapillaryWorkerHandler {
  private eventSource: EventSource | null = null;
  private isStreaming = false;
  private photos: PhotoData[] = [];
  private callbacks: MapillaryWorkerCallbacks;
  
  constructor(callbacks: MapillaryWorkerCallbacks) {
    this.callbacks = callbacks;
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
      this.stopStream();
    }
    
    const url = `${backendUrl}/mapillary` +
      `?top_left_lat=${topLeftLat}` +
      `&top_left_lon=${topLeftLon}` +
      `&bottom_right_lat=${bottomRightLat}` +
      `&bottom_right_lon=${bottomRightLon}` +
      `&client_id=${clientId}`;
    
    console.log('Worker: Starting Mapillary stream:', url);
    
    this.eventSource = new EventSource(url);
    this.isStreaming = true;
    
    this.eventSource.onmessage = (event) => {
      try {
        const data: StreamMessage = JSON.parse(event.data);
        this.handleStreamMessage(data);
      } catch (error) {
        console.error('Worker: Error parsing Mapillary stream message:', error);
        this.callbacks.onError('Error parsing stream data');
      }
    };
    
    this.eventSource.onerror = (error) => {
      console.error('Worker: Mapillary stream error:', error);
      this.callbacks.onError('Stream connection error');
      this.stopStream();
    };
    
    this.eventSource.onopen = () => {
      console.log('Worker: Mapillary stream opened');
    };
  }
  
  private handleStreamMessage(data: StreamMessage): void {
    switch (data.type) {
      case 'cached_photos':
        if (data.photos) {
          console.log(`Worker: Received ${data.photos.length} cached Mapillary photos`);
          this.addMapillaryPhotos(data.photos);
        }
        break;
        
      case 'live_photos_batch':
        if (data.photos) {
          console.log(`Worker: Received ${data.photos.length} live Mapillary photos from region ${data.region}`);
          this.addMapillaryPhotos(data.photos);
        }
        break;
        
      case 'stream_complete':
        console.log(`Worker: Mapillary stream complete, total photos: ${data.total_live_photos}`);
        this.callbacks.onStreamComplete();
        this.stopStream();
        break;
        
      case 'cache_status':
        console.log(`Worker: Mapillary cache status - uncached regions: ${data.uncached_regions}`);
        break;
        
      case 'region_complete':
        console.log(`Worker: Mapillary region ${data.region} complete, photos: ${data.photos_count}`);
        break;
        
      case 'error':
        console.error('Worker: Mapillary stream error:', data.message);
        this.callbacks.onError(data.message || 'Unknown stream error');
        break;
        
      default:
        console.warn('Worker: Unknown Mapillary stream message type:', data.type);
    }
  }
  
  private addMapillaryPhotos(newPhotos: MapillaryPhoto[]): void {
    const convertedPhotos: PhotoData[] = newPhotos.map(photo => {
      const lat = photo.geometry.coordinates[1];
      const lng = photo.geometry.coordinates[0];
      
      return {
        id: photo.id,
        lat: lat,
        lng: lng,
        coord: { lat: lat, lng: lng }, // Add coord property for compatibility
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
    
    console.log(`Worker: Added ${convertedPhotos.length} Mapillary photos, total: ${this.photos.length}`);
    
    // Notify the worker about new photos
    this.callbacks.onPhotosAdded(convertedPhotos);
  }
  
  stopStream(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    this.isStreaming = false;
    console.log('Worker: Mapillary stream stopped');
  }
  
  clearPhotos(): void {
    this.photos = [];
    console.log('Worker: Cleared Mapillary photos');
  }
  
  getPhotos(): PhotoData[] {
    return [...this.photos];
  }
  
  getIsStreaming(): boolean {
    return this.isStreaming;
  }
}