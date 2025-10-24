/**
 * Photo Operations - Pure Business Logic
 */

import type { PhotoData, SourceConfig, Bounds } from './photoWorkerTypes';
import { PhotoSourceFactory, type PhotoSourceOptions } from './sources/PhotoSourceFactory';
import type { PhotoSourceLoader, PhotoSourceCallbacks } from './sources/PhotoSourceLoader';
import { filterPhotosByArea } from './workerUtils';
import { MAX_PHOTOS_IN_AREA } from './photoWorkerConstants';

// Import worker version for validation
declare const __WORKER_VERSION__: string;

export interface OperationCallbacks {
    shouldAbort: (processId: string) => boolean;
    postMessage: (message: any) => void;
    updatePhotosInArea: (photos: PhotoData[]) => void;
    updatePhotosInRange: (photos: PhotoData[]) => void;
    getPhotosInArea: () => PhotoData[];
    getPhotosInRange: () => PhotoData[];
    sendPhotosInAreaUpdate: () => void;
    sendPhotosInRangeUpdate: () => void;
    getValidToken: () => Promise<string | null>;
}

interface SourceCache {
    photos: PhotoData[];
    isComplete: boolean; // true = no more photos available, false = partial load (stream has "next" link)
    cachedBounds?: Bounds; // The geographic bounds that were completely cached
}

export class PhotoOperations {
    private loadingProcesses = new Map<string, PhotoSourceLoader>();
    private sourceCache = new Map<string, SourceCache>(); // Cache for each source
    private maxPhotosInArea: number = MAX_PHOTOS_IN_AREA;

    constructor() {}

    setMaxPhotosInArea(maxPhotos: number): void {
        this.maxPhotosInArea = maxPhotos;
    }

    /**
     * Clean up all resources - call this when worker is being terminated
     */
    cleanup(): void {
        console.log('🢄PhotoOperations: Cleaning up all resources');
        // Cancel all active loading processes
        for (const [sourceId, process] of this.loadingProcesses.entries()) {
            console.log(`🢄PhotoOperations: Cancelling loader for ${sourceId}`);
            process.cancel();
        }
        this.loadingProcesses.clear();

        // Clear all caches
        this.sourceCache.clear();
    }

    // Check if requestedBounds is completely contained within cachedBounds
    private isAreaWithinCachedBounds(requestedBounds: Bounds, cachedBounds: Bounds): boolean {
        return requestedBounds.top_left.lat <= cachedBounds.top_left.lat &&
               requestedBounds.top_left.lng >= cachedBounds.top_left.lng &&
               requestedBounds.bottom_right.lat >= cachedBounds.bottom_right.lat &&
               requestedBounds.bottom_right.lng <= cachedBounds.bottom_right.lng;
    }

    async processConfig(
        processId: string,
        messageId: number,
        config: { sources: SourceConfig[]; expectedWorkerVersion?: string; [key: string]: any },
        callbacks: OperationCallbacks
    ): Promise<void> {
        console.log(`🢄PhotoOperations: Processing config update (${processId})`);

        if (callbacks.shouldAbort(processId)) {
            console.log(`🢄PhotoOperations: PROCESSCONFIG: Config process ${processId} aborted before completion`);
            return;
        }

        // Check worker version if provided
        if (config.expectedWorkerVersion && config.expectedWorkerVersion !== __WORKER_VERSION__) {
            throw new Error(`Worker version mismatch! Expected: ${config.expectedWorkerVersion}, Actual: ${__WORKER_VERSION__}`);
        }

        if (!config?.sources) {
            throw new Error('Invalid config: missing sources array');
        }

        const sources = config.sources;
        let allLoadedPhotos: PhotoData[] = [];
        const enabledSourceIds = new Set(sources.filter(s => s.enabled).map(s => s.id));
        console.log(`🢄PhotoOperations: PROCESSCONFIG: enabledSourceIds: ${Array.from(enabledSourceIds).join(', ')}, loadingProcesses: ${Array.from(this.loadingProcesses.keys()).join(', ')}`);

        for (const [sourceId, process] of this.loadingProcesses.entries()) {
            if (!enabledSourceIds.has(sourceId)) {
                console.log(`🢄PhotoOperations: PROCESSCONFIG: Cancelling loading process for disabled source ${sourceId}`);
                process.cancel();
                this.loadingProcesses.delete(sourceId);
                // Also clear the cache for disabled sources to free memory
                //this.sourceCache.delete(sourceId);
                //console.log(`🢄PhotoOperations: PROCESSCONFIG: Cleared cache for disabled source ${sourceId}`);
            }
        }

        // Update photosInArea with all loaded photos
        // (Stream and device sources add their photos via callbacks)
        callbacks.updatePhotosInArea(allLoadedPhotos);
        callbacks.sendPhotosInAreaUpdate();

        console.log(`🢄PhotoOperations: PROCESSCONFIG: Config processing complete (${processId}) - loaded ${allLoadedPhotos.length} photos`);
        callbacks.postMessage({
            type: 'processComplete',
            processId,
            processType: 'config',
            messageId
        });
    }

    async processArea(
        processId: string,
        messageId: number,
        area: Bounds,
        sources: SourceConfig[],
        callbacks: OperationCallbacks
    ): Promise<void> {
        console.log(`🢄PhotoOperations: Processing area update (${processId}) with ${sources.length} sources`);

        if (callbacks.shouldAbort(processId)) return;

        if (!area) {
            console.log(`🢄PhotoOperations: No area bounds provided (${processId})`);
            callbacks.postMessage({
                type: 'processComplete',
                processId,
                processType: 'area',
                messageId
            });
            return;
        }

        // Area operations create FRESH arrays (never modify existing)
        let newPhotosInArea: PhotoData[] = [];

        // For each enabled source, collect photos in area
        if (sources) {
            for (const source of sources.filter(s => s.enabled)) {
                if (callbacks.shouldAbort(processId)) return;

                const cache = this.sourceCache.get(source.id);

                if (cache && cache.isComplete && cache.cachedBounds && this.isAreaWithinCachedBounds(area, cache.cachedBounds)) {
                    // Cache is complete AND current area is within cached bounds - use cache
                    console.log(`🢄PhotoOperations: Current area is within cached bounds for ${source.id}, filtering cached photos`);
                    const filteredPhotos = filterPhotosByArea(cache.photos, area);
                    console.log(`🢄PhotoOperations: Filtered ${filteredPhotos.length} photos from ${cache.photos.length} cached for ${source.id}`);

                    if (filteredPhotos.length > 0) {
                        newPhotosInArea.push(...filteredPhotos);
                    }
                } else if (cache && !cache.isComplete) {
                    // Cache is partial - need to perform bounded load
                    console.log(`🢄PhotoOperations: Cache for ${source.id} is partial, performing bounded load`);
                    await this.loadSource(source, processId, callbacks, area);
                } else {
                    // No cache - perform bounded load
                    console.log(`🢄PhotoOperations: No cache for ${source.id}, performing bounded load`);
                    await this.loadSource(source, processId, callbacks, area);
                }
            }
        }

        if (callbacks.shouldAbort(processId)) return;

        callbacks.updatePhotosInArea(newPhotosInArea);
        callbacks.sendPhotosInAreaUpdate();

        console.log(`🢄PhotoOperations: Area processing complete (${processId}) - ${newPhotosInArea.length} photos in area`);
        callbacks.postMessage({
            type: 'processComplete',
            processId,
            processType: 'area',
            messageId
        });
    }


    private async loadSource(
        source: SourceConfig,
        processId: string,
        callbacks: OperationCallbacks,
        bounds?: Bounds
    ): Promise<void> {
        // Cancel existing loader for this source if any
        const existingProcess = this.loadingProcesses.get(source.id);
        if (existingProcess) {
            console.log(`🢄PhotoOperations: Cancelling existing loader for source ${source.id} (process: ${processId})`);
            existingProcess.cancel();
        }

        // Create callbacks for all source types
        const sourceCallbacks: PhotoSourceCallbacks = {
            onProgress: (loaded, total) => {
                callbacks.postMessage({
                    type: 'loadProgress',
                    sourceId: source.id,
                    loaded,
                    total
                });
            },
            onError: (error) => {
                callbacks.postMessage({
                    type: 'loadError',
                    sourceId: source.id,
                    error: error.message
                });
            },
            enqueueMessage: (message) => {
                callbacks.postMessage(message);
            },
            getValidToken: callbacks.getValidToken
        };

        const options: PhotoSourceOptions = {
            maxPhotos: this.maxPhotosInArea
        };

        const loader = PhotoSourceFactory.createLoader(source, sourceCallbacks, options);
        this.loadingProcesses.set(source.id, loader);

        try {
            await loader.start(bounds);
        } catch (error) {
            if (!loader.isAborted() && !callbacks.shouldAbort(processId)) {
                console.error(`🢄PhotoOperations: Error loading source ${source.id}:`, error);
            }
        } finally {
            // Ensure loader is removed from active processes
            if (this.loadingProcesses.get(source.id) === loader) {
                this.loadingProcesses.delete(source.id);
            }
        }
    }

    async processCombinePhotos(
        processId: string,
        messageId: number,
        areaBounds: Bounds | null,
        sources: SourceConfig[],
        callbacks: OperationCallbacks
    ): Promise<void> {
        console.log(`🢄PhotoOperations: Processing combinePhotos (${processId})`);

        if (callbacks.shouldAbort(processId)) {
            console.log(`🢄PhotoOperations: CombinePhotos process ${processId} aborted before processing`);
            return;
        }

        // This operation combines and culls existing photos from all sources
        // No new loading - just processing current data using existing culling logic

        // The worker has the sophisticated culling logic (mergeAndCullPhotos)
        // Just trigger the standard photo update pipeline
        callbacks.sendPhotosInAreaUpdate();
        callbacks.sendPhotosInRangeUpdate();

        console.log(`🢄PhotoOperations: CombinePhotos processing complete (${processId}) - triggered photo updates`);
        callbacks.postMessage({
            type: 'processComplete',
            processId,
            processType: 'sourcesPhotosInArea',
            messageId
        });
    }

    private async simulateWork(
        processId: string,
        callbacks: OperationCallbacks,
        ms: number
    ): Promise<void> {
        return new Promise((resolve) => {
            setTimeout(() => {
                resolve(); // Always resolve to avoid hanging
            }, ms);
        });
    }
}
