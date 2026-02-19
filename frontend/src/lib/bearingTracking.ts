import { get } from 'svelte/store';
import { bearingMode } from '$lib/mapState';
import { enableCompass, disableCompass } from '$lib/compass.svelte';
import { enableGpsOrientation, disableGpsOrientation } from '$lib/gpsOrientation.svelte';

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
