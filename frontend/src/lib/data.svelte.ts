import {type Photo} from "./types";
import {Coordinate} from "tsgeo/Coordinate";
import {Vincenty} from "tsgeo/Distance/Vincenty";
import Angles from 'angles';
//import {DMS} from "tsgeo/Formatter/Coordinate/DMS";
import {space_db} from "./debug_server.js";
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
import { photoProcessingService } from './photoProcessingService';
import type { AreaFilterResult, DistanceResult, BearingResult } from './photoProcessingService';

export const geoPicsUrl = import.meta.env.VITE_REACT_APP_GEO_PICS_URL; //+'2'

let client_id = localStorageSharedStore('client_id', Math.random().toString(36));

let calculator = new Vincenty();

export let app = writable<{
    error: string | null;
    debug: number;
    displayMode: 'split' | 'max';
    loading?: boolean;
    isAuthenticated?: boolean;
    userPhotos?: any[];
}>({
    error: null,
    debug: 0,
    displayMode: 'split', // 'split' or 'max'
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

export let hillview_photos = writable<PhotoData[]>([]);
export let hillview_photos_in_area = writable<PhotoData[]>([]);
export let mapillary_photos = writable(new Map());
export let mapillary_photos_in_area = writable<any[]>([]);
export let photos_in_area = writable<any[]>([]);
export let photos_in_range = writable<any[]>([]);

export let photo_in_front = writable<any | null>(null);
export let photos_to_left = writable<any[]>([]);
export let photos_to_right = writable<any[]>([]);
export let photo_to_left = writable<any | null>(null);
export let photo_to_right = writable<any | null>(null);

function dist(coord1: any, coord2: any) {
    return calculator.getDistance(new Coordinate(coord1.lat, coord1.lng), new Coordinate(coord2.lat, coord2.lng));
}

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

async function get_mapillary_photos() {

    let src = get(sources).find(s => s.id === 'mapillary');
    if (!src) {
        return;
    }

    let enabled = src.enabled;
    console.log('mapillary enabled:', enabled);
    if (!enabled) {
        filter_mapillary_photos_by_area();
        return;
    }

    let ts = new Date().getTime();

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
    //console.log('get_mapillary_photos:', p2);
    let window_x = 0//p2.bottom_right.lng - p2.top_left.lng;
    let window_y = 0//p2.top_left.lat - p2.bottom_right.lat;
    sources.update(s => {
        src.requests.push(ts);
        return s;
    });

    let res2 = [];
    try {
        let res = await fetch(`${import.meta.env.VITE_BACKEND}/mapillary?top_left_lat=${p2.top_left.lat + window_y}&top_left_lon=${p2.top_left.lng - window_x}&bottom_right_lat=${p2.bottom_right.lat - window_y}&bottom_right_lon=${p2.bottom_right.lng + window_x}&client_id=${get(client_id)}`);
        res2 = await res.json();
        console.log('fetched Mapillary photos:', res2.length);
    }
    catch (e) {
        console.warn('Error fetching Mapillary photos:', e);
    }

    let current_photos = get(mapillary_photos);

    for (let photo of res2) {
        const id = 'mapillary_' + photo.id;

        if (current_photos.has(id)) {
            continue;
        }
        
        let coord = new LatLng(photo.geometry.coordinates[1], photo.geometry.coordinates[0]);
        let bearing = photo.compass_angle;
        let processed_photo = {
            source: src,
            id: id,
            coord: coord,
            bearing: bearing,
            sizes: {
                1024: {width: 1024, height: 768, url: photo.thumb_1024_url},
                50: {width: 50, height: 50, url: photo.thumb_1024_url},
                'full': {width: 1024, height: 768, url: photo.thumb_1024_url}
            },
        };

        current_photos.set(id, processed_photo);
    }

    const limit = 1500;
    if (current_photos.size > limit) {
        let keys = [...current_photos.keys()];
        for (let i = 0; i < current_photos.size - limit; i++) {
            current_photos.delete(keys[i]);
        }
    }
    console.log('Mapillary photos:', current_photos.size);
    mapillary_photos.set(current_photos);
    sources.update(s => {
        src.requests.splice(src.requests.indexOf(ts), 1);
        return s;
    });
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
    
    if (hillviewChanged || mapillaryChanged) {
        // Re-filter with new source states
        const p2 = get(pos2);
        photoProcessingService.queueAreaFilter(
            { top_left: p2.top_left, bottom_right: p2.bottom_right },
            p2.range,
            s
        );
    }
    
    if (mapillaryChanged && s.find((src: Source) => src.id === 'mapillary')?.enabled) {
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

// Now handled by photoProcessingService
// pos2.subscribe(filter_mapillary_photos_by_area);
// mapillary_photos.subscribe(filter_mapillary_photos_by_area);
// sources.subscribe(filter_mapillary_photos_by_area);

function update_bearing_diff() {
    let b = get(bearing);
    let res = get(photos_in_area);
    for (let photo of res) {
        photo.abs_bearing_diff = Math.abs(Angles.distance(b, photo.bearing));
        photo.bearing_color = get_bearing_color(photo);
        photo.range_distance = null;
    }
};

// Keep this subscription to update bearing colors on all photos in area
bearing.subscribe(update_bearing_diff);
photos_in_area.subscribe(update_bearing_diff);

function filter_photos_in_range() {
    let p2 = get(pos2);
    let ph = get(photos_in_area);
    let res = ph.filter(photo => {
        photo.range_distance = dist(photo.coord, new LatLng((p2.top_left.lat + p2.bottom_right.lat) / 2, (p2.top_left.lng + p2.bottom_right.lng) / 2));
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
    ph.map(photo => {
        photo.angular_distance_abs = Math.abs(Angles.distance(b, photo.bearing));
    });
    let phs = ph.slice().sort((a, b) => a.angular_distance_abs - b.angular_distance_abs);
    let fr = phs[0];
    let idx = ph.indexOf(fr);
    let phl = ph[(idx - 1 + ph.length) % ph.length];
    let phr = ph[(idx + 1) % ph.length];
    photo_to_left.set(phl);
    photo_to_right.set(phr);
    photo_in_front.set(fr);
    let phsl = [];
    let phsr = [];
    if (idx !== -1 && ph.length > 1) {
        for (let i = 1; i < 8; i++) {
            let phl_idx = (idx - i + ph.length*2) % ph.length;
            //console.log('phl_idx:', phl_idx);
            let phl = ph[phl_idx];
            //console.log('phl:', phl);
            let phr = ph[(idx + i) % ph.length];
            if (phl && phsl.indexOf(phl) === -1 && phsr.indexOf(phl) === -1)
                phsl.push(phl);
            if (phr && phsl.indexOf(phr) === -1 && phsr.indexOf(phr) === -1)
                phsr.push(phr);
        }
        phsl.reverse();
    }
    // console.log('ph:', ph);
    // console.log('phs:', phs);
    // console.log('phsl:', phsl);
    // console.log('phsr:', phsr);
    photos_to_left.set(phsl);
    photos_to_right.set(phsr);
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

function get_bearing_color(photo: any) {
    if (photo.abs_bearing_diff === null) return '#9E9E9E'; // grey
    return 'hsl(' + Math.round(100 - photo.abs_bearing_diff/2) + ', 100%, 70%)';
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

// Initialize photo processing service
function initializePhotoProcessing() {
    // Register result handlers
    photoProcessingService.onResult('filter_area', (result: AreaFilterResult) => {
        hillview_photos_in_area.set(result.hillviewPhotosInArea);
        mapillary_photos_in_area.set(result.mapillaryPhotosInArea);
        photos_in_area.set(result.photosInArea);
        
        // Queue distance calculation
        const p2 = get(pos2);
        const center = {
            lat: (p2.top_left.lat + p2.bottom_right.lat) / 2,
            lng: (p2.top_left.lng + p2.bottom_right.lng) / 2
        };
        const photoIds = result.photosInArea.map(p => p.id);
        photoProcessingService.queueDistanceCalculation(photoIds, center, p2.range);
    });
    
    photoProcessingService.onResult('calculate_distances', (result: DistanceResult) => {
        photos_in_range.set(result.photosInRange);
    });
    
    photoProcessingService.onResult('update_bearings', (result: BearingResult) => {
        // Only update photos_in_area if we were processing photos_in_area
        // photos_in_area.set(result.photosInArea);
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
        photoProcessingService.updatePhotoStore(allPhotos);
        
        // Trigger initial filtering when photos first load
        if (!hasInitialPhotosLoaded && photos.length > 0) {
            hasInitialPhotosLoaded = true;
            const p2 = get(pos2);
            const srcs = get(sources);
            
            console.log('Initial photos loaded, triggering filter');
            photoProcessingService.queueAreaFilter(
                { top_left: p2.top_left, bottom_right: p2.bottom_right },
                p2.range,
                srcs
            );
        }
    });
    
    mapillary_photos.subscribe(photos => {
        const allPhotos = [
            ...get(hillview_photos),
            ...Array.from(photos.values())
        ];
        photoProcessingService.updatePhotoStore(allPhotos);
    });
    
    // Replace direct subscriptions with queued operations
    pos2.subscribe(p2 => {
        photoProcessingService.queueAreaFilter(
            { top_left: p2.top_left, bottom_right: p2.bottom_right },
            p2.range,
            get(sources)
        );
    });
    
    bearing.subscribe(b => {
        const photosInRange = get(photos_in_range);
        const photoIds = photosInRange.map(p => p.id);
        photoProcessingService.queueBearingUpdate(b, photoIds);
    });
    
    photos_in_range.subscribe(photos => {
        const b = get(bearing);
        const photoIds = photos.map(p => p.id);
        photoProcessingService.queueBearingUpdate(b, photoIds);
    });
}

// Initialize on module load
initializePhotoProcessing();
