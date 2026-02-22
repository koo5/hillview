import {derived} from 'svelte/store';
import {gpsLocation, locationTracking} from "$lib/location.svelte";
import {bearingMode, bearingState} from "$lib/mapState";
import {compassEnabled, compassWalkingActive} from "$lib/compass.svelte";
import {gpsOrientationEnabled} from "$lib/gpsOrientation.svelte";
import {localStorageSharedStore} from "$lib/svelte-shared-store";


// Derived store to indicate if compass calibration is needed
// True when compass is active in walking mode but accuracy is LOW or UNRELIABLE
export const needsCalibration = derived(
	[compassWalkingActive, bearingState],
	([$compassWalkingActive, $bearingState]) => {
		//console.log(`needsCalibration: $compassWalkingActive: ${$compassWalkingActive}, $bearingState: ${JSON.stringify($bearingState)}`);
		if (!$compassWalkingActive) return false;
		// Accuracy: 0 = UNRELIABLE, 1 = LOW, 2 = MEDIUM, 3 = HIGH
		const accuracy = $bearingState.accuracy_level;
		return accuracy !== null && accuracy !== undefined && accuracy != 3;
	}
);


// "Do not show again" preferences for tracking hints
export const hideBearingTrackingHint = localStorageSharedStore<boolean>('hideBearingTrackingHint', false);
export const hideLocationTrackingHint = localStorageSharedStore<boolean>('hideLocationTrackingHint', false);

// Show bearing tracking hint when:
// - Bearing tracking is disabled (neither compass nor GPS orientation enabled)
// - User hasn't dismissed the hint
export const shouldShowBearingTrackingHint = derived(
	[compassEnabled, gpsOrientationEnabled, hideBearingTrackingHint],
	([$compassEnabled, $gpsOrientationEnabled, $hideBearingTrackingHint]) => {
		if ($hideBearingTrackingHint) return false;
		const isBearingTrackingEnabled = $compassEnabled || $gpsOrientationEnabled;
		return !isBearingTrackingEnabled;
	}
);

// Show location tracking hint when:
// - Location tracking is disabled
// - User hasn't dismissed the hint
export const shouldShowLocationTrackingHint = derived(
	[locationTracking, hideLocationTrackingHint],
	([$locationTracking, $hideLocationTrackingHint]) => {
		if ($hideLocationTrackingHint) return false;
		return !$locationTracking;
	}
);

// Show "In a vehicle?" hint when:
// - Compass is active in walking mode and GPS shows speed > 5 m/s
// - Neither of the tracking hints are showing
export const shouldShowSwitchToCarModeHint = derived(
	[compassWalkingActive, gpsLocation, shouldShowBearingTrackingHint, shouldShowLocationTrackingHint],
	([$compassWalkingActive, $gpsLocation, $shouldShowBearingTrackingHint, $shouldShowLocationTrackingHint]) => {
		// Don't show if tracking hints are visible
		if ($shouldShowBearingTrackingHint || $shouldShowLocationTrackingHint) return false;
		return $compassWalkingActive && $gpsLocation && ($gpsLocation.coords?.speed || 0) > 5; // m/s
	}
);

