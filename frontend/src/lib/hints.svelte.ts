import {derived} from 'svelte/store';
import {gpsLocation} from "$lib/location.svelte";
import {bearingState} from "$lib/mapState";
import {compassWalkingActive} from "$lib/compass.svelte";


// Derived store to indicate if compass calibration is needed
// True when compass is active in walking mode but accuracy is LOW or UNRELIABLE
export const needsCalibration = derived(
	[compassWalkingActive, bearingState],
	([$compassWalkingActive, $bearingState]) => {
		console.log(`needsCalibration: $compassWalkingActive: ${$compassWalkingActive}, $bearingState: ${JSON.stringify($bearingState)}`);
		if (!$compassWalkingActive) return false;
		// Accuracy: 0 = UNRELIABLE, 1 = LOW, 2 = MEDIUM, 3 = HIGH
		const accuracy = $bearingState.accuracy;
		return accuracy !== null && accuracy !== undefined && accuracy != 3;
	}
);


export const shouldShowSwitchToCarModeHint = derived(
	[compassWalkingActive, gpsLocation],
	([$compassWalkingActive, $gpsLocation]) => {
		console.log(`shouldShowSwitchToCarModeHint: $compassWalkingActive: ${$compassWalkingActive}, $gpsLocation: ${$gpsLocation}`);
		return $compassWalkingActive && $gpsLocation && ($gpsLocation.coords?.speed || 0) > 5; // m/s
	}
);

