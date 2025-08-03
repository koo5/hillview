import {LatLng} from 'leaflet';
import {get, writable} from "svelte/store";
import { staggeredLocalStorageSharedStore } from './svelte-shared-store';
import type { PhotoData } from './sources';
import { geoPicsUrl } from './config';
import { auth } from './auth.svelte';
import { userPhotos } from './stores';

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
    {id: 'hillview', name: 'Hillview', type: 'json', enabled: false, requests: [], color: '#000', url: `${geoPicsUrl}/files.json`},
    {id: 'mapillary', name: 'Mapillary', type: 'mapillary', enabled: true, requests: [], color: '#888'},
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
// Mapillary photos now handled by worker
// export let mapillary_photos = writable<Map<string, any>>(new Map());
export let mapillary_cache_status = writable<any>({ uncached_regions: 0, is_streaming: false, total_live_photos: 0 });

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

// Mapillary functionality moved to worker
let old_sources: Source[] = JSON.parse(JSON.stringify(get(sources)));

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
        
        // Mapillary source changes now handled by worker
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