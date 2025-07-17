import {type Photo} from "./types";
import Angles from 'angles';
//import {DMS} from "tsgeo/Formatter/Coordinate/DMS";
import {space_db} from "./debug_server.js";
import { updatePhotoBearingData, calculateAngularDistance } from './utils/bearingUtils';
import { calculateDistance, calculateCenterFromBounds } from './utils/distanceUtils';
import { buildNavigationStructure } from './utils/photoNavigationUtils';
import {LatLng} from 'leaflet';
import {get, writable} from "svelte/store";
import {
    localStorageReadOnceSharedStore,
    localStorageSharedStore
} from './svelte-shared-store';
import { fixup_bearings, sources, type PhotoData, type Source } from './sources';
import {tick} from "svelte";
import { auth } from './auth.svelte';
import { userPhotos } from './stores';
import { updateCaptureLocationFromMap } from './captureLocation';
import { photoProcessingAdapter } from './photoProcessingAdapter';
import { createMapillaryStreamService, type MapillaryStreamCallbacks } from './mapillaryStreamService';

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

export const geoPicsUrl = import.meta.env.VITE_REACT_APP_GEO_PICS_URL; //+'2'

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


function source_by_id(id: string) {
    return get(sources).find(s => s.id === id);
}

export let pos = localStorageReadOnceSharedStore('pos', {
    center: new LatLng(50.06173640462974,
        14.514600411057472),
    zoom: 20,
    reason: 'default'
});

// Initialize capture location with default map position
const initialPos = get(pos);
updateCaptureLocationFromMap(initialPos.center.lat, initialPos.center.lng, 0);

export function update_pos(cb: (pos: any) => any)
{
    let v = get(pos);
    let n = cb(v);
    if (n.center.lat == v.center.lat && n.center.lng == v.center.lng && n.zoom == v.zoom) return;
    pos.set(n);
    
    // Update capture location when map position changes
    updateCaptureLocationFromMap(n.center.lat, n.center.lng, get(bearing));
}


export let pos2 = writable({
    top_left: new LatLng(0, 0),
    bottom_right: new LatLng(10, 10),
    range: 1,
});
export function update_pos2(cb: (pos2: any) => any)
{
    let v = get(pos2);
    let n = cb(v);
    if (n.top_left.lat == v.top_left.lat && n.top_left.lng == v.top_left.lng && n.bottom_right.lat == v.bottom_right.lat && n.bottom_right.lng == v.bottom_right.lng && n.range == v.range) return;
    pos2.set(n);
}

export let bearing = localStorageSharedStore('bearing', 0);
export let recalculateBearingDiffForAllPhotosInArea = localStorageSharedStore('recalculateBearingDiffForAllPhotosInArea', false);

export let hillview_photos = writable<PhotoData[]>([]);
export let hillview_photos_in_area = writable<PhotoData[]>([]);
export let mapillary_photos = writable(new Map());
export let mapillary_photos_in_area = writable<any[]>([]);
export let mapillary_cache_status = writable({ uncached_regions: 0, is_streaming: false, total_live_photos: 0 });
export let photos_in_area = writable<any[]>([]);
export let photos_in_range = writable<any[]>([]);

export let photo_in_front = writable<any | null>(null);
export let photos_to_left = writable<any[]>([]);
export let photos_to_right = writable<any[]>([]);
export let photo_to_left = writable<any | null>(null);
export let photo_to_right = writable<any | null>(null);


bearing.subscribe(b => {
    let b2 = (b + 360) % 360;
    if (b2 !== b) {
        bearing.set(b2);
    }
    
    // Update capture location when bearing changes
    const p = get(pos);
    updateCaptureLocationFromMap(p.center.lat, p.center.lng, b2);
});

pos.subscribe(p => {

    console.log('pos changed:', p);

    // Keep longitude in -180 to 180 range instead of 0-360
    if (p.center.lng > 180) {
        p.center.lng -= 360;
        pos.set({...p, reason: 'wrap'})
    }
    if (p.center.lng < -180) {
        p.center.lng += 360;
        pos.set({...p, reason: 'wrap'})
    }
});

async function share_state() {
    let p = get(pos);
    let p2 = get(pos2);
    await space_db.transaction('rw', 'state', async () => {
        await space_db.state.clear();
        let state = {
            ts: Date.now(),
            center: p.center,
            zoom: p.zoom,
            top_left: p2.top_left,
            bottom_right: p2.bottom_right,
            range: p2.range,
            bearing: get(bearing)
        }
        //console.log('Saving state:', state);
        space_db.state.add(state);
    });
};

//pos.subscribe(share_state);
//bearing.subscribe(share_state);

const area_tolerance = 0.1;

function filter_hillview_photos_by_area() {

    if (!get(sources).find(s => s.id === 'hillview')?.enabled) {
        hillview_photos_in_area.set([]);
        return;
    }

    let p2 = get(pos2);
    let b = get(bearing);
    let ph = get(hillview_photos);
    //console.log('filter_hillview_photos_by_area: p2.top_left:', p2.top_left, 'p2.bottom_right:', p2.bottom_right);

    let window_x = p2.bottom_right.lng - p2.top_left.lng;
    let window_y = p2.top_left.lat - p2.bottom_right.lat;

    let res = ph.filter(photo => {
        //console.log('photo:', photo);
        let yes = photo.coord.lat < p2.top_left.lat + window_y && photo.coord.lat > p2.bottom_right.lat - window_y &&
            photo.coord.lng > p2.top_left.lng - window_x && photo.coord.lng < p2.bottom_right.lng + window_x;
        //console.log('yes:', yes);
        return yes;
    });
    console.log('hillview photos in area:', res.length);
    hillview_photos_in_area.set(res);
}

// Now handled by photoProcessingService
// pos2.subscribe(filter_hillview_photos_by_area);
// hillview_photos.subscribe(filter_hillview_photos_by_area);

function collect_photos_in_area() {
    let phs = [...get(hillview_photos_in_area), ...get(mapillary_photos_in_area)];
    fixup_bearings(phs);
    console.log('collect_photos_in_area:', phs.length, 'photos (hillview:', get(hillview_photos_in_area).length, ', mapillary:', get(mapillary_photos_in_area).length, ')');
    photos_in_area.set(phs);
}

// Now handled by photoProcessingService
// hillview_photos_in_area.subscribe(collect_photos_in_area);
// mapillary_photos_in_area.subscribe(collect_photos_in_area);

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
            
            // Also trigger bearing update
            triggerBearingUpdate();
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
    
    // Check if any source enabled state changed
    const hillviewChanged = old.find((src: Source) => src.id === 'hillview')?.enabled !== s.find((src: Source) => src.id === 'hillview')?.enabled;
    const mapillaryChanged = old.find((src: Source) => src.id === 'mapillary')?.enabled !== s.find((src: Source) => src.id === 'mapillary')?.enabled;
    const mapillaryEnabled = s.find((src: Source) => src.id === 'mapillary')?.enabled;
    
    if (hillviewChanged || (mapillaryChanged && !mapillaryEnabled)) {
        // Re-filter with new source states
        // Only queue immediately if Hillview changed or Mapillary was disabled
        // If Mapillary was enabled, the filter will be queued after photos load
        const p2 = get(pos2);
        photoProcessingAdapter.queueAreaFilter(
            { top_left: p2.top_left, bottom_right: p2.bottom_right },
            p2.range,
            s
        );
    }
    
    if (mapillaryChanged && mapillaryEnabled) {
        console.log('get_mapillary_photos');
        await get_mapillary_photos();
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

function filter_photos_in_range() {
    let p2 = get(pos2);
    let ph = get(photos_in_area);
    const center = getCurrentCenter();
    let res = ph.filter(photo => {
        photo.range_distance = calculateDistance(photo.coord, center);
        //console.log('photo.range_distance:', photo.range_distance, 'p2.range:', p2.range);
        if (photo.range_distance > p2.range) {
            photo.range_distance = null;
        }
        return photo.range_distance !== null;
    });
    console.log('Photos in range:', res.length);
    photos_in_range.set(res);
};

// Now handled by photoProcessingService
// photos_in_area.subscribe(filter_photos_in_range);

function update_view() {
    // Suspend updates when in capture mode
    if (get(app).activity === 'capture') {
        return;
    }
    
    let b = get(bearing);
    let ph = get(photos_in_range);
    if (ph.length === 0) {
        photo_in_front.set(null);
        photo_to_left.set(null);
        photo_to_right.set(null);
        photos_to_left.set([]);
        photos_to_right.set([]);
        return;
    }
    
    // Add angular distance to photos
    ph.map(photo => {
        photo.angular_distance_abs = calculateAngularDistance(b, photo.bearing);
    });
    
    // Sort by angular distance
    let phs = ph.slice().sort((a, b) => a.angular_distance_abs - b.angular_distance_abs);
    
    // Use navigation utility to build structure
    const navResult = buildNavigationStructure(phs, ph);
    
    photo_in_front.set(navResult.photoInFront);
    photo_to_left.set(navResult.photoToLeft);
    photo_to_right.set(navResult.photoToRight);
    photos_to_left.set(navResult.photosToLeft);
    photos_to_right.set(navResult.photosToRight);
}

// Now handled by photoProcessingService
// bearing.subscribe(update_view);
// photos_in_range.subscribe(update_view);

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
    const currentPhotosInRange = get(photos_in_range);
    const currentPhotoToLeft = get(photo_to_left);
    const currentPhotoToRight = get(photo_to_right);
    
    console.log('Current state:', {
        photosInRangeCount: currentPhotosInRange.length,
        hasPhotoToLeft: !!currentPhotoToLeft,
        hasPhotoToRight: !!currentPhotoToRight
    });
    
    if (dir === 'left') {
        if (currentPhotoToLeft) {
            console.log('Turning to left photo:', currentPhotoToLeft.bearing);
            bearing.set(currentPhotoToLeft.bearing);
        } else {
            console.warn('No photo to left available');
        }
    } else if (dir === 'right') {
        if (currentPhotoToRight) {
            console.log('Turning to right photo:', currentPhotoToRight.bearing);
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
    updateCaptureLocationFromMap(p.center.lat, p.center.lng, b + diff);
}



function RGB2HTML(red: number, green: number, blue: number)
{
    red = Math.min(255, Math.max(0, Math.round(red)));
    green = Math.min(255, Math.max(0, Math.round(green)));
    blue = Math.min(255, Math.max(0, Math.round(blue)));
    let r = red.toString(16);
    let g = green.toString(16);
    let b = blue.toString(16);
    if (r.length == 1) r = '0' + r;
    if (g.length == 1) g = '0' + g;
    if (b.length == 1) b = '0' + b;
    return '#' + r + g + b;
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

// Helper function to trigger bearing update with current position
function triggerBearingUpdate() {
    // Skip bearing updates when in capture mode
    if (get(app).activity === 'capture') {
        return;
    }
    const b = get(bearing);
    const center = getCurrentCenter();
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
        
        // Queue distance calculation (skip when in capture mode)
        if (get(app).activity !== 'capture') {
            const p2 = get(pos2);
            const center = getCurrentCenter();
            const photoIds = result.photosInArea.map(p => p.id);
            photoProcessingAdapter.queueDistanceCalculation(photoIds, center, p2.range);
        }
    });
    
    photoProcessingAdapter.onResult('calculate_distances', (result: DistanceResult) => {
        photos_in_range.set(result.photosInRange);
    });
    
    photoProcessingAdapter.onResult('update_bearing_and_center', (result: BearingResult) => {
        // Only update photos_in_area if we were processing photos_in_area
        // photos_in_area.set(result.photosInArea);
        
        // Suspend updates when in capture mode
        if (get(app).activity === 'capture') {
            return;
        }
        
        photo_in_front.set(result.photoInFront);
        photo_to_left.set(result.photoToLeft);
        photo_to_right.set(result.photoToRight);
        photos_to_left.set(result.photosToLeft);
        photos_to_right.set(result.photosToRight);
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
            
            // Also trigger bearing update to select initial photo
            triggerBearingUpdate();
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
        photoProcessingAdapter.queueAreaFilter(
            { top_left: p2.top_left, bottom_right: p2.bottom_right },
            p2.range,
            get(sources)
        );
        
        // Also trigger bearing update to select photo in front
        triggerBearingUpdate();
    });
    
    bearing.subscribe(b => {
        triggerBearingUpdate();
    });
    
    // Watch for activity changes to trigger updates when switching back to view mode
    let previousActivity: string | null = null;
    app.subscribe(appState => {
        if (previousActivity === 'capture' && appState.activity === 'view') {
            // Switching from capture to view, trigger updates
            const p2 = get(pos2);
            const center = getCurrentCenter();
            const photosInArea = get(photos_in_area);
            if (photosInArea.length > 0) {
                const photoIds = photosInArea.map((p: any) => p.id);
                photoProcessingAdapter.queueDistanceCalculation(photoIds, center, p2.range);
            }
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
