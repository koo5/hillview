/**
 * A person turning the view by hand: the map's arrow drag, the 3D world's drag. One rule for both
 * (docs/tauri-map-ui-contract.md, Bearing writers: the last writer wins because the automatic
 * producers are switched off first). Without it the compass's next sample puts the bearing back,
 * and in car mode gps-kalman does: there the turn moves the mount offset instead, so the GPS
 * heading and the hand agree from then on.
 */
import { get } from 'svelte/store';
import { bearingMode, updateBearing } from '$lib/mapState';
import { compassEnabled, disableCompass } from '$lib/compass.svelte';
import { adjustMountOffset, gpsOrientationEnabled } from '$lib/gpsOrientation.svelte';
import { getAngularDistance } from '$lib/utils/bearingUtils';

/** stop the automatic producers that would overwrite a hand-set bearing (idempotent) */
export function stopBearingProducers() {
	if (get(compassEnabled)) {
		console.log('🢄🧭 Disabling compass tracking: the bearing is being set by hand');
		disableCompass();
	}
}

/** the hand turned the view from `from` to `to` (degrees); `source` names the control */
export function userTurn(from: number, to: number, source: string) {
	stopBearingProducers();
	if (get(bearingMode) === 'car' && get(gpsOrientationEnabled)) {
		// Translate the turn into a mount-offset change so Kotlin (Tauri) /
		// the subsequent gps-kalman diffs (browser) stay consistent.
		adjustMountOffset(getAngularDistance(from, to));
	} else {
		updateBearing(to, source);
	}
}
