/**
 * Base interface for all photo source loaders
 * Each source type (JSON, stream, device) implements this interface
 */

import type { PhotoData, SourceConfig, Bounds } from '../photoWorkerTypes';

export interface PhotoSourceCallbacks {
    onProgress?: (loaded: number, total?: number) => void;
    onError?: (error: Error) => void;
    enqueueMessage: (message: any) => void;
    getValidToken: (forceRefresh?: boolean) => Promise<string | null>;
}

export interface PhotoSourceLoader {
    /**
     * Start loading photos from this source
     */
    start(bounds?: Bounds): Promise<void>;
    
    /**
     * Cancel the loading operation
     */
    cancel(): void;
    
    /**
     * Check if the operation was cancelled
     */
    isAborted(): boolean;
    
    /**
     * Check if loading is complete
     */
    isFinished(): boolean;
    
    /**
     * Check if currently loading
     */
    isLoading(): boolean;
    
    /**
     * Get loading duration in milliseconds
     */
    getDuration(): number;
    
    /**
     * Get the source configuration
     */
    getSource(): SourceConfig;
    
    /**
     * Get all loaded photos
     */
    getAllPhotos(): PhotoData[];
    
    /**
     * Get photos filtered by bounds
     */
    getFilteredPhotos(bounds: Bounds): PhotoData[];
}

export abstract class BasePhotoSourceLoader implements PhotoSourceLoader {
    protected source: SourceConfig;
    protected callbacks: PhotoSourceCallbacks;
    protected startTime: number;
    protected isComplete: boolean = false;
    protected abortController?: AbortController;

    constructor(source: SourceConfig, callbacks: PhotoSourceCallbacks) {
        this.source = source;
        this.callbacks = callbacks;
        this.startTime = Date.now();
    }

    abstract start(bounds?: Bounds): Promise<void>;
    
    cancel(): void {
        console.log(`${this.getLoaderType()}: Cancelling load for ${this.source.id}`);
        if (this.abortController && !this.abortController.signal.aborted) {
            this.abortController.abort();
        }
    }

    isAborted(): boolean {
        return this.abortController?.signal.aborted || false;
    }

    isFinished(): boolean {
        return this.isComplete;
    }

    isLoading(): boolean {
        return !this.isComplete && !this.isAborted();
    }

    getDuration(): number {
        return Date.now() - this.startTime;
    }

    getSource(): SourceConfig {
        return this.source;
    }

    abstract getAllPhotos(): PhotoData[];
    abstract getFilteredPhotos(bounds: Bounds): PhotoData[];

    protected checkAborted(): void {
        if (this.abortController?.signal.aborted) {
            throw new Error('Loading cancelled');
        }
    }

    protected abstract getLoaderType(): string;
}