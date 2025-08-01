import type { PhotoData, Bounds, SourceConfig } from './photoWorkerTypes';
import { spatialState, visualState, photosInArea, photosInRange, photoInFront, photoToLeft, photoToRight } from './mapState';
import { sources } from './data.svelte';
import { geoPicsUrl } from './config';
import { get } from 'svelte/store';

/**
 * Simplified direct worker communication
 * No adapter layers - just direct message passing
 */
class SimplePhotoWorker {
  private worker: Worker | null = null;
  private messageId = 0;
  private pendingMessages = new Map<string, { resolve: Function; reject: Function; timeout: NodeJS.Timeout }>();
  private isInitialized = false;
  private lastBearing: number | null = null;

  async initialize(): Promise<void> {
    if (this.worker && this.isInitialized) return;

    try {
      // Create worker directly
      this.worker = new Worker(
        new URL('./photo.worker.ts', import.meta.url),
        { type: 'module' }
      );

      this.setupWorkerHandlers();
      
      // Initialize worker
      await this.sendMessage('init', undefined);
      this.isInitialized = true;
      
      // Send configuration including geoPicsUrl
      await this.sendMessage('updateConfig', { 
        config: { 
          geoPicsUrl: geoPicsUrl || 'http://localhost:8212' 
        } 
      });
      
      console.log('SimplePhotoWorker: Initialized successfully with geoPicsUrl:', geoPicsUrl);
      
      // Set up reactive subscriptions
      this.setupReactivity();
      
      // Test: Check initial sources
      const initialSources = get(sources);
      console.log('SimplePhotoWorker: Initial sources on startup:', initialSources.map(s => ({ 
        id: s.id, 
        type: s.type, 
        enabled: s.enabled, 
        url: s.url,
        keys: Object.keys(s),
        JSON: JSON.stringify(s)
      })));
      
    } catch (error) {
      console.error('SimplePhotoWorker: Failed to initialize', error);
      throw error;
    }
  }

  private setupWorkerHandlers(): void {
    if (!this.worker) return;

    this.worker.onmessage = (e: MessageEvent) => {
      const response = e.data;
      
      // Handle automatic updates from worker
      if (response.id === 'auto') {
        this.handleWorkerUpdate(response);
        return;
      }
      
      // Handle responses to requests
      const pending = this.pendingMessages.get(response.id);
      if (pending) {
        clearTimeout(pending.timeout);
        this.pendingMessages.delete(response.id);
        
        if (response.type === 'error') {
          pending.reject(new Error(response.error?.message || 'Unknown error'));
        } else {
          pending.resolve(response.data);
        }
      }
    };

    this.worker.onerror = (error: ErrorEvent) => {
      console.error('SimplePhotoWorker: Worker error', error);
      // Clear all pending messages
      for (const [id, pending] of this.pendingMessages.entries()) {
        clearTimeout(pending.timeout);
        pending.reject(new Error('Worker crashed'));
      }
      this.pendingMessages.clear();
    };
  }

  private handleWorkerUpdate(response: any): void {
    switch (response.type) {
      case 'photosUpdate':
        // Update photos in area (spatial filtering result)
        const areaPhotos = response.data.photos || [];
        console.log(`SimplePhotoWorker: Updated photosInArea count: ${areaPhotos.length}`);
        photosInArea.set(areaPhotos);
        break;
        
      case 'rangeUpdate':
        // Update navigation photos (range-based filtering result)
        const rangePhotos = response.data.photosInRange || [];
        console.log(`SimplePhotoWorker: Updated photosInRange count: ${rangePhotos.length}`);
        photosInRange.set(rangePhotos);
        break;
        
      case 'bearingUpdate':
        // Update photos with bearing colors
        const photosWithColors = response.data.photos || [];
        console.log(`SimplePhotoWorker: Updated bearing colors for ${photosWithColors.length} photos`);
        photosInArea.set(photosWithColors);
        break;
        
      case 'error':
        console.error('SimplePhotoWorker: Worker error', response.error);
        break;
    }
  }

  private setupReactivity(): void {
    // React to spatial changes - triggers photo filtering
    spatialState.subscribe(async (spatial) => {
      if (!this.isInitialized || !spatial.bounds) return;
      
      try {
        await this.sendMessage('updateBounds', { bounds: spatial.bounds });
        console.log('SimplePhotoWorker: Updated spatial bounds');
      } catch (error) {
        console.error('SimplePhotoWorker: Failed to update bounds', error);
      }
    });

    // React to source changes - triggers photo loading and filtering  
    sources.subscribe(async (sourceList) => {
      if (!this.isInitialized) return;
      
      try {
        // Convert to plain objects for worker serialization
        const plainSources = sourceList.map(s => {
          console.log('SimplePhotoWorker: Source before conversion:', { id: s.id, type: s.type, enabled: s.enabled, url: s.url });
          const plain = {
            id: s.id,
            name: s.name,
            type: s.type,
            enabled: s.enabled,
            url: s.url,
            path: s.path,
            color: s.color
          };
          console.log('SimplePhotoWorker: Plain source after conversion:', JSON.stringify(plain));
          return plain;
        });
        
        // First load photos from sources
        const enabledSources = plainSources.filter(s => s.enabled);
        if (enabledSources.length > 0) {
          console.log('SimplePhotoWorker: Loading photos from sources:', enabledSources.map(s => s.id));
          console.log('SimplePhotoWorker: Sending plain sources to worker:', plainSources);
          await this.loadFromSources(plainSources);
        }
        
        // Then update source configuration for filtering
        await this.sendMessage('updateSources', { sources: plainSources });
        console.log('SimplePhotoWorker: Updated sources');
        
        // Trigger initial range update after sources are loaded
        const currentSpatial = get(spatialState);
        if (currentSpatial.center) {
          console.log('SimplePhotoWorker: Triggering initial range update');
          // First set the range in the worker
          await this.updateRange(currentSpatial.range);
          // Then update photos in range
          await this.updatePhotosInRange({
            lat: currentSpatial.center.lat,
            lng: currentSpatial.center.lng
          });
        }
      } catch (error) {
        console.error('SimplePhotoWorker: Failed to update sources', error);
      }
    });

    // React to spatial state changes (map center/range) - triggers range updates
    spatialState.subscribe(async (spatial) => {
      if (!this.isInitialized || !spatial.center) return;
      
      try {
        console.log(`SimplePhotoWorker: Spatial state changed, updating range with center: ${spatial.center.lat.toFixed(4)}, ${spatial.center.lng.toFixed(4)}, range: ${spatial.range}m`);
        // First update the range in the worker
        await this.updateRange(spatial.range);
        // Then update photos in range with new center
        await this.updatePhotosInRange({ 
          lat: spatial.center.lat, 
          lng: spatial.center.lng 
        });
      } catch (error) {
        console.error('SimplePhotoWorker: Failed to update photos in range after spatial change', error);
      }
    });

    // React to visual state changes (bearing) - triggers bearing color updates
    visualState.subscribe(async (visual) => {
      if (!this.isInitialized) return;
      
      // Skip update if bearing hasn't changed
      if (this.lastBearing === visual.bearing) {
        return;
      }
      
      try {
        console.log(`SimplePhotoWorker: Bearing changed from ${this.lastBearing}° to ${visual.bearing}°, updating colors`);
        this.lastBearing = visual.bearing;
        await this.updateBearingColors(visual.bearing);
      } catch (error) {
        console.error('SimplePhotoWorker: Failed to update bearing colors', error);
      }
    });
  }

  private async sendMessage(type: string, data?: any): Promise<any> {
    if (!this.worker) {
      throw new Error('Worker not initialized');
    }

    const id = `msg_${++this.messageId}`;
    
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pendingMessages.delete(id);
        reject(new Error(`Worker timeout: ${type}`));
      }, 10000); // 10 second timeout

      this.pendingMessages.set(id, { resolve, reject, timeout });
      this.worker!.postMessage({ id, type, data });
    });
  }

  // Public API
  async loadPhotos(photos: PhotoData[]): Promise<void> {
    await this.sendMessage('loadPhotos', { photos });
  }

  async loadFromSources(sources: SourceConfig[]): Promise<void> {
    await this.sendMessage('loadFromSources', { sources });
  }

  async updateRange(range: number): Promise<void> {
    await this.sendMessage('updateRange', { range });
  }

  async updatePhotosInRange(center: { lat: number; lng: number }): Promise<void> {
    await this.sendMessage('getPhotosInRange', { center });
  }

  async updateBearingColors(bearing: number): Promise<void> {
    await this.sendMessage('updateBearingColors', { bearing });
  }

  terminate(): void {
    if (this.worker) {
      this.worker.terminate();
      this.worker = null;
      this.isInitialized = false;
      this.lastBearing = null;
    }
    
    // Clear pending messages
    for (const [id, pending] of this.pendingMessages.entries()) {
      clearTimeout(pending.timeout);
      pending.reject(new Error('Worker terminated'));
    }
    this.pendingMessages.clear();
  }

  isReady(): boolean {
    return this.isInitialized && this.worker !== null;
  }
}

// Global instance
export const simplePhotoWorker = new SimplePhotoWorker();