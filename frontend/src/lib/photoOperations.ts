/**
 * Photo Operations - Pure Business Logic
 */

import type { PhotoData, SourceConfig, Bounds } from './photoWorkerTypes';
import { PhotoSourceFactory } from './sources/PhotoSourceFactory';
import type { PhotoSourceLoader, PhotoSourceCallbacks } from './sources/PhotoSourceLoader';
import { filterPhotosByArea } from './workerUtils';

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
}

interface SourceCache {
    photos: PhotoData[];
    isComplete: boolean; // true = no more photos available, false = partial load (stream has "next" link)
}

export class PhotoOperations {
    private loadingProcesses = new Map<string, PhotoSourceLoader>();
    private sourceCache = new Map<string, SourceCache>(); // Cache for each source

    constructor() {}

    async processConfig(
        processId: string,
        messageId: number,
        config: { sources: SourceConfig[]; expectedWorkerVersion?: string; [key: string]: any },
        callbacks: OperationCallbacks
    ): Promise<void> {
        console.log(`PhotoOperations: Processing config update (${processId})`);
        
        if (callbacks.shouldAbort(processId)) return;

        // Check worker version if provided
        if (config.expectedWorkerVersion && config.expectedWorkerVersion !== __WORKER_VERSION__) {
            throw new Error(`Worker version mismatch! Expected: ${config.expectedWorkerVersion}, Actual: ${__WORKER_VERSION__}`);
        }
        
        if (!config?.sources) {
            console.log(`PhotoOperations: No sources in config (${processId})`);
            callbacks.postMessage({
                type: 'processComplete',
                processId,
                processType: 'config',
                messageId
            });
            return;
        }

        const sources = config.sources;
        let allLoadedPhotos: PhotoData[] = [];

        // Cancel any existing loading processes that are no longer needed
        const enabledSourceIds = new Set(sources.filter(s => s.enabled).map(s => s.id));
        for (const [sourceId, process] of this.loadingProcesses.entries()) {
            if (!enabledSourceIds.has(sourceId)) {
                console.log(`PhotoOperations: Cancelling loading process for disabled source ${sourceId}`);
                process.cancel();
                this.loadingProcesses.delete(sourceId);
            }
        }

        // Process each enabled source - perform global preloading for cache
        for (const source of sources.filter(s => s.enabled)) {
            if (callbacks.shouldAbort(processId)) return;
            
            console.log(`PhotoOperations: Processing source ${source.id} (${processId})`);
            
            // Check if we already have a cache for this source
            const existingCache = this.sourceCache.get(source.id);
            if (!existingCache) {
                console.log(`PhotoOperations: No cache for ${source.id}, performing global preload`);
                
                // Perform global load with full globe bounds
                const globalBounds: Bounds = {
                    top_left: { lat: 90, lng: -180 },
                    bottom_right: { lat: -90, lng: 180 }
                };
                await this.loadSource(source, processId, callbacks, globalBounds);
            } else {
                console.log(`PhotoOperations: Using existing cache for ${source.id} (${existingCache.photos.length} photos, complete: ${existingCache.isComplete})`);
                
                // Add cached photos to the current operation
                if (existingCache.photos.length > 0) {
                    callbacks.updatePhotosInArea(existingCache.photos);
                }
            }
        }
        
        if (callbacks.shouldAbort(processId)) {
            console.log(`PhotoOperations: Config process ${processId} aborted before completion`);
            return;
        }
        
        // Update photosInArea with all loaded photos
        // (Stream and device sources add their photos via callbacks)
        callbacks.updatePhotosInArea(allLoadedPhotos);
        callbacks.sendPhotosInAreaUpdate();
        
        console.log(`PhotoOperations: Config processing complete (${processId}) - loaded ${allLoadedPhotos.length} photos`);
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
        console.log(`PhotoOperations: Processing area update (${processId}) with ${sources.length} sources`);
        
        if (callbacks.shouldAbort(processId)) return;
        
        if (!area) {
            console.log(`PhotoOperations: No area bounds provided (${processId})`);
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
                
                if (cache && cache.isComplete) {
                    // Cache is complete - filter cached photos by area instead of new load
                    console.log(`PhotoOperations: Using complete cache for ${source.id}, filtering by area`);
                    const filteredPhotos = filterPhotosByArea(cache.photos, area);
                    console.log(`PhotoOperations: Filtered ${filteredPhotos.length} photos from ${cache.photos.length} cached for ${source.id}`);
                    
                    if (filteredPhotos.length > 0) {
                        newPhotosInArea.push(...filteredPhotos);
                    }
                } else if (cache && !cache.isComplete) {
                    // Cache is partial - need to perform bounded load
                    console.log(`PhotoOperations: Cache for ${source.id} is partial, performing bounded load`);
                    await this.loadSource(source, processId, callbacks, area);
                } else {
                    // No cache - perform bounded load
                    console.log(`PhotoOperations: No cache for ${source.id}, performing bounded load`);
                    await this.loadSource(source, processId, callbacks, area);
                }
            }
        }
        
        if (callbacks.shouldAbort(processId)) return;
        
        // Update shared state with NEW array (not in-place modification)
        callbacks.updatePhotosInArea(newPhotosInArea);
        callbacks.sendPhotosInAreaUpdate();
        
        console.log(`PhotoOperations: Area processing complete (${processId}) - ${newPhotosInArea.length} photos in area`);
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
            console.log(`PhotoOperations: Cancelling existing loader for source ${source.id} (process: ${processId})`);
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
                // Intercept messages to populate cache when doing global loads
                const isGlobalLoad = bounds && 
                    bounds.top_left.lat === 90 && bounds.top_left.lng === -180 &&
                    bounds.bottom_right.lat === -90 && bounds.bottom_right.lng === 180;
                
                if (isGlobalLoad) { // Global load - update cache
                    if (message.type === 'photosAdded') {
                        // Replace cache with latest photo list (source accumulates internally)
                        // Check if stream indicates no more photos (no "next" link)
                        const isComplete = !message.hasNext;
                        this.sourceCache.set(source.id, {
                            photos: [...message.photos],
                            isComplete
                        });
                        console.log(`PhotoOperations: Cache updated for ${source.id} (${message.photos.length} photos, hasNext: ${message.hasNext})`);
                    } else if (message.type === 'streamComplete') {
                        // Mark cache as complete
                        const cache = this.sourceCache.get(source.id);
                        if (cache) {
                            cache.isComplete = true;
                            console.log(`PhotoOperations: Cache complete for ${source.id} (${cache.photos.length} photos)`);
                        }
                    }
                }
                
                // Forward message to worker queue
                callbacks.postMessage(message);
            }
        };

        const loader = PhotoSourceFactory.createLoader(source, sourceCallbacks);
        this.loadingProcesses.set(source.id, loader);
        
        try {
            await loader.start(bounds);
        } catch (error) {
            if (!loader.isAborted() && !callbacks.shouldAbort(processId)) {
                console.error(`PhotoOperations: Error loading source ${source.id}:`, error);
            }
        } finally {
            this.loadingProcesses.delete(source.id);
        }
    }

    async processCombinePhotos(
        processId: string,
        messageId: number,
        areaBounds: Bounds | null,
        sources: SourceConfig[],
        callbacks: OperationCallbacks
    ): Promise<void> {
        console.log(`PhotoOperations: Processing combinePhotos (${processId})`);
        
        if (callbacks.shouldAbort(processId)) {
            console.log(`PhotoOperations: CombinePhotos process ${processId} aborted before processing`);
            return;
        }
        
        // This operation combines and culls existing photos from all sources
        // No new loading - just processing current data using existing culling logic
        
        // The worker has the sophisticated culling logic (mergeAndCullPhotos)
        // Just trigger the standard photo update pipeline
        callbacks.sendPhotosInAreaUpdate();
        callbacks.sendPhotosInRangeUpdate();
        
        console.log(`PhotoOperations: CombinePhotos processing complete (${processId}) - triggered photo updates`);
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