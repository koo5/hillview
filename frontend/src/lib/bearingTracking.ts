import { get } from 'svelte/store';
import {bearingMode, updateBearing} from '$lib/mapState';
import { enableCompass, disableCompass } from '$lib/compass.svelte';
import { enableGpsOrientation, disableGpsOrientation } from '$lib/gpsOrientation.svelte';
import type {PhotoData, PhotoId} from './types/photoTypes';

// Bearing-mode-aware tracking helpers
export function enableBearingTracking() {
    if (get(bearingMode) === 'walking') {
        console.log('🧭 Enabling compass tracking (walking mode)');
        enableCompass();
    } else {
        console.log('🚗 Enabling GPS orientation tracking (car mode)');
        enableGpsOrientation();
    }
}

export function disableBearingTracking() {
    console.log('🛑 Disabling all bearing tracking');
    disableCompass();
    disableGpsOrientation();
}

export function updateBearingWithPhoto(photo: PhotoData, source: string = 'photo_navigation') {
	disableBearingTracking();
	updateBearing(photo.bearing, source, photo.uid);
}
