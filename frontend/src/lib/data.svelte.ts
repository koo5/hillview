import {type Photo} from "./types";
import {space_db} from "./debug_server.js";
import { updatePhotoBearingData, calculateAngularDistance } from './utils/bearingUtils';
import { calculateDistance, calculateCenterFromBounds } from './utils/distanceUtils';
import { buildNavigationStructure } from './utils/photoNavigationUtils';
import { updatePhotoBearings, sortPhotosByAngularDistance } from './photoProcessing';
import {LatLng} from 'leaflet';
import {get, writable} from "svelte/store";
import {
    localStorageReadOnceSharedStore,
    localStorageSharedStore
} from './svelte-shared-store';
import type { PhotoData } from './sources';
import {tick} from "svelte";
import { geoPicsUrl } from './config';
import { auth } from './auth.svelte';
import { userPhotos } from './stores';
import { updateCaptureLocation } from './captureLocation';
import { photoProcessingAdapter } from './photoProcessingAdapter';
import { createMapillaryStreamService, type MapillaryStreamCallbacks } from './mapillaryStreamService';
import {triggerPhotosBearingDiffRecalculator} from "$lib/photosBearingDiffRecalculator";

// Source interface and store moved here to avoid circular dependency
export interface Source {
    id: string;
    name: string;
    type: 'json' | 'mapillary' | 'device' | 'directory';
    enabled: boolean;
    requests: number[];
    color: string;
    url?: string; // For JSON sources (both built-in and custom)
    path?: string; // For directory sources
}

export const sources = writable<Source[]>([
    {id: 'hillview', name: 'Hillview', type: 'json', enabled: true, requests: [], color: '#000', url: `${geoPicsUrl}/files.json`},
    {id: 'mapillary', name: 'Mapillary', type: 'mapillary', enabled: false, requests: [], color: '#888'},
    {id: 'device', name: 'My Device', type: 'device', enabled: true, requests: [], color: '#4a90e2'},
]);

// Define types locally since we removed photoProcessingService
export interface AreaFilterResult {
    hillviewPhotosInArea: PhotoData[];
    mapillaryPhotosInArea: PhotoData[];
    photosInArea: PhotoData[];
}

export interface DistanceResult {
    photosInRange: PhotoData[];
}

export interface BearingResult {
    photoInFront: PhotoData | null;
    photoToLeft: PhotoData | null;
    photoToRight: PhotoData | null;
    photosToLeft: PhotoData[];
    photosToRight: PhotoData[];
}


export let client_id = localStorageSharedStore('client_id', Math.random().toString(36));


export let app = writable<{
    error: string | null;
    debug: number;
    displayMode: 'split' | 'max';
    loading?: boolean;
    isAuthenticated?: boolean;
    userPhotos?: any[];
    activity: 'capture' | 'view';
}>({
    error: null,
    debug: 0,
    displayMode: 'split', // 'split' or 'max'
    activity: 'view',
})

// Subscribe to auth store to keep app state in sync
auth.subscribe(authState => {
    app.update(a => ({
        ...a,
        isAuthenticated: authState.isAuthenticated
    }));
});

// Subscribe to userPhotos store to keep app state in sync
userPhotos.subscribe(photos => {
    app.update(a => ({
        ...a,
        userPhotos: photos
    }));
});

export let photos_in_area = writable<any[]>([]);
export let photos_in_range = writable<any[]>([]);

export let photo_in_front = writable<any | null>(null);
export let photos_to_left = writable<any[]>([]);
export let photos_to_right = writable<any[]>([]);
export let photo_to_left = writable<any | null>(null);
export let photo_to_right = writable<any | null>(null);








let last_mapillary_request = 0;
let mapillary_request_timer: any = null;
let mapillary_stream_service: any = null;

function processMapillaryPhotos(photos: any[], src: any) {
    let current_photos = get(mapillary_photos);
    let added_count = 0;
    
    for (let photo of photos) {
        const id = 'mapillary_' + photo.id;

        if (current_photos.has(id)) {
            continue;
        }
        
        let coord = new LatLng(photo.geometry.coordinates[1], photo.geometry.coordinates[0]);
        let bearing = photo.compass_angle;
        let processed_photo = {
            source: src,
            source_type: 'mapillary',
            id: id,
            file: photo.id + '.jpg',
            url: photo.thumb_1024_url,
            coord: coord,
            bearing: bearing,
            altitude: 0,
            sizes: {
                1024: {width: 1024, height: 768, url: photo.thumb_1024_url},
                50: {width: 50, height: 50, url: photo.thumb_1024_url},
                'full': {width: 1024, height: 768, url: photo.thumb_1024_url}
            },
        };

        current_photos.set(id, processed_photo);
        added_count++;
    }
    
    const limit = 1500;
    if (current_photos.size > limit) {
        let keys = [...current_photos.keys()];
        for (let i = 0; i < current_photos.size - limit; i++) {
            current_photos.delete(keys[i]);
        }
    }
    
    mapillary_photos.set(current_photos);
    return added_count;
}

async function get_mapillary_photos() {
    let src = get(sources).find(s => s.id === 'mapillary');
    if (!src) {
        return;
    }

    let enabled = src.enabled;
    console.log('mapillary enabled:', enabled);
    if (!enabled) {
        // Stop any existing stream
        if (mapillary_stream_service) {
            mapillary_stream_service.stopStream();
        }
        mapillary_cache_status.set({ uncached_regions: 0, is_streaming: false, total_live_photos: 0 });
        filter_mapillary_photos_by_area();
        return;
    }

    let ts = new Date().getTime();

    // Rate limiting check
    if (ts - last_mapillary_request < 5000) {
        if (mapillary_request_timer) {
            return;
        }
        mapillary_request_timer = setTimeout(() => {
            mapillary_request_timer = null;
            get_mapillary_photos();
            }, 1000);
        return;
    }
    last_mapillary_request = ts;

    let p2 = get(pos2);
    let window_x = 0;
    let window_y = 0;
    
    sources.update(s => {
        src.requests.push(ts);
        return s;
    });

    // Stop any existing stream
    if (mapillary_stream_service) {
        mapillary_stream_service.stopStream();
    }

    // Create stream service with callbacks
    const callbacks: MapillaryStreamCallbacks = {
        onCachedPhotos: (photos) => {
            console.log('Received cached photos:', photos.length);
            if (photos.length > 0) {
                const added = processMapillaryPhotos(photos, src);
                console.log(`Added ${added} cached photos`);
                
                // Trigger area filter after cached photos are loaded
                photoProcessingAdapter.queueAreaFilter(
                    { top_left: p2.top_left, bottom_right: p2.bottom_right },
                    p2.range,
                    get(sources)
                );
            }
        },
        
        onCacheStatus: (uncachedRegions) => {
            console.log('Cache status - uncached regions:', uncachedRegions);
            mapillary_cache_status.update(status => ({
                ...status,
                uncached_regions: uncachedRegions,
                is_streaming: uncachedRegions > 0
            }));
        },
        
        onLivePhotosBatch: (photos, region) => {
            console.log(`Received live photos batch: ${photos.length} photos from region ${region}`);
            const added = processMapillaryPhotos(photos, src);
            console.log(`Added ${added} live photos from region ${region}`);
            
            // Trigger area filter after each batch
            photoProcessingAdapter.queueAreaFilter(
                { top_left: p2.top_left, bottom_right: p2.bottom_right },
                p2.range,
                get(sources)
            );
            
            // Also trigger area update since new photos were added
            triggerAreaUpdate();
        },
        
        onRegionComplete: (region, photosCount) => {
            console.log(`Region ${region} completed with ${photosCount} photos`);
        },
        
        onStreamComplete: (totalLivePhotos) => {
            console.log(`Stream completed with ${totalLivePhotos} total live photos`);
            mapillary_cache_status.update(status => ({
                ...status,
                is_streaming: false,
                total_live_photos: totalLivePhotos
            }));
            
            sources.update(s => {
                src.requests.splice(src.requests.indexOf(ts), 1);
                return s;
            });
            
            console.log('Final Mapillary photos count:', get(mapillary_photos).size);
        },
        
        onError: (message) => {
            console.error('Mapillary stream error:', message);
            mapillary_cache_status.update(status => ({
                ...status,
                is_streaming: false
            }));
            
            sources.update(s => {
                src.requests.splice(src.requests.indexOf(ts), 1);
                return s;
            });
        }
    };

    // Start streaming
    mapillary_stream_service = createMapillaryStreamService(callbacks);
    
    try {
        await mapillary_stream_service.startStream(
            p2.top_left.lat + window_y,
            p2.top_left.lng - window_x,
            p2.bottom_right.lat - window_y,
            p2.bottom_right.lng + window_x
        );
    } catch (error) {
        console.error('Error starting Mapillary stream:', error);
        mapillary_cache_status.update(status => ({
            ...status,
            is_streaming: false
        }));
        
        sources.update(s => {
            src.requests.splice(src.requests.indexOf(ts), 1);
            return s;
        });
    }
}

pos2.subscribe(get_mapillary_photos);


let old_sources: Source[] = JSON.parse(JSON.stringify(get(sources)));
sources.subscribe(async (s: Source[]) => {
    console.log('sources changed:', s);
    let old = JSON.parse(JSON.stringify(old_sources));
    old_sources = JSON.parse(JSON.stringify(s));
    
    // Check if any source enabled state changed or new sources were added
    const changedSources = s.filter((src, i) => {
        const oldSrc = old.find((o: Source) => o.id === src.id);
        // Source changed if it's new (not in old) or if enabled state changed
        return !oldSrc || oldSrc.enabled !== src.enabled;
    });
    
    if (changedSources.length > 0) {
        console.log('Source enabled states changed:', changedSources.map(s => ({ id: s.id, enabled: s.enabled })));
        
        // Handle Mapillary separately (it has its own streaming logic)
        const mapillaryChanged = changedSources.find(s => s.id === 'mapillary');
        const otherSourcesChanged = changedSources.filter(s => s.id !== 'mapillary');
        
        // Trigger filter update if:
        // 1. Non-Mapillary sources changed, OR
        // 2. Mapillary was disabled (need to remove its photos)
        if (otherSourcesChanged.length > 0 || (mapillaryChanged && !mapillaryChanged.enabled)) {
            const p2 = get(pos2);
            photoProcessingAdapter.queueAreaFilter(
                { top_left: p2.top_left, bottom_right: p2.bottom_right },
                p2.range,
                s
            );
        }
        
        // If Mapillary was enabled, start streaming
        if (mapillaryChanged && mapillaryChanged.enabled) {
            console.log('get_mapillary_photos');
            await get_mapillary_photos();
        }
    }
});


function filter_mapillary_photos_by_area() {

    if (!get(sources).find(s => s.id === 'mapillary')?.enabled) {
        mapillary_photos_in_area.set([]);
        return;
    }

    let p2 = get(pos2);
    let ph = get(mapillary_photos);

    let window_x = p2.bottom_right.lng - p2.top_left.lng;
    let window_y = p2.top_left.lat - p2.bottom_right.lat;

    let res = [];
    for (let photo of ph.values()) {
        let yes = photo.coord.lat < p2.top_left.lat + window_y && photo.coord.lat > p2.bottom_right.lat - window_y &&
            photo.coord.lng > p2.top_left.lng - window_x && photo.coord.lng < p2.bottom_right.lng + window_x;
        if (yes) {
            res.push(photo);
        }
    }
    console.log('mapillary photos in area:', res.length);
    mapillary_photos_in_area.set(res);
}

function update_bearing_diff() {
    if (!get(recalculateBearingDiffForAllPhotosInArea))
        return;
    // Skip bearing diff updates when in capture mode
    if (get(app).activity === 'capture')
        return;
    let b = get(bearing);
    let res = get(photos_in_area);
    for (let i = 0; i < res.length; i++) {
        const updated = updatePhotoBearingData(res[i], b);
        res[i] = { ...updated, range_distance: null };
    }
};

// Keep this subscription to update bearing colors on all photos in area
bearing.subscribe(update_bearing_diff);
photos_in_area.subscribe(update_bearing_diff);




interface TurnEvent {
    type: string;
    dir: string;
}

let events: TurnEvent[] = [];

export async function turn_to_photo_to(dir: string) {
    events.push({type: 'turn_to_photo_to', dir: dir});
    await handle_events();
}

async function handle_events() {
    await tick();
    if (events.length === 0) return;
    let e = events[events.length - 1];
    events = [];
    let dir = e.dir;
    console.log('turn_to_photo_to:', dir);
    
    // Get current state  
    const currentPhotoToLeft = get(photo_to_left);
    const currentPhotoToRight = get(photo_to_right);
    
    console.log('Current state:', {
        hasPhotoToLeft: !!currentPhotoToLeft,
        hasPhotoToRight: !!currentPhotoToRight
    });
    
    if (dir === 'left') {
        if (currentPhotoToLeft) {
            console.log('Turning to left photo:', currentPhotoToLeft.id, 'bearing:', currentPhotoToLeft.bearing);
            bearing.set(currentPhotoToLeft.bearing);
        } else {
            console.warn('No photo to left available');
        }
    } else if (dir === 'right') {
        if (currentPhotoToRight) {
            console.log('Turning to right photo:', currentPhotoToRight.id, 'bearing:', currentPhotoToRight.bearing);
            console.log('Current bearing:', get(bearing), 'New bearing:', currentPhotoToRight.bearing);
            bearing.set(currentPhotoToRight.bearing);
        } else {
            console.warn('No photo to right available');
        }
    }
}

export function update_bearing(diff: number) {
    let b = get(bearing);
    bearing.set(b + diff);
    
    // Update capture location when bearing changes
    const p = get(pos);
    updateCaptureLocation(p.center.lat, p.center.lng, b + diff);
}




export function reversed<T>(list: T[]): T[]
{
    let res = [];
    for (let i = list.length - 1; i >= 0; i--) {
        res.push(list[i]);
    }
    return res;
}

// Helper function to get center coordinates from current position
function getCurrentCenter() {
    const p2 = get(pos2);
    return calculateCenterFromBounds(p2);
}

// Helper function to trigger bearing update for bearing-only changes (user rotation)
function triggerBearingUpdate() {
    if (get(app).activity === 'capture') {
        return;
    }
    const b = get(bearing);
    const photosInArea = get(photos_in_area);
    
    console.log('🔄 triggerBearingUpdate:', {
        bearing: b,
        photosInArea: photosInArea.length
    });
    
    // For bearing-only changes, use current photos in range if available
    const data = photoProcessingAdapter.getCurrentData();
    if (data && data.photosInRange.length > 0) {
        console.log('🔄 Using cached photos for bearing update:', {
            photosInRange: data.photosInRange.length
        });
        
        // Recalculate navigation structure with new bearing but same photos
        const withBearings = updatePhotoBearings(data.photosInRange, b);
        const sorted = sortPhotosByAngularDistance(withBearings, b);
        const navResult = buildNavigationStructure(sorted, withBearings);
        
        console.log('🔄 Navigation result:', {
            photoInFront: !!navResult.photoInFront,
            photoToLeft: !!navResult.photoToLeft,
            photoToRight: !!navResult.photoToRight,
            photosToLeft: navResult.photosToLeft.length,
            photosToRight: navResult.photosToRight.length
        });
        
        // Update navigation directly
        photo_in_front.set(navResult.photoInFront);
        photo_to_left.set(navResult.photoToLeft);
        photo_to_right.set(navResult.photoToRight);
        photos_to_left.set(navResult.photosToLeft);
        photos_to_right.set(navResult.photosToRight);
    } else {
        console.log('🔄 No cached data, falling back to full update');
        // Fall back to full update if no current data
        const center = getCurrentCenter();
        photoProcessingAdapter.updateBearingAndCenter(b, center);
    }
}

// Helper function to trigger area update after photo filtering completes (map movement)
function triggerAreaUpdate() {
    if (get(app).activity === 'capture') {
        return;
    }
    const b = get(bearing);
    const center = getCurrentCenter();
    const photosInArea = get(photos_in_area);
    
    console.log('🗺️ triggerAreaUpdate:', {
        bearing: b,
        photosInArea: photosInArea.length,
        center: `${center.lat.toFixed(6)}, ${center.lng.toFixed(6)}`
    });
    
    // After area update, we need to recalculate navigation with new photos in area
    // Use full update since photo set has changed
    photoProcessingAdapter.updateBearingAndCenter(b, center);
}

// Subscribe to recalculateBearingDiffForAllPhotosInArea setting
recalculateBearingDiffForAllPhotosInArea.subscribe(value => {
    photoProcessingAdapter.updateConfig({ recalculateBearingDiffForAllPhotosInArea: value });
});

// Initialize photo processing service
function initializePhotoProcessing() {
    // Register result handlers
    photoProcessingAdapter.onResult('filter_area', (result: AreaFilterResult) => {
        console.log('📍 Filter area result:', {
            hillview: result.hillviewPhotosInArea.length,
            mapillary: result.mapillaryPhotosInArea.length,
            total: result.photosInArea.length
        });
        hillview_photos_in_area.set(result.hillviewPhotosInArea);
        mapillary_photos_in_area.set(result.mapillaryPhotosInArea);
        photos_in_area.set(result.photosInArea);

        console.log('📍 Updated photos_in_area store:', {
            newLength: result.photosInArea.length,
            storeLength: get(photos_in_area).length
        });

        // Trigger area update after area filter completes to update navigation photos
        // This ensures photos_to_left/photos_to_right are recalculated with new photos in area
        triggerAreaUpdate();
    });

    photoProcessingAdapter.onResult('update_bearing_and_center', (result: BearingResult) => {
        // Only update photos_in_area if we were processing photos_in_area
        // photos_in_area.set(result.photosInArea);
        
        // Suspend updates when in capture mode
        if (get(app).activity === 'capture') {
            return;
        }
        
        const currentPhotosInArea = get(photos_in_area);
        console.log('🧭 Navigation update - photos available:', {
            photosInArea: currentPhotosInArea.length,
            photoInFront: !!result.photoInFront,
            photoToLeft: !!result.photoToLeft,  
            photoToRight: !!result.photoToRight,
            leftCount: result.photosToLeft.length,
            rightCount: result.photosToRight.length
        });
        
        photo_in_front.set(result.photoInFront);
        photo_to_left.set(result.photoToLeft);
        photo_to_right.set(result.photoToRight);
        photos_to_left.set(result.photosToLeft);
        photos_to_right.set(result.photosToRight);
        
        console.log('🧭 Updated navigation stores:', {
            photos_to_left: get(photos_to_left).length,
            photos_to_right: get(photos_to_right).length
        });
    });
    
    // Update photo store when photos change
    let hasInitialPhotosLoaded = false;
    hillview_photos.subscribe(photos => {
        const allPhotos = [
            ...photos,
            ...Array.from(get(mapillary_photos).values())
        ];
        photoProcessingAdapter.updatePhotoStore(allPhotos);
        
        // Trigger initial filtering when photos first load
        if (!hasInitialPhotosLoaded && photos.length > 0) {
            hasInitialPhotosLoaded = true;
            const p2 = get(pos2);
            const srcs = get(sources);
            
            console.log('Initial photos loaded, triggering filter', {
                bounds: { top_left: p2.top_left, bottom_right: p2.bottom_right },
                range: p2.range,
                sources: srcs.map(s => ({ id: s.id, enabled: s.enabled }))
            });
            photoProcessingAdapter.queueAreaFilter(
                { top_left: p2.top_left, bottom_right: p2.bottom_right },
                p2.range,
                srcs
            );
            
            // Also trigger area update to select initial photo after photos load
            triggerAreaUpdate();
        }
    });
    
    mapillary_photos.subscribe(photos => {
        const allPhotos = [
            ...get(hillview_photos),
            ...Array.from(photos.values())
        ];
        photoProcessingAdapter.updatePhotoStore(allPhotos);
    });
    
    // Replace direct subscriptions with queued operations
    pos2.subscribe(p2 => {
        const photosInArea = get(photos_in_area);
        console.log('🗺️ Map position changed:', {
            bounds: {
                nw: `${p2.top_left.lat.toFixed(6)}, ${p2.top_left.lng.toFixed(6)}`,
                se: `${p2.bottom_right.lat.toFixed(6)}, ${p2.bottom_right.lng.toFixed(6)}`
            },
            range: p2.range,
            currentPhotosInArea: photosInArea.length
        });
        
        photoProcessingAdapter.queueAreaFilter(
            { top_left: p2.top_left, bottom_right: p2.bottom_right },
            p2.range,
            get(sources)
        );
        
        // Note: triggerBearingUpdate() moved to area filter completion callback
        // to avoid race condition with async photo processing
    });
    
    // When bearing changes (user turns), update navigation using photos in range
    bearing.subscribe(b => {
        // Skip bearing updates when in capture mode
        if (get(app).activity === 'capture') {
            return;
        }
        
        const photosInArea = get(photos_in_area);
        console.log('🧭 Bearing changed:', {
            newBearing: b,
            photosInArea: photosInArea.length
        });
        
        // Get current data which contains photos in range
        const data = photoProcessingAdapter.getCurrentData();
        if (data && data.photosInRange.length > 0) {
            console.log('🧭 Using direct bearing update with cached data:', {
                photosInRange: data.photosInRange.length
            });
            
            const withBearings = updatePhotoBearings(data.photosInRange, b);
            const sorted = sortPhotosByAngularDistance(withBearings, b);
            const navResult = buildNavigationStructure(sorted, withBearings);
            
            console.log('🧭 Direct bearing update result:', {
                photoInFront: !!navResult.photoInFront,
                photoToLeft: !!navResult.photoToLeft,
                photoToRight: !!navResult.photoToRight,
                photosToLeft: navResult.photosToLeft.length,
                photosToRight: navResult.photosToRight.length
            });
            
            // Update navigation pointers
            photo_in_front.set(navResult.photoInFront);
            photo_to_left.set(navResult.photoToLeft);
            photo_to_right.set(navResult.photoToRight);
            photos_to_left.set(navResult.photosToLeft);
            photos_to_right.set(navResult.photosToRight);
        } else {
            console.log('🧭 No cached data for bearing update');
        }
    });
    
    // Watch for activity changes to trigger updates when switching back to view mode
    let previousActivity: string | null = null;
    app.subscribe(appState => {
        if (previousActivity === 'capture' && appState.activity === 'view') {
            // Switching from capture to view, trigger updates
            const p2 = get(pos2);
            const center = getCurrentCenter();
            const photosInArea = get(photos_in_area);
            triggerBearingUpdate();
        }
        previousActivity = appState.activity;
    });
    
    // REMOVED: Redundant subscription that was causing excessive re-renders
    // The bearing subscription above already handles updates when bearing changes
    // Photos in range updates are handled by the worker callbacks
}

// Initialize on module load
initializePhotoProcessing();

// Expose debugging utilities globally
if (typeof window !== 'undefined') {
    (window as any).photoQueue = {
        getStatus: () => photoProcessingAdapter.getQueueStatus(),
        clearQueue: () => photoProcessingAdapter.clearQueue(),
        adapter: photoProcessingAdapter
    };
    console.log('Photo queue debugging available: window.photoQueue.getStatus(), window.photoQueue.clearQueue()');
}
