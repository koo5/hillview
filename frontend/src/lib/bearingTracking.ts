import { get } from 'svelte/store';
import {bearingMode, bearingState, updateBearing, type BearingMode} from '$lib/mapState';
import { enableCompass, disableCompass } from '$lib/compass.svelte';
import { enableGpsOrientation, disableGpsOrientation } from '$lib/gpsOrientation.svelte';
import type {PhotoData, PhotoId} from './types/photoTypes';

const doLog = false;

// Bearing-mode-aware tracking helpers
export function enableBearingTracking() {
    if (get(bearingMode) === 'walking') {
        if (doLog) console.log('🧭 Enabling compass tracking (walking mode)');
        enableCompass();
    } else {
        if (doLog) console.log('🚗 Enabling GPS orientation tracking (car mode)');
        enableGpsOrientation();
    }
}

export function disableBearingTracking() {
    if (doLog) console.log('🛑 Disabling all bearing tracking');
    disableCompass();
    disableGpsOrientation();
}

export function selectBearingMode(mode: BearingMode) {
    bearingMode.set(mode);
    disableBearingTracking();
    enableBearingTracking();
}

export function updateBearingWithPhoto(photo: PhotoData, source: string = 'photo_navigation') {
	disableBearingTracking();
	// A photo with no recorded heading cannot be "turned to": keep the view
	// where it is and record only the choice (the photoUid). The choice drops
	// as soon as anything else writes the bearing, which clears photoUid —
	// same lifetime as any deliberate selection.
	const bearing = photo.has_bearing === false ? get(bearingState).bearing : photo.bearing;
	updateBearing(bearing, source, photo.uid);
}
