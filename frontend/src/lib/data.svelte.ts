import {LatLng} from 'leaflet';
import {get, writable} from "svelte/store";
import { staggeredLocalStorageSharedStore } from './svelte-shared-store';
import type { PhotoData } from './sources';
import { geoPicsUrl } from './config';
import { auth } from './auth.svelte';
import { userPhotos } from './stores';
import { createMapillaryStreamService, type MapillaryStreamCallbacks } from './mapillaryStreamService';

// Source interface for compatibility
export interface Source {
    id: string;
    name: string;
    type: 'json' | 'mapillary' | 'device' | 'directory';
    enabled: boolean;
    requests: number[];
    color: string;
    url?: string;
    path?: string;
}

export const sources = writable<Source[]>([
    {id: 'hillview', name: 'Hillview', type: 'json', enabled: true, requests: [], color: '#000', url: `${geoPicsUrl}/files.json`},
    {id: 'mapillary', name: 'Mapillary', type: 'mapillary', enabled: false, requests: [], color: '#888'},
    {id: 'device', name: 'My Device', type: 'device', enabled: true, requests: [], color: '#4a90e2'},
]);

export let client_id = staggeredLocalStorageSharedStore('client_id', Math.random().toString(36));

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
    displayMode: 'split',
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

// Core stores - now using simplified mapState
export let hillview_photos = writable<any[]>([]);
export let mapillary_photos = writable<Map<string, any>>(new Map());
export let mapillary_cache_status = writable<any>({});

// Import new mapState for legacy compatibility only
import { 
    spatialState, 
    visualState, 
    photoInFront, 
    photoToLeft, 
    photoToRight, 
    updateBearing as mapStateUpdateBearing
} from './mapState';

// Essential exports still used by components
export { photoInFront as photo_in_front };
export { photoToLeft as photo_to_left };
export { photoToRight as photo_to_right };

// Mapillary functionality
let last_mapillary_request = 0;
let mapillary_request_timer: any = null;
let mapillary_stream_service: any = null;
let old_sources: Source[] = JSON.parse(JSON.stringify(get(sources)));

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
        if (mapillary_stream_service) {
            mapillary_stream_service.stopStream();
        }
        mapillary_cache_status.set({ uncached_regions: 0, is_streaming: false, total_live_photos: 0 });
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

    let spatial = get(spatialState);
    if (!spatial.bounds) return;
    
    sources.update(s => {
        src!.requests.push(ts);
        return s;
    });

    if (mapillary_stream_service) {
        mapillary_stream_service.stopStream();
    }

    const callbacks: MapillaryStreamCallbacks = {
        onCachedPhotos: (photos) => {
            console.log('Received cached photos:', photos.length);
            if (photos.length > 0) {
                const added = processMapillaryPhotos(photos, src!);
                console.log(`Added ${added} cached photos`);
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
            const added = processMapillaryPhotos(photos, src!);
            console.log(`Added ${added} live photos from region ${region}`);
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
                src!.requests.splice(src!.requests.indexOf(ts), 1);
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
                src!.requests.splice(src!.requests.indexOf(ts), 1);
                return s;
            });
        }
    };

    mapillary_stream_service = createMapillaryStreamService(callbacks);
    
    try {
        const bounds = spatial.bounds;
        await mapillary_stream_service.startStream(
            bounds.top_left.lat,
            bounds.top_left.lng,
            bounds.bottom_right.lat,
            bounds.bottom_right.lng
        );
    } catch (error) {
        console.error('Error starting Mapillary stream:', error);
        mapillary_cache_status.update(status => ({
            ...status,
            is_streaming: false
        }));
        
        sources.update(s => {
            src!.requests.splice(src!.requests.indexOf(ts), 1);
            return s;
        });
    }
}

// Subscribe to spatial changes for mapillary updates
spatialState.subscribe(get_mapillary_photos);

sources.subscribe(async (s: Source[]) => {
    console.log('sources changed:', s);
    let old = JSON.parse(JSON.stringify(old_sources));
    old_sources = JSON.parse(JSON.stringify(s));
    
    const changedSources = s.filter((src, i) => {
        const oldSrc = old.find((o: Source) => o.id === src.id);
        return !oldSrc || oldSrc.enabled !== src.enabled;
    });
    
    if (changedSources.length > 0) {
        console.log('Source enabled states changed:', changedSources.map(s => ({ id: s.id, enabled: s.enabled })));
        
        const mapillaryChanged = changedSources.find(s => s.id === 'mapillary');
        
        if (mapillaryChanged && mapillaryChanged.enabled) {
            console.log('get_mapillary_photos');
            await get_mapillary_photos();
        }
    }
});

// Navigation functions using new mapState
export async function turn_to_photo_to(dir: string) {
    const currentPhotoToLeft = get(photoToLeft);
    const currentPhotoToRight = get(photoToRight);
    
    console.log('turn_to_photo_to:', dir, {
        hasPhotoToLeft: !!currentPhotoToLeft,
        hasPhotoToRight: !!currentPhotoToRight
    });
    
    if (dir === 'left' && currentPhotoToLeft) {
        console.log('Turning to left photo:', currentPhotoToLeft.id, 'bearing:', currentPhotoToLeft.bearing);
        mapStateUpdateBearing(currentPhotoToLeft.bearing);
    } else if (dir === 'right' && currentPhotoToRight) {
        console.log('Turning to right photo:', currentPhotoToRight.id, 'bearing:', currentPhotoToRight.bearing);
        mapStateUpdateBearing(currentPhotoToRight.bearing);
    } else {
        console.warn(`No photo to ${dir} available`);
    }
}

export function update_bearing(diff: number) {
    const current = get(visualState);
    const newBearing = (current.bearing + diff + 360) % 360;
    mapStateUpdateBearing(newBearing);
}

export function reversed<T>(list: T[]): T[] {
    let res = [];
    for (let i = list.length - 1; i >= 0; i--) {
        res.push(list[i]);
    }
    return res;
}