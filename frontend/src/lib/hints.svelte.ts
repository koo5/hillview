import {derived} from 'svelte/store';
import {gpsLocation} from "$lib/location.svelte";
import {bearingState} from "$lib/mapState";
import {compassWalkingActive} from "$lib/compass.svelte";


// Derived store to indicate if compass calibration is needed
// True when compass is active in walking mode but accuracy is LOW or UNRELIABLE
export const needsCalibration = derived(
	[compassWalkingActive, bearingState],
	([$compassWalkingActive, $bearingState]) => {
		if (!$compassWalkingActive) return false;
		// Accuracy: 0 = UNRELIABLE, 1 = LOW, 2 = MEDIUM, 3 = HIGH
		const accuracy = $bearingState.accuracy;
		return accuracy !== null && accuracy !== undefined && accuracy <= 1;
	}
);


export const shouldShowSwitchToCarModeHint = derived(
	[compassWalkingActive, gpsLocation],
	([$compassWalkingActive, $gpsLocation]) => {
		return $compassWalkingActive && $gpsLocation && ($gpsLocation.coords?.speed || 0) > 5; // m/s
	}
);

