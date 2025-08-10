/**
 * JSON Source Loader - Loads photos from JSON endpoints
 * Handles its own caching logic since only JSON sources need caching
 */

import type { PhotoData, Bounds } from '../photoWorkerTypes';
import { BasePhotoSourceLoader, type PhotoSourceCallbacks } from './PhotoSourceLoader';
import { filterPhotosByArea } from '../workerUtils';

export interface JsonSourceCallbacks extends PhotoSourceCallbacks {
    getCachedJson?: (sourceId: string) => PhotoData[] | undefined;
    setCachedJson?: (sourceId: string, photos: PhotoData[]) => void;
}

export class JsonSourceLoader extends BasePhotoSourceLoader {
    private callbacks: JsonSourceCallbacks;
    private photos: PhotoData[] = [];

    constructor(source: any, callbacks: JsonSourceCallbacks) {
        super(source, callbacks);
        this.callbacks = callbacks;
    }

    async start(bounds?: Bounds): Promise<void> {
        if (!this.source.url) {
            throw new Error('JSON source missing URL');
        }

        // Check if we have cached data
        const cachedPhotos = this.callbacks.getCachedJson?.(this.source.id);
        if (cachedPhotos) {
            console.log(`JsonSourceLoader: Using cached data for ${this.source.id} (${cachedPhotos.length} photos)`);
            this.photos = [...cachedPhotos];
            const duration = Date.now() - this.startTime;
            
            this.callbacks.enqueueMessage({
                type: 'photosLoaded',
                sourceId: this.source.id,
                photos: this.photos,
                duration,
                fromCache: true
            });
            
            this.isComplete = true;
            return;
        }

        // Load fresh data from URL
        await this.loadFromUrl();
    }

    private async loadFromUrl(): Promise<void> {
        this.abortController = new AbortController();
        
        console.log(`JsonSourceLoader: Loading JSON from ${this.source.url}`);
        console.log(`JsonSourceLoader: Source config:`, JSON.stringify({
            id: this.source.id,
            name: this.source.name,
            type: this.source.type,
            enabled: this.source.enabled,
            url: this.source.url
        }));

        try {
            const response = await fetch(this.source.url, {
                signal: this.abortController.signal
            });

            console.log(`JsonSourceLoader: Response status: ${response.status} ${response.statusText}`);
            console.log(`JsonSourceLoader: Response headers:`, Object.fromEntries([...response.headers.entries()]));

            if (!response.ok) {
                console.error(`JsonSourceLoader: HTTP error ${response.status} ${response.statusText} for ${this.source.url}`);
                throw new Error(`Failed to fetch from ${this.source.url}: ${response.status} ${response.statusText}`);
            }

            const contentLength = response.headers.get('content-length');
            const total = contentLength ? parseInt(contentLength, 10) : undefined;
            let loaded = 0;

            const reader = response.body?.getReader();
            if (!reader) {
                throw new Error('Response body is not readable');
            }

            const chunks: Uint8Array[] = [];

            while (true) {
                this.checkAborted();
                
                const { done, value } = await reader.read();
                if (done) break;

                chunks.push(value);
                loaded += value.length;
                this.callbacks.onProgress?.(loaded, total);
            }

            const decoder = new TextDecoder();
            const jsonText = decoder.decode(new Uint8Array(
                chunks.reduce((acc, chunk) => [...acc, ...chunk], [] as number[])
            ));

            const photos: PhotoData[] = JSON.parse(jsonText);
            
            // Add source reference to each photo
            photos.forEach(photo => {
                photo.source = this.source;
            });

            this.photos = photos;

            // Cache the photos
            this.callbacks.setCachedJson?.(this.source.id, photos);
            this.isComplete = true;

            console.log(`JsonSourceLoader: Loaded ${photos.length} photos from JSON source ${this.source.id}`);

            const duration = Date.now() - this.startTime;
            
            // Send completion message
            this.callbacks.enqueueMessage({
                type: 'photosLoaded',
                sourceId: this.source.id,
                photos: photos,
                duration,
                fromCache: false
            });

        } catch (error) {
            if (!this.isAborted()) {
                console.error(`JsonSourceLoader: Error loading ${this.source.url}:`, error);
                this.callbacks.onError?.(error as Error);
            }
            throw error;
        }
    }

    getAllPhotos(): PhotoData[] {
        return [...this.photos];
    }

    getFilteredPhotos(bounds: Bounds): PhotoData[] {
        return filterPhotosByArea(this.photos, bounds);
    }

    protected getLoaderType(): string {
        return 'JsonSourceLoader';
    }
}