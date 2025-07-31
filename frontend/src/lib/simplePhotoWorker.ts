import type { PhotoData, Bounds, SourceConfig } from './types/photoTypes';
import { spatialState, sources, photosInArea, photosInRange, photoInFront, photoToLeft, photoToRight } from './mapState';
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
      
      console.log('SimplePhotoWorker: Initialized successfully');
      
      // Set up reactive subscriptions
      this.setupReactivity();
      
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
        photosInArea.set(response.data.photos || []);
        break;
        
      case 'bearingUpdate':
        // Update navigation photos (bearing-based filtering result)
        photosInRange.set(response.data.photosInRange || []);
        
        // Update navigation structure
        if (response.data.navigation) {
          photoInFront.set(response.data.navigation.photoInFront || null);
          photoToLeft.set(response.data.navigation.photoToLeft || null);
          photoToRight.set(response.data.navigation.photoToRight || null);
        }
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

    // React to source changes - triggers photo filtering  
    sources.subscribe(async (sourceList) => {
      if (!this.isInitialized) return;
      
      try {
        await this.sendMessage('updateSources', { sources: sourceList });
        console.log('SimplePhotoWorker: Updated sources');
      } catch (error) {
        console.error('SimplePhotoWorker: Failed to update sources', error);
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

  async updateBearingAndCenter(bearing: number, center: { lat: number; lng: number }): Promise<void> {
    await this.sendMessage('getPhotosInRange', { bearing, center });
  }

  terminate(): void {
    if (this.worker) {
      this.worker.terminate();
      this.worker = null;
      this.isInitialized = false;
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