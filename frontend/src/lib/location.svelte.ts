import {writable, derived, get} from 'svelte/store';
import type { GeolocationPosition } from '$lib/preciseLocation';

// Store for current GPS location from device
export const gpsLocation = writable<GeolocationPosition | null>(null);

// Last known GPS position — only set when real GPS data arrives, never cleared.
export const lastKnownGpsLocation = writable<{ lat: number; lng: number } | null>(null);

// Store for whether location tracking is active
export const locationTracking = writable<boolean>(false);

// Background location tracking: entered when the user manually pans the map while
// ACTIVE tracking is on. GPS stays subscribed and pulsing, but the map no longer
// follows it (locationTracking is false, so the GPS handler early-returns). GPS
// rows keep flowing to the locations table tagged "background", and a captured
// photo's live GPS fix is recorded into its EXIF UserComment as an alternative
// location. Mutually exclusive with locationTracking: OFF = both false,
// ACTIVE = locationTracking true, BACKGROUND = backgroundLocationTracking true.
export const backgroundLocationTracking = writable<boolean>(false);

export function setBackgroundLocationTracking(on: boolean) {
    backgroundLocationTracking.set(on);
}

// Store for location error messages
export const locationError = writable<string | null>(null);


// Helper function to check if position has changed
export function hasPositionChanged(oldPosition: GeolocationPosition | null, newPosition: GeolocationPosition | null): boolean {
    if (!oldPosition && !newPosition) return false;
    if (!oldPosition || !newPosition) return true;

    return (
        oldPosition.coords.latitude !== newPosition.coords.latitude ||
        oldPosition.coords.longitude !== newPosition.coords.longitude ||
        oldPosition.coords.altitude !== newPosition.coords.altitude ||
        oldPosition.coords.accuracy !== newPosition.coords.accuracy ||
        oldPosition.coords.heading !== newPosition.coords.heading
    );
}

// Helper function to update location
export function updateGpsLocation(position: GeolocationPosition | null) {

	//console.debug('🢄updateGpsLocation: Received update:', JSON.stringify(position));

    const old = get(gpsLocation);
    if (!hasPositionChanged(old, position)) {
        // No change in coordinates, do not update
        return false;
    }

    //console.debug('🢄Updating GPS location store:', JSON.stringify(position));
    gpsLocation.set(position);

    if (position) {
        lastKnownGpsLocation.set({ lat: position.coords.latitude, lng: position.coords.longitude });
    }

    // Capture location updates are now handled by captureLocationManager.ts
    return true;
}

// Helper function to update tracking status
export function setLocationTracking(isTracking: boolean) {
    locationTracking.set(isTracking);

    // Note: Compass tracking is now handled separately
}

// Helper function to set location error
export function setLocationError(error: string | null) {
    locationError.set(error);
}

