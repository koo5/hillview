import { get } from 'svelte/store';
import {bearingMode, updateBearing, type BearingMode} from '$lib/mapState';
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
	updateBearing(photo.bearing, source, photo.uid);
}
