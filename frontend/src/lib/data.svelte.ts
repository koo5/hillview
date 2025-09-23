import {get, writable, derived} from "svelte/store";
import {staggeredLocalStorageSharedStore} from './svelte-shared-store';
import {backendUrl} from './config';
import {MAX_DEBUG_MODES} from './constants';
import {auth} from './auth.svelte';
// Import new mapState for legacy compatibility only
import {photoInFront, photoToLeft, photoToRight, updateBearing as mapStateUpdateBearing, bearingState} from './mapState';
import {TAURI} from "$lib/tauri";

// Device source subtypes
export type subtype = 'hillview' | 'folder' | 'gallery';

// Source interface for compatibility
export interface Source {
    id: string;
    name: string;
    type: 'stream' | 'device';
    enabled: boolean;
    requests: number[];
    color: string;
    url?: string;
    path?: string;
    // Device-specific properties
    subtype?: subtype;
}

const baseSources: Source[] = [
    {id: 'hillview', name: 'Hillview', type: 'stream', enabled: !import.meta.env.VITE_PICS_OFF, requests: [], color: '#000', url: `${backendUrl}/hillview`},
    {id: 'mapillary', name: 'Mapillary', type: 'stream', enabled: !import.meta.env.VITE_PICS_OFF, requests: [], color: '#888', url: `${backendUrl}/mapillary`}
];

const deviceSources: Source[] = !TAURI ? [] : [
    {id: 'device', name: 'My Device', type: 'device', enabled: !import.meta.env.VITE_PICS_OFF, requests: [], color: '#4a90e2', subtype: 'hillview'}
];

export const sources = writable<Source[]>([...baseSources, ...deviceSources]);

export let client_id = staggeredLocalStorageSharedStore('client_id', Math.random().toString(36));

// Camera overlay opacity store (0 = fully transparent, 5 = most opaque)
export let cameraOverlayOpacity = staggeredLocalStorageSharedStore('cameraOverlayOpacity', 3);

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
            activity: !!import.meta.env.VITE_PICS_OFF ? 'view' : settings.activity
        }));
    }
});

// Also sync changes back to persisted settings when app store changes
app.subscribe(appState => {
    const currentSettings = get(appSettings);
    // Only update if values have actually changed
    if (((!isNaN(currentSettings.debug) && !isNaN(appState.debug)) && currentSettings.debug != appState.debug) ||
        currentSettings.displayMode != appState.displayMode ||
        currentSettings.activity != appState.activity) {
        console.log('🢄currentSettings.debug:', currentSettings.debug, 'appState.debug:', appState.debug, 'currentSettings.displayMode:', currentSettings.displayMode, 'appState.displayMode:', appState.displayMode, 'currentSettings.activity:', currentSettings.activity, 'appState.activity:', appState.activity);
        setTimeout(() => {
            console.log('🢄Updating appSettings from app state:', JSON.stringify(appState));
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

// Generic source loading status for all stream sources
export interface SourceLoadingStatus {
    [sourceId: string]: {
        isLoading: boolean;
        progress?: string;
        error?: string;
    };
}

export let sourceLoadingStatus = writable<SourceLoadingStatus>({});

// Derived store to check if any enabled source is loading
export const anySourceLoading = derived(
    [sources, sourceLoadingStatus],
    ([sources, loadingStatus]) => {
        return sources.some(source => {
            if (!source.enabled) return false;
            // For stream sources, check loading status
            if (source.type === 'stream') {
                return loadingStatus[source.id]?.isLoading || false;
            }
            // For device sources, check if requests are pending
            return !!(source.requests && source.requests.length);
        });
    }
);

// Essential exports still used by components
export {photoInFront as photo_in_front};
export {photoToLeft as photo_to_left};
export {photoToRight as photo_to_right};

let old_sources: Source[] = [];

sources.subscribe(async (s: Source[]) => {

    let old = JSON.parse(JSON.stringify(old_sources));
    old_sources = JSON.parse(JSON.stringify(s));

	console.log('🢄sources changed: old vs new', old, s);

    const changedSources = s.filter((src, i) => {
        const oldSrc = old.find((o: Source) => o.id === src.id);
        return !oldSrc || oldSrc.enabled !== src.enabled;
    });

    if (changedSources.length > 0) {
        console.log('🢄Source enabled states changed:', changedSources.map(s => ({id: s.id, enabled: s.enabled})));

        // Mapillary source changes now handled by worker
    }
});

// Navigation functions using new mapState
export async function turn_to_photo_to(dir: string) {
    const currentPhotoToLeft = get(photoToLeft);
    const currentPhotoToRight = get(photoToRight);

    console.log('🢄turn_to_photo_to:', dir, {
        hasPhotoToLeft: !!currentPhotoToLeft,
        hasPhotoToRight: !!currentPhotoToRight
    });

    if (dir === 'left' && currentPhotoToLeft) {
        console.log('🢄Turning to left photo:', currentPhotoToLeft.id, 'bearing:', currentPhotoToLeft.bearing);
        mapStateUpdateBearing(currentPhotoToLeft.bearing);
    } else if (dir === 'right' && currentPhotoToRight) {
        console.log('🢄Turning to right photo:', currentPhotoToRight.id, 'bearing:', currentPhotoToRight.bearing);
        mapStateUpdateBearing(currentPhotoToRight.bearing);
    } else {
        console.warn(`🢄No photo to ${dir} available`);
    }
}

// Debug modes constants

export function toggleDebug() {
    app.update(a => {
        const newDebug = ((a.debug || 0) + 1) % (MAX_DEBUG_MODES + 1);
        return {...a, debug: newDebug};
    });
    console.log(`Debug mode toggled to ${get(app).debug}`);
}

export function closeDebug() {
    app.update(a => ({...a, debug: 0}));
    console.log('🢄Debug mode closed');
}
