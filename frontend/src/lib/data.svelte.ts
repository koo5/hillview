import {get, writable, derived} from "svelte/store";
import {
	localStorageReadOnceSharedStore,
	localStorageSharedStore,
	staggeredLocalStorageSharedStore
} from './svelte-shared-store';
import {backendUrl} from './config';
import {MAX_DEBUG_MODES} from './constants';
import {auth} from './auth.svelte';
import {TAURI, BROWSER} from "$lib/tauri";
// Import new mapState for legacy compatibility only
import {photoInFront, photoToLeft, photoToRight, photoUp, photoDown} from './mapState';
import {updateBearingWithPhoto} from './bearingTracking';
import {getSettings, updateSettings} from "$lib/settings";

const doLog = false;


// Draggable split store for gallery/map split percentage (0-100, percentage for photo panel)
export let splitPercent = localStorageReadOnceSharedStore('splitPercent', 50);
export type AppActivity = 'capture' | 'view' | 'lines';

export interface Line {
	label: string;
	start: { lat: number; lng: number };
	end: { lat: number; lng: number };
	visible: boolean;
}

export let linesVisible = localStorageSharedStore('linesVisible', false);
export let lines = localStorageSharedStore<Line[]>('lines', []);




// Device source subtypes
export type subtype = 'hillview' | 'folder' | 'gallery';

// Source interface for compatibility
export interface Source {
	id: string;
	name: string;
	type: 'stream' | 'device';
	enabled: boolean;
	color: string;
	url?: string;
	path?: string;
	// Device-specific properties
	subtype?: subtype;
	// Mapillary-specific properties
	client_id?: string;
	backend_url?: string;
}

const baseSources: Source[] = [
	{
		id: 'hillview',
		name: 'Hillview',
		type: 'stream',
		enabled: !import.meta.env.VITE_PICS_OFF,
		color: '#000',
		url: `${backendUrl}/hillview`
	},
	{
		id: 'mapillary',
		name: 'Mapillary',
		type: 'stream',
		enabled: false/*!import.meta.env.VITE_PICS_OFF*/,
		color: '#888',
		url: `${backendUrl}/mapillary`
	}
];

const deviceSources: Source[] = TAURI ? [
	{
		id: 'device',
		name: 'Device',
		type: 'device',
		enabled: !import.meta.env.VITE_PICS_OFF,
		color: '#4ae24d',
		subtype: 'hillview'
	}
] : [];

/*console.log('🢄📸 Device sources configuration:', {
	TAURI,
	VITE_PICS_OFF: import.meta.env.VITE_PICS_OFF,
	deviceSourcesCount: deviceSources.length,
	deviceSourceEnabled: deviceSources.length > 0 ? deviceSources[0].enabled : 'N/A'
});*/

// Store source enabled states separately for persistence
const sourceStates = localStorageReadOnceSharedStore('sourceStates', {} as Record<string, boolean>);

// Create reactive sources store that combines base config with persisted states
export const sources = writable<Source[]>([...baseSources, ...deviceSources]);

// Initialize sources with persisted enabled states
sourceStates.subscribe(states => {
	sources.update(srcs => {
		return srcs.map(src => ({
			...src,
			enabled: states[src.id] !== undefined ? states[src.id] : src.enabled
		}));
	});
});

// Save enabled state changes to persistence
sources.subscribe(srcs => {
	const states = srcs.reduce((acc, src) => {
		acc[src.id] = src.enabled;
		return acc;
	}, {} as Record<string, boolean>);

	// Only update if states actually changed to avoid infinite loops
	const currentStates = get(sourceStates);
	if (JSON.stringify(states) !== JSON.stringify(currentStates)) {
		sourceStates.set(states);
	}
});

export let client_id = staggeredLocalStorageSharedStore('client_id', Math.random().toString(36));

// Camera overlay opacity store (0 = fully transparent, 5 = most opaque)
export let cameraOverlayOpacity = staggeredLocalStorageSharedStore('cameraOverlayOpacity', 3);

// Compass calibration view state (takes precedence over camera and gallery views)
export let showCalibrationView = writable(false);

// License identifiers stored on uploaded photos as `legal_rights`:
//   'full1'   — operator / seed content, full ownership (backfilled by migration, never user-selectable)
//   'ccbysa4' — CC BY-SA 4.0 granted by the contributor at upload time
// These stores hold the identifier string the user has consented to for a given upload path.
// null means "no license selected" — upload is blocked for that path.
export let autoUploadLicense = localStorageSharedStore<string | null>('autoUploadLicense', null);
export let manualUploadLicense = localStorageSharedStore<string | null>('manualUploadLicense', null);

// Sync auto-upload license to Settings (bridges to Kotlin SharedPrefs on Android).
// Also: clearing the license disables auto-upload (can't upload without a license).
autoUploadLicense.subscribe(async value => {
	try {
		const current = await getSettings();
		const needsUpdate =
			current.auto_upload_license !== value ||
			(value === null && current.auto_upload_enabled);
		if (needsUpdate) {
			await updateSettings({
				auto_upload_license: value,
				...(value === null ? { auto_upload_enabled: false } : {})
			});
		}
	} catch (error) {
		console.error('Error syncing autoUploadLicense to settings:', error);
	}
});


// Separate persisted app settings from session-specific state
export let appSettings = localStorageReadOnceSharedStore('appSettings', {
	debug: 0,
	debug_enabled: false,
	activity: 'view' as AppActivity,
},500);

// Main app store with both persisted and session-specific fields
export let app = writable<{
	error: string | null;
	debug: number;
	debug_enabled: boolean;
	loading?: boolean;
	is_authenticated?: boolean;
	activity: AppActivity;
}>({
	error: null,
	debug: 0,
	debug_enabled: false,
	activity: 'view',
});

// Sync persisted settings with main app store
appSettings.subscribe(settings => {
	const currentApp = get(app);
	// Only update if values have actually changed
	if (currentApp.debug != settings.debug ||
		currentApp.debug_enabled != settings.debug_enabled ||
		currentApp.activity != settings.activity) {
		app.update(a => ({
			...a,
			debug: settings.debug,
			debug_enabled: settings.debug_enabled,
			activity: !!import.meta.env.VITE_PICS_OFF ? 'view' : settings.activity
		}));
	}
});

// Also sync changes back to persisted settings when app store changes
app.subscribe(appState => {
	const currentSettings = get(appSettings);
	// Only update if values have actually changed
	if (((!isNaN(currentSettings.debug) && !isNaN(appState.debug)) && currentSettings.debug != appState.debug) ||
		currentSettings.debug_enabled != appState.debug_enabled ||
		currentSettings.activity != appState.activity) {
		console.log('🢄currentSettings.debug:', currentSettings.debug, 'appState.debug:', appState.debug, 'currentSettings.activity:', currentSettings.activity, 'appState.activity:', appState.activity);
		appSettings.update(settings => ({
			...settings,
			debug: appState.debug,
			debug_enabled: appState.debug_enabled,
			activity: appState.activity
		}));
	}
});

// Subscribe to auth store to keep app state in sync
auth.subscribe(authState => {
	app.update(a => ({
		...a,
		is_authenticated: authState.is_authenticated
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
		is_loading: boolean;
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
			return loadingStatus[source.id]?.is_loading || false;
		});
	}
);

let old_sources: Source[] = [];

sources.subscribe(async (s: Source[]) => {

	let old = JSON.parse(JSON.stringify(old_sources));
	old_sources = JSON.parse(JSON.stringify(s));

	//console.log('🢄sources changed: old vs new', old, s);

	const changedSources = s.filter((src, i) => {
		const oldSrc = old.find((o: Source) => o.id === src.id);
		return !oldSrc || oldSrc.enabled !== src.enabled;
	});

	if (changedSources.length > 0) {
		//console.log('🢄Source enabled states changed:', changedSources.map(s => ({id: s.id, enabled: s.enabled})));
	}
});

/**
 * Enables the source for a given photo uid if it's not already enabled
 * @param photoUid The photo uid in format "source-id"
 * @returns The source type that was enabled, or null if no action taken
 */
export function enableSourceForPhotoUid(photoUid: string): string | null {
	const sourceType = photoUid.split('-')[0];

	if (sourceType && (sourceType === 'hillview' || sourceType === 'mapillary')) {
		console.log('🢄Attempting to enable source for photo:', sourceType);

		let wasEnabled = false;
		sources.update(srcs => {
			const updated = srcs.map(src => {
				if (src.id === sourceType && !src.enabled) {
					console.log(`🢄Auto-enabled source ${sourceType} for photo ${photoUid}`);
					wasEnabled = true;
					return {...src, enabled: true};
				}
				return src;
			});
			return updated;
		});

		return wasEnabled ? sourceType : null;
	}

	console.warn('🢄Invalid or unsupported photo uid format:', photoUid);
	return null;
}

// Navigation functions using new mapState
export async function turn_to_photo_to(dir: string) {
	const currentPhotoToLeft = get(photoToLeft);
	const currentPhotoToRight = get(photoToRight);
	const currentPhotoUp = get(photoUp);
	const currentPhotoDown = get(photoDown);

	/*console.log('🢄turn_to_photo_to:', dir, {
		hasPhotoToLeft: !!currentPhotoToLeft,
		hasPhotoToRight: !!currentPhotoToRight,
		hasPhotoUp: !!currentPhotoUp,
		hasPhotoDown: !!currentPhotoDown
	});*/

	if (dir === 'left' && currentPhotoToLeft) {
		console.log('🢄Turning to left photo:', currentPhotoToLeft.uid, 'bearing:', currentPhotoToLeft.bearing);
		updateBearingWithPhoto(currentPhotoToLeft, 'photo_navigation');
	} else if (dir === 'right' && currentPhotoToRight) {
		console.log('🢄Turning to right photo:', currentPhotoToRight.uid, 'bearing:', currentPhotoToRight.bearing);
		updateBearingWithPhoto(currentPhotoToRight, 'photo_navigation');
	} else if (dir === 'up' && currentPhotoUp) {
		console.log('🢄Turning to up photo:', currentPhotoUp.uid, 'bearing:', currentPhotoUp.bearing, 'pitch:', currentPhotoUp.pitch);
		updateBearingWithPhoto(currentPhotoUp, 'photo_navigation');
	} else if (dir === 'down' && currentPhotoDown) {
		console.log('🢄Turning to down photo:', currentPhotoDown.uid, 'bearing:', currentPhotoDown.bearing, 'pitch:', currentPhotoDown.pitch);
		updateBearingWithPhoto(currentPhotoDown, 'photo_navigation');
	} else {
		console.debug(`🢄No photo to ${dir} available`);
		const p = get(photoInFront);
		if (p) {
			console.debug('🢄Photo in front exists, updating bearing to it');
			updateBearingWithPhoto(p, 'photo_navigation');
		}
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

export let mockCamera = localStorageSharedStore('mockCamera', false);
export let fakeCamera = localStorageSharedStore('fakeCamera', false);

export let maxPhotosInArea = localStorageReadOnceSharedStore('maxPhotosInArea', 100);

export let frontendBusy = writable(0);


export function onAppActivityChange(newActivity: string) {
	if (newActivity === 'capture') {
		// Entering capture mode - disable all photo sources
		sources.update(srcs => {
			return srcs.map(src => ({
				...src,
				enabled: src.id === 'device' // Only enable device source
			}));
		});
		// Note: Location and compass are now handled by reactive statement
	} else {
		// Exiting capture mode - re-enable previously enabled sources
		sources.update(srcs => {
			return srcs.map(src => ({
				...src,
				enabled: src.id === 'hillview'// || src.id === 'device'
			}));
		});
		// Note: Compass stopping is now handled by reactive statement
	}
}
