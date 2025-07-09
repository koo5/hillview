import type { 
  WorkerMessage, 
  WorkerResponse, 
  PhotoData, 
  Bounds, 
  SourceConfig,
  PhotosUpdateData,
  BearingUpdateData,
  WorkerError
} from './photoWorkerTypes';

export type { PhotoData, Bounds, SourceConfig } from './photoWorkerTypes';

// Web Worker wrapper class with improved error handling
class PhotoWorkerManager {
  private worker: Worker | null = null;
  private messageId = 0;
  private pendingMessages = new Map<string, { 
    resolve: Function; 
    reject: Function; 
    timeout: NodeJS.Timeout;
    operation: string;
  }>();
  private onPhotosUpdateCallback: ((data: PhotosUpdateData) => void) | null = null;
  private onBearingUpdateCallback: ((data: BearingUpdateData) => void) | null = null;
  private onErrorCallback: ((error: WorkerError) => void) | null = null;
  private isInitialized = false;
  private initializationPromise: Promise<void> | null = null;
  private workerUrl: string | null = null;

  constructor() {}

  async initialize(): Promise<void> {
    // Return existing initialization if in progress
    if (this.initializationPromise) {
      return this.initializationPromise;
    }

    // Already initialized
    if (this.worker && this.isInitialized) {
      return;
    }

    this.initializationPromise = this.createWorker();
    
    try {
      await this.initializationPromise;
    } catch (error) {
      this.initializationPromise = null;
      throw error;
    }
    
    return this.initializationPromise;
  }

  private async createWorker(): Promise<void> {
    try {
      // Terminate existing worker if any
      if (this.worker) {
        this.terminate();
      }

      // Create worker using Vite's worker import syntax
      // This will be properly bundled by Vite
      this.worker = new Worker(
        new URL('./photo.worker.ts', import.meta.url),
        { type: 'module' }
      );

      this.setupWorkerHandlers();

      // Initialize worker
      await this.sendMessage('init', undefined, 'initialize');
      this.isInitialized = true;
      
      console.log('PhotoWorker: Initialized successfully');
    } catch (error) {
      console.error('PhotoWorker: Failed to initialize', error);
      this.handleWorkerError({
        message: 'Failed to initialize worker',
        operation: 'initialize',
        timestamp: Date.now()
      });
      throw error;
    }
  }

  private setupWorkerHandlers(): void {
    if (!this.worker) return;

    this.worker.onmessage = (e: MessageEvent<WorkerResponse>) => {
      const response = e.data;
      
      // Handle automatic updates
      if (response.id === 'auto' || response.id === 'error') {
        this.handleAutomaticMessage(response);
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
      console.error('PhotoWorker: Worker error', error);
      this.handleWorkerError({
        message: error.message || 'Worker crashed',
        operation: 'runtime',
        timestamp: Date.now()
      });
      
      // Attempt to restart worker
      this.restartWorker();
    };
  }

  private handleAutomaticMessage(response: WorkerResponse): void {
    switch (response.type) {
      case 'photosUpdate':
        if (this.onPhotosUpdateCallback && response.data) {
          this.onPhotosUpdateCallback({
            photos: response.data.photos || [],
            hillviewCount: response.data.hillviewCount || 0,
            mapillaryCount: response.data.mapillaryCount || 0
          });
        }
        break;
        
      case 'bearingUpdate':
        if (this.onBearingUpdateCallback && response.data) {
          this.onBearingUpdateCallback({
            photosInRange: response.data.photosInRange || [],
            bearing: response.data.bearing || 0
          });
        }
        break;
        
      case 'error':
        if (response.error) {
          this.handleWorkerError(response.error);
        }
        break;
    }
  }

  private handleWorkerError(error: WorkerError): void {
    console.error('PhotoWorker: Error', error);
    
    if (this.onErrorCallback) {
      this.onErrorCallback(error);
    }
    
    // Cancel all pending operations
    for (const [id, pending] of this.pendingMessages.entries()) {
      clearTimeout(pending.timeout);
      pending.reject(new Error(`Worker error: ${error.message}`));
    }
    this.pendingMessages.clear();
  }

  private async restartWorker(): Promise<void> {
    console.log('PhotoWorker: Attempting to restart worker...');
    
    this.isInitialized = false;
    this.initializationPromise = null;
    
    // Wait a bit before restarting
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    try {
      await this.initialize();
      console.log('PhotoWorker: Restarted successfully');
    } catch (error) {
      console.error('PhotoWorker: Failed to restart', error);
    }
  }

  private async sendMessage(
    type: WorkerMessage['type'], 
    data?: WorkerMessage['data'],
    operation: string = type
  ): Promise<any> {
    if (!this.worker) {
      throw new Error('Worker not initialized');
    }

    const id = `msg_${++this.messageId}`;
    
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pendingMessages.delete(id);
        reject(new Error(`Worker timeout: ${operation}`));
      }, 30000);

      this.pendingMessages.set(id, {
        resolve,
        reject,
        timeout,
        operation
      });

      this.worker!.postMessage({ id, type, data } as WorkerMessage);
    });
  }

  // Public API with error handling
  async loadPhotos(photos: PhotoData[]): Promise<void> {
    try {
      await this.ensureInitialized();
      await this.sendMessage('loadPhotos', { photos }, 'loadPhotos');
    } catch (error) {
      console.error('PhotoWorker: Failed to load photos', error);
      throw error;
    }
  }

  async updateBounds(bounds: Bounds): Promise<void> {
    try {
      await this.ensureInitialized();
      await this.sendMessage('updateBounds', { bounds }, 'updateBounds');
    } catch (error) {
      console.error('PhotoWorker: Failed to update bounds', error);
      throw error;
    }
  }

  async updateRange(range: number): Promise<void> {
    try {
      await this.ensureInitialized();
      await this.sendMessage('updateRange', { range }, 'updateRange');
    } catch (error) {
      console.error('PhotoWorker: Failed to update range', error);
      throw error;
    }
  }

  async updateSources(sources: SourceConfig[]): Promise<void> {
    try {
      await this.ensureInitialized();
      await this.sendMessage('updateSources', { sources }, 'updateSources');
    } catch (error) {
      console.error('PhotoWorker: Failed to update sources', error);
      throw error;
    }
  }

  async getBearingPhotos(bearing: number, center: { lat: number; lng: number }): Promise<void> {
    try {
      await this.ensureInitialized();
      await this.sendMessage('getBearingPhotos', { bearing, center }, 'getBearingPhotos');
    } catch (error) {
      console.error('PhotoWorker: Failed to get bearing photos', error);
      throw error;
    }
  }

  private async ensureInitialized(): Promise<void> {
    if (!this.isInitialized) {
      await this.initialize();
    }
  }

  // Event handlers
  onPhotosUpdate(callback: (data: PhotosUpdateData) => void): void {
    this.onPhotosUpdateCallback = callback;
  }

  onBearingUpdate(callback: (data: BearingUpdateData) => void): void {
    this.onBearingUpdateCallback = callback;
  }

  onError(callback: (error: WorkerError) => void): void {
    this.onErrorCallback = callback;
  }

  // Lifecycle methods
  terminate(): void {
    if (this.worker) {
      // Cancel all pending operations
      for (const [id, pending] of this.pendingMessages.entries()) {
        clearTimeout(pending.timeout);
        pending.reject(new Error('Worker terminated'));
      }
      this.pendingMessages.clear();
      
      // Terminate worker
      this.worker.terminate();
      this.worker = null;
      this.isInitialized = false;
      this.initializationPromise = null;
    }
  }

  isReady(): boolean {
    return this.isInitialized && this.worker !== null;
  }

  getStatus(): {
    initialized: boolean;
    pendingOperations: number;
    ready: boolean;
  } {
    return {
      initialized: this.isInitialized,
      pendingOperations: this.pendingMessages.size,
      ready: this.isReady()
    };
  }
}

// Singleton instance
export const photoWorker = new PhotoWorkerManager();