/// <reference lib="webworker" />

import type {Bounds, PhotoData, PhotoId, SourceConfig, WorkerMessage, WorkerResponse} from './photoWorkerTypes';
import {loadJsonPhotos} from './utils/photoParser';
import {MapillaryWorkerHandler} from './mapillaryWorkerHandler';
import {updatePhotoBearingDiffData} from './utils/bearingUtils';
import {calculateCenterFromBounds, getDistance, isInBounds} from './utils/distanceUtils';

declare const __WORKER_VERSION__: string;
export const WORKER_VERSION = __WORKER_VERSION__;

console.log(`Photo.Worker: Worker script loaded with version: ${WORKER_VERSION}`);

let sourcesConfig: SourceConfig[] = [];

// Photo data store - source of truth
const photoStore = new Map<PhotoId, PhotoData>();
let lastVisiblePhotos: PhotoData[] = [];

let currentBounds: Bounds | null = null;
let currentRange = 5000; // Default 5km range




// Grid-based photo sampling
function samplePhotosInGrid(photos: PhotoData[], maxPhotos: number): PhotoData[] {
    if (photos.length <= maxPhotos) return photos;

    console.log(`Photo.Worker: Sampling ${photos.length} photos down to ${maxPhotos} using grid sampling`);

    // Create a 10x10 grid
    const gridSize = 10;
    const totalCells = gridSize * gridSize;

    // Find bounds of all photos
    let minLat = Infinity, maxLat = -Infinity;
    let minLng = Infinity, maxLng = -Infinity;

    for (const photo of photos) {
        minLat = Math.min(minLat, photo.coord.lat);
        maxLat = Math.max(maxLat, photo.coord.lat);
        minLng = Math.min(minLng, photo.coord.lng);
        maxLng = Math.max(maxLng, photo.coord.lng);
    }

    const latStep = (maxLat - minLat) / gridSize;
    const lngStep = (maxLng - minLng) / gridSize;

    // Create grid cells
    const grid = new Map<string, PhotoData[]>();

    // Assign photos to grid cells
    for (const photo of photos) {
        const gridLat = Math.floor((photo.coord.lat - minLat) / latStep);
        const gridLng = Math.floor((photo.coord.lng - minLng) / lngStep);
        const cellKey = `${Math.min(gridLat, gridSize - 1)},${Math.min(gridLng, gridSize - 1)}`;

        if (!grid.has(cellKey)) {
            grid.set(cellKey, []);
        }
        grid.get(cellKey)!.push(photo);
    }

    // Sample photos from grid cells
    const sampledPhotos: PhotoData[] = [];
    const photosPerCell = Math.ceil(maxPhotos / totalCells);

    for (const cellPhotos of grid.values()) {
        if (cellPhotos.length <= photosPerCell) {
            sampledPhotos.push(...cellPhotos);
        } else {
            // Sample evenly from cell
            const step = cellPhotos.length / photosPerCell;
            for (let i = 0; i < photosPerCell; i++) {
                const index = Math.floor(i * step);
                sampledPhotos.push(cellPhotos[index]);
            }
        }

        if (sampledPhotos.length >= maxPhotos) break;
    }

    console.log(`Photo.Worker: Sampled down to ${sampledPhotos.length} photos from ${photos.length}, slicing to max ${maxPhotos}`);
    return sampledPhotos.slice(0, maxPhotos);
}

// Photo loading from sources
async function loadFromSources(sources: SourceConfig[]): Promise<void> {
    try {
        console.log('Photo.Worker: Loading photos from sources', sources.map(s => ({
            id: s.id,
            enabled: s.enabled,
            type: s.type,
            url: s.url
        })));

        // Check if Mapillary is disabled and stop stream if needed
        const mapillarySource = sources.find(s => s.id === 'mapillary');
        if (!mapillarySource || !mapillarySource.enabled) {
            console.log('Photo.Worker: Mapillary disabled or not found, stopping stream');
            mapillaryHandler.stopStream();
            mapillaryHandler.clearPhotos();
        }

        photoStore.clear();
        spatialIndex.clear();

        const allPhotos: PhotoData[] = [];

        for (const source of sources) {
            if (!source.enabled) {
                console.log(`Photo.Worker: Skipping disabled source: ${source.id}`);
                continue;
            }

            try {
                let sourcePhotos: PhotoData[] = [];

                switch (source.type) {
                    case 'json':
                        if (source.url) {

                            console.log(`Photo.Worker: Loading JSON photos from source ${source.id} at ${source.url}`);
                            sourcePhotos = await loadJsonPhotos(source.url);
                            console.log(`Photo.Worker: Loaded ${sourcePhotos.length} photos from JSON source ${source.id}`);

                            // Set source reference on each photo
                            sourcePhotos.forEach(photo => {
                                photo.source = source;
                            });

                            allPhotos.push(...sourcePhotos);
                        }
                        break;
                    case 'mapillary':
                        console.log('Photo.Worker: Starting Mapillary streaming for source:', source.id);
                        // Start Mapillary streaming - photos will be added via callback
                        if (currentBounds && source.backendUrl && source.clientId) {
                            await mapillaryHandler.startStream(
                                currentBounds.top_left.lat,
                                currentBounds.top_left.lng,
                                currentBounds.bottom_right.lat,
                                currentBounds.bottom_right.lng,
                                source.clientId,
                                source.backendUrl
                            );
                        } else {
                            console.log('Photo.Worker: Cannot start Mapillary stream - missing bounds or config');
                        }
                        break;
                    case 'device':
                        console.log('Photo.Worker: Device photo loading not yet implemented in worker');
                        break;
                    case 'directory':
                        console.log('Photo.Worker: Directory photo loading not yet implemented in worker');
                        break;
                    default:
                        console.error(`Photo.Worker: Unknown source type: ${source.type} for source ${source.id}`);
                }
            } catch (error) {
                console.error(`Photo.Worker: Error loading from source ${source.id}:`, error);
            }
        }

        // Load photos into worker stores
        for (const photo of allPhotos) {
            photoStore.set(photo.id, photo);
            spatialIndex.addPhoto(photo.id, photo.coord.lat, photo.coord.lng);
        }

        console.log(`Photo.Worker: Total immediately loaded ${allPhotos.length} photos from ${sources.length} sources`);
        recalculatePhotosInArea();

    } catch (error) {
        console.error('Photo.Worker: Error in loadFromSources:', error);
        postError('loadFromSources', error);
    }
}


function updateBounds(bounds: Bounds): void {
    try {
        console.log('Photo.Worker: updateBounds called with:', bounds);
        // Only recalculate if bounds actually changed
        if (!currentBounds ||
            currentBounds.top_left.lat !== bounds.top_left.lat ||
            currentBounds.top_left.lng !== bounds.top_left.lng ||
            currentBounds.bottom_right.lat !== bounds.bottom_right.lat ||
            currentBounds.bottom_right.lng !== bounds.bottom_right.lng) {
            currentBounds = bounds;
            console.log('Photo.Worker: Bounds updated, triggering recalculation');

            // For Mapillary, update bounds and restart streaming
            const mapillarySource = sourcesConfig.find(s => s.id === 'mapillary' && s.enabled);
            if (mapillarySource) {
                // Update bounds in handler (this will cull photos outside new bounds)
                mapillaryHandler.updateBounds({
                    topLeftLat: currentBounds.top_left.lat,
                    topLeftLon: currentBounds.top_left.lng,
                    bottomRightLat: currentBounds.bottom_right.lat,
                    bottomRightLon: currentBounds.bottom_right.lng
                });

                // Restart streaming with new bounds if we have config
                if (mapillarySource.backendUrl && mapillarySource.clientId) {
                    console.log('Photo.Worker: Restarting Mapillary stream for new bounds');
                    mapillaryHandler.startStream(
                        currentBounds.top_left.lat,
                        currentBounds.top_left.lng,
                        currentBounds.bottom_right.lat,
                        currentBounds.bottom_right.lng,
                        mapillarySource.clientId,
                        mapillarySource.backendUrl
                    );
                }
            }

            recalculatePhotosInArea();
        } else {
            console.log('Photo.Worker: Bounds unchanged, skipping recalculation');
        }
    } catch (error) {
        console.error('Photo.Worker: Error updating bounds:', error);
        postError('updateBounds', error);
    }
}

async function updateSources(sources: SourceConfig[]): Promise<void> {
    try {
        // Only reload if sources actually changed
        const sourcesChanged = !sourcesConfig ||
            sourcesConfig.length !== sources.length ||
            sourcesConfig.some((s, i) => s.id !== sources[i]?.id || s.enabled !== sources[i]?.enabled);

        if (sourcesChanged) {
            console.log('Photo.Worker: Source configuration changed, reloading photos');
            sourcesConfig = sources;

            // Reload photos with new source configuration
            await loadFromSources(sources);
        }
    } catch (error) {
        console.error('Photo.Worker: Error updating sources:', error);
        postError('updateSources', error);
    }
}

function recalculatePhotosInArea(): void {
    // Debounce
    if (recalculateTimeout) {
        clearTimeout(recalculateTimeout);
    }
    recalculateTimeout = setTimeout(() => {
// Guard against duplicate operations
        if (isRecalculating) {
            console.log('Photo.Worker: recalculatePhotosInArea: Already recalculating, skipping');
            return;
        }

        isRecalculating = true;
        recalculatePhotosInAreaInternal();
        recalculateTimeout = null;
        isRecalculating = false;
    }, 100);
}

function recalculatePhotosInAreaInternal(): void {
    if (!currentBounds) {
        console.log('Photo.Worker: recalculatePhotosInArea: No bounds set, skipping recalculation. Photos loaded:', photoStore.size);
        return;
    }

    console.log('Photo.Worker: recalculatePhotosInArea: bounds:', currentBounds, 'input Photos:', photoStore.size);
    const startTime = performance.now();

    // Get photo IDs in spatial bounds first
    const photoIdsInBounds = spatialIndex.getPhotoIdsInBounds(currentBounds);
    console.log(`Photo.Worker: recalculatePhotosInArea: Found ${photoIdsInBounds.length} photos in bounds`);

    const photosInBounds: PhotoData[] = [];

    for (const photoId of photoIdsInBounds) {
        const photo = photoStore.get(photoId);
        if (photo) {
            photosInBounds.push(photo);
        }
    }

    // Apply grid-based sampling if too many photos
    const visiblePhotos = photosInBounds.length <= MAX_PHOTOS_IN_AREA
        ? photosInBounds
        : samplePhotosInGrid(photosInBounds, MAX_PHOTOS_IN_AREA);

    // Sort by bearing, then by ID for stable ordering
    visiblePhotos.sort((a, b) => {
        if (a.bearing !== b.bearing) {
            return a.bearing - b.bearing;
        }
        return a.id.localeCompare(b.id);
    });

    // Calculate distances from center of bounds
    const center = calculateCenterFromBounds(currentBounds);

    for (const photo of visiblePhotos) {
        const distance = getDistance(center, photo.coord);
        //console.log(`Photo.Worker: Photo ${photo.id} distance from center: ${distance.toFixed(2)}m`);
        photo.range_distance = distance <= currentRange ? distance : null;
    }

    lastVisiblePhotos = visiblePhotos;

    // Only log when we have results or significant processing time
    const processingTime = performance.now() - startTime;
    //if (visiblePhotos.length > 0 || processingTime > 10) {
    console.log(`Photo.Worker: recalculatePhotosInArea: Filtered down to ${visiblePhotos.length} photos in ${processingTime.toFixed(1)}ms`);
    //}

    postMessage({
        id: 'auto',
        type: 'photosUpdate',
        data: {
            photos: visiblePhotos,
        }
    } as WorkerResponse);
}


function getPhotosInRange(center: { lat: number; lng: number }): void {
    try {
        let photosWithDistance: PhotoData[] = [];

        console.log('Photo.Worker: Recalculating distances for photos, lastVisiblePhotos:', lastVisiblePhotos.length);
        for (const photo of lastVisiblePhotos) {
            const distance = getDistance(center, photo.coord);

            //console.log(`Photo.Worker: Photo ${photo.id} distance from center: ${distance.toFixed(2)}m, limit: ${currentRange}m`);

            if (distance <= currentRange) {
                photosWithDistance.push({
                    ...photo,
                    range_distance: distance
                });
            }
        }

        // Limit photos (preserve bearing order from lastVisiblePhotos)
        photosWithDistance = photosWithDistance.slice(0, MAX_PHOTOS_IN_RANGE);
        console.log(`Photo.Worker: getPhotosInRange filtered ${photosWithDistance.length} photos within range`);

        postMessage({
            id: 'auto',
            type: 'rangeUpdate',
            data: {
                photosInRange: photosWithDistance
            }
        } as WorkerResponse);
    } catch (error) {
        console.error('Photo.Worker: Error filtering photos by range:', error);
        postError('getPhotosInRange', error);
    }
}

function updateBearingColors(bearing: number): void {
    try {
        console.log(`Photo.Worker: Updating bearing colors for ${lastVisiblePhotos.length} photos, bearing: ${bearing}`);

        // Update bearing colors for all visible photos
        const photosWithColors = lastVisiblePhotos.map(photo =>
            updatePhotoBearingDiffData(photo, bearing)
        );

        postMessage({
            id: 'auto',
            type: 'bearingUpdate',
            data: {
                photos: photosWithColors,
                bearing: bearing
            }
        } as WorkerResponse);
    } catch (error) {
        console.error('Photo.Worker: Error updating bearing colors:', error);
        postError('updateBearingColors', error);
    }
}


function postError(operation: string, error: any): void {
    postMessage({
        id: 'error',
        type: 'error',
        error: {
            message: error?.message || 'Unknown error',
            operation,
            timestamp: Date.now()
        }
    } as WorkerResponse);
}

// Message handler
self.onmessage = async function (e: MessageEvent<WorkerMessage>) {
    const {id, type, data} = e.data;

    try {
        switch (type) {
            case 'init':
                // Worker initialization
                console.log(`Photo.Worker: Init request received, responding with version: ${WORKER_VERSION}`);
                postMessage({id, type: 'ready', data: {version: WORKER_VERSION}} as WorkerResponse);
                break;

            case 'loadFromSources':
                console.log('Photo.Worker: loadFromSources message received, data:', data);
                if (data?.sources) {
                    console.log('Photo.Worker: data.sources is valid, length:', data.sources.length);
                    await loadFromSources(data.sources);
                } else {
                    console.log('Photo.Worker: data.sources is invalid:', data?.sources);
                }
                postMessage({id, type: 'success'} as WorkerResponse);
                break;

            case 'updateBounds':
                if (data?.bounds) {
                    updateBounds(data.bounds);
                }
                postMessage({id, type: 'success'} as WorkerResponse);
                break;

            case 'updateSources':
                if (data?.sources) {
                    await updateSources(data.sources);
                }
                postMessage({id, type: 'success'} as WorkerResponse);
                break;

            case 'updateRange':
                if (data?.range !== undefined) {
                    console.log(`Photo.Worker: Updating range from ${currentRange} to ${data.range}`);
                    currentRange = data.range;
                }
                postMessage({id, type: 'success'} as WorkerResponse);
                break;

            case 'getPhotosInRange':
                if (data?.center) {
                    getPhotosInRange(data.center);
                }
                postMessage({id, type: 'success'} as WorkerResponse);
                break;

            case 'updateBearingColors':
                if (data?.bearing !== undefined) {
                    updateBearingColors(data.bearing);
                }
                postMessage({id, type: 'success'} as WorkerResponse);
                break;

            case 'updateConfig':
                if (data?.config) {
                    if (data.config.recalculateBearingDiffForAllPhotosInArea !== undefined) {
                        recalculateBearingDiffForAllPhotosInArea = data.config.recalculateBearingDiffForAllPhotosInArea;
                        console.log('Photo.Worker: Updated recalculateBearingDiffForAllPhotosInArea to', recalculateBearingDiffForAllPhotosInArea);
                    }
                }
                postMessage({id, type: 'success'} as WorkerResponse);
                break;

            case 'terminate':
                self.close();
                break;

            default:
                throw new Error(`Unknown message type: ${type}`);
        }
    } catch (error: any) {
        postMessage({
            id,
            type: 'error',
            error: {message: error?.message || 'Unknown error'}
        } as WorkerResponse);
    }
};


function onPhotoStoreChange() {
    // Trigger recalculation if we have bounds
    if (currentBounds) {
        recalculatePhotosInArea();

        // Also trigger range update for navigation using bounds center
        const center = calculateCenterFromBounds(currentBounds);
        getPhotosInRange(center);
    }
}


// Initialize Mapillary handler
const mapillaryHandler = new MapillaryWorkerHandler({
    onPhotosAdded: (photos: PhotoData[]) => {
        console.log(`Photo.Worker: Mapillary adding ${photos.length} photos`);
        // Add photos to store and spatial index
        photos.forEach(photo => {
            photoStore.set(photo.id, photo);
            if (spatialIndex) {
                // All photos now use coord property consistently
                if (photo.coord) {
                    spatialIndex.addPhoto(photo.id, photo.coord.lat, photo.coord.lng);
                }
            }
        });
        onPhotoStoreChange();
    },
    onStreamComplete: () => {
        console.log('Photo.Worker: Mapillary streaming completed');
    },
    onError: (error: string) => {
        console.error('Photo.Worker: Mapillary error:', error);
    },
    onStatusUpdate: (status) => {
        // Send unified status update to main thread for debug panel
        postMessage({
            id: 'auto',
            type: 'statusUpdate',
            data: {
                mapillaryStatus: {
                    // Legacy compatibility fields
                    uncached_regions: status.uncachedRegions || 0,
                    is_streaming: status.isStreaming,
                    total_live_photos: status.totalPhotos,

                    // New detailed fields
                    stream_phase: status.streamPhase,
                    completed_regions: status.completedRegions?.length || 0,
                    last_request_time: status.lastRequestTime,
                    last_response_time: status.lastResponseTime,
                    current_url: status.currentUrl,
                    last_error: status.lastError,
                    last_bounds: status.lastBounds
                }
            }
        } as WorkerResponse);
    }
});

// Export for TypeScript
export {};