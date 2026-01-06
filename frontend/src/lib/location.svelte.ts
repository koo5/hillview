import {writable, derived, get} from 'svelte/store';
import type { GeolocationPosition } from '$lib/preciseLocation';
import {updateSpatialState} from "$lib/mapState";

// Store for current GPS location from device
export const gpsLocation = writable<GeolocationPosition | null>(null);

// Store for whether location tracking is active
export const locationTracking = writable<boolean>(false);

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

	console.debug('🢄updateGpsLocation: Received update:', JSON.stringify(position));

    const old = get(gpsLocation);
    if (!hasPositionChanged(old, position)) {
        // No change in coordinates, do not update
        return false;
    }

    console.debug('🢄Updating GPS location store:', JSON.stringify(position));
    gpsLocation.set(position);

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

