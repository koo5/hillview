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

// Separate persisted app settings from session-specific state
export let appSettings = staggeredLocalStorageSharedStore('appSettings', {
    debug: 0,
    displayMode: 'split' as 'split' | 'max',
    activity: 'view' as 'capture' | 'view',
});

// Main app store with both persisted and session-specific fields
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
});

// Sync persisted settings with main app store
appSettings.subscribe(settings => {
    const currentApp = get(app);
    // Only update if values have actually changed
    if (currentApp.debug != settings.debug ||
        currentApp.displayMode != settings.displayMode ||
        currentApp.activity != settings.activity) {
        app.update(a => ({
            ...a,
            debug: settings.debug,
            displayMode: settings.displayMode,
            activity: settings.activity
        }));
    }
});

// Also sync changes back to persisted settings when app store changes
app.subscribe(appState => {
    const currentSettings = get(appSettings);
    // Only update if values have actually changed
    if ((!isNaN(currentSettings.debug && !isNaN(appState.debug)) && currentSettings.debug != appState.debug) ||
        currentSettings.displayMode != appState.displayMode ||
        currentSettings.activity != appState.activity) {
        console.log('currentSettings.debug:', currentSettings.debug, 'appState.debug:', appState.debug, 'currentSettings.displayMode:', currentSettings.displayMode, 'appState.displayMode:', appState.displayMode, 'currentSettings.activity:', currentSettings.activity, 'appState.activity:', appState.activity);
        setTimeout(() => {
            console.log('Updating appSettings from app state:', JSON.stringify(appState));
            appSettings.update(settings => ({
                ...settings,
                debug: appState.debug,
                displayMode: appState.displayMode,
                activity: appState.activity
            }));
        }, 500);
    }
});

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
// Unified Mapillary debug status store
export interface MapillaryDebugStatus {
  // Legacy fields (keep for compatibility)
  uncached_regions: number;
  is_streaming: boolean;
  total_live_photos: number;
  
  // New detailed status fields
  stream_phase: 'idle' | 'connecting' | 'receiving_cached' | 'receiving_live' | 'complete' | 'error';
  completed_regions: number;
  last_request_time?: number;
  last_response_time?: number;
  current_url?: string;
  last_error?: string;
  last_bounds?: {
    topLeftLat: number;
    topLeftLon: number;
    bottomRightLat: number;
    bottomRightLon: number;
  };
}

export let mapillary_cache_status = writable<MapillaryDebugStatus>({ 
  uncached_regions: 0, 
  is_streaming: false, 
  total_live_photos: 0,
  stream_phase: 'idle',
  completed_regions: 0
});

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