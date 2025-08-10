/**
 * Photo Operations - Pure Business Logic
 */

import type { PhotoData, SourceConfig, Bounds } from './photoWorkerTypes';
import { PhotoLoadingProcess, type PhotoLoadingCallbacks } from './PhotoLoadingProcess';
import { filterPhotosByArea } from './photoProcessingUtils';

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

export class PhotoOperations {
    private jsonCache = new Map<string, PhotoData[]>();
    private loadingProcesses = new Map<string, PhotoLoadingProcess>();

    constructor() {}

    // Cache management
    getCachedJson(sourceId: string): PhotoData[] | undefined {
        return this.jsonCache.get(sourceId);
    }

    setCachedJson(sourceId: string, photos: PhotoData[]): void {
        this.jsonCache.set(sourceId, photos);
        console.log(`PhotoOperations: Cached ${photos.length} photos for source ${sourceId}`);
    }

    clearCache(): void {
        this.jsonCache.clear();
        // Cancel any ongoing loading processes
        for (const process of this.loadingProcesses.values()) {
            process.cancel();
        }
        this.loadingProcesses.clear();
        console.log('PhotoOperations: Cleared cache and cancelled loading processes');
    }

    async processConfig(
        processId: string,
        messageId: number,
        config: { sources: SourceConfig[]; [key: string]: any },
        callbacks: OperationCallbacks
    ): Promise<void> {
        console.log(`PhotoOperations: Processing config update (${processId})`);
        
        if (callbacks.shouldAbort(processId)) return;
        
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

        // Process each enabled source
        for (const source of sources.filter(s => s.enabled)) {
            if (callbacks.shouldAbort(processId)) return;
            
            console.log(`PhotoOperations: Processing source ${source.id} (${processId})`);
            
            if (source.type === 'json') {
                // For JSON sources, load once into cache if not already cached
                let cachedPhotos = this.getCachedJson(source.id);
                
                if (!cachedPhotos) {
                    console.log(`PhotoOperations: Loading JSON source ${source.id}`);
                    await this.loadJsonSource(source, processId, callbacks);
                    cachedPhotos = this.getCachedJson(source.id);
                }
                
                if (cachedPhotos) {
                    allLoadedPhotos.push(...cachedPhotos);
                }
                
            } else if (source.type === 'stream') {
                // For stream sources, the loading process will add photos via callbacks as they arrive
                console.log(`PhotoOperations: Starting stream source ${source.id}`);
                await this.startStreamSource(source, processId, callbacks);
            }
        }
        
        if (callbacks.shouldAbort(processId)) return;
        
        // Update photosInArea with all loaded photos from JSON sources
        // (Stream sources add their photos via callbacks)
        if (allLoadedPhotos.length > 0) {
            callbacks.updatePhotosInArea(allLoadedPhotos);
            callbacks.sendPhotosInAreaUpdate();
        }
        
        console.log(`PhotoOperations: Config processing complete (${processId}) - loaded ${allLoadedPhotos.length} photos from JSON sources`);
        callbacks.postMessage({
            type: 'processComplete',
            processId,
            processType: 'config',
            messageId: undefined
        });
    }

    async processArea(
        processId: string,
        messageId: number,
        area: Bounds,
        sources: SourceConfig[],
        callbacks: OperationCallbacks
    ): Promise<void> {
        console.log(`PhotoOperations: Processing area update (${processId})`);
        
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
                
                if (source.type === 'json') {
                    // Filter cached data by area
                    const cachedPhotos = this.getCachedJson(source.id);
                    if (cachedPhotos) {
                        console.log(`PhotoOperations: Filtering ${cachedPhotos.length} cached photos for source ${source.id}`);
                        const filteredPhotos = filterPhotosByArea(cachedPhotos, area);
                        newPhotosInArea.push(...filteredPhotos);
                        
                        // Small delay for large datasets to allow abortion checks
                        if (filteredPhotos.length > 1000) {
                            await this.simulateWork(processId, callbacks, 10);
                        }
                    }
                } else if (source.type === 'stream') {
                    // For stream sources, start new stream with bounds
                    // Photos will be added as they arrive via callbacks
                    console.log(`PhotoOperations: Restarting stream source ${source.id} with new bounds`);
                    await this.startStreamSource(source, processId, callbacks, area);
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
            messageId: undefined
        });
    }

    private async loadJsonSource(
        source: SourceConfig,
        processId: string,
        callbacks: OperationCallbacks
    ): Promise<void> {
        const loadingCallbacks: PhotoLoadingCallbacks = {
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
            enqueueMessage: callbacks.postMessage,
            getCachedJson: (sourceId) => this.getCachedJson(sourceId),
            setCachedJson: (sourceId, photos) => this.setCachedJson(sourceId, photos)
        };

        const loadingProcess = new PhotoLoadingProcess(source, loadingCallbacks);
        this.loadingProcesses.set(source.id, loadingProcess);
        
        try {
            await loadingProcess.start();
        } catch (error) {
            if (!loadingProcess.isAborted() && !callbacks.shouldAbort(processId)) {
                console.error(`PhotoOperations: Error loading JSON source ${source.id}:`, error);
            }
        } finally {
            this.loadingProcesses.delete(source.id);
        }
    }

    private async startStreamSource(
        source: SourceConfig,
        processId: string,
        callbacks: OperationCallbacks,
        bounds?: Bounds
    ): Promise<void> {
        // Cancel existing stream for this source if any
        const existingProcess = this.loadingProcesses.get(source.id);
        if (existingProcess) {
            existingProcess.cancel();
        }

        const loadingCallbacks: PhotoLoadingCallbacks = {
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
            enqueueMessage: callbacks.postMessage,
            getCachedJson: (sourceId) => this.getCachedJson(sourceId),
            setCachedJson: (sourceId, photos) => this.setCachedJson(sourceId, photos)
        };

        const loadingProcess = new PhotoLoadingProcess(source, loadingCallbacks);
        this.loadingProcesses.set(source.id, loadingProcess);
        
        try {
            await loadingProcess.start(bounds);
        } catch (error) {
            if (!loadingProcess.isAborted() && !callbacks.shouldAbort(processId)) {
                console.error(`PhotoOperations: Error loading stream source ${source.id}:`, error);
            }
        } finally {
            this.loadingProcesses.delete(source.id);
        }
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