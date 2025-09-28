/**
 * Device Source Loader - Loads photos from local device storage
 * Handles local photo files and metadata
 */

import type { PhotoData, Bounds } from '../photoWorkerTypes';
import { BasePhotoSourceLoader, type PhotoSourceCallbacks } from './PhotoSourceLoader';
import { filterPhotosByArea } from '../workerUtils';

export class DeviceSourceLoader extends BasePhotoSourceLoader {
    private photos: PhotoData[] = [];

    constructor(source: any, callbacks: PhotoSourceCallbacks) {
        super(source, callbacks);
    }

    async start(bounds?: Bounds): Promise<void> {
        console.log(`🢄DeviceSourceLoader: Loading device photos from ${this.source.path || 'default location'}`);

        try {
            // For now, device sources are handled by the frontend directly
            // This loader mainly provides the interface compatibility
            // In a future implementation, this could scan local directories
            // or interface with device photo APIs

            // Placeholder for device photo loading logic
            this.photos = [];
            this.isComplete = true;

            const duration = Date.now() - this.startTime;
            
            this.callbacks.enqueueMessage({
                type: 'photosAdded',
                sourceId: this.source.id,
                photos: this.photos,
                duration,
                fromCache: false
            });

            console.log(`🢄DeviceSourceLoader: Loaded ${this.photos.length} photos from device source ${this.source.id}`);

        } catch (error) {
            if (!this.isAborted()) {
                console.error(`🢄DeviceSourceLoader: Error loading device photos:`, error);
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
        return 'DeviceSourceLoader';
    }
}