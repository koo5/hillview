import {writable, derived, get} from 'svelte/store';
import type { GeolocationPosition } from '$lib/geolocation';
import { updateCaptureLocationFromGps } from './captureLocation';

// Store for current GPS location from device
export const gpsLocation = writable<GeolocationPosition | null>(null);

// Store for whether location tracking is active
export const locationTracking = writable<boolean>(false);

// Store for location error messages
export const locationError = writable<string | null>(null);

// Derived store for easy access to coordinates
export const gpsCoordinates = derived(
    gpsLocation,
    $gpsLocation => {
        if (!$gpsLocation) return null;
        
        const { latitude, longitude, altitude, accuracy, heading, speed } = $gpsLocation.coords;
        
        return {
            latitude,
            longitude,
            altitude,
            accuracy,
            heading,
            speed,
            timestamp: $gpsLocation.timestamp
        };
    }
);

// Derived store for formatted location string
export const gpsLocationString = derived(
    gpsCoordinates,
    $coords => {
        if (!$coords) return 'No GPS data';
        
        return `${$coords.latitude.toFixed(6)}, ${$coords.longitude.toFixed(6)}`;
    }
);

// Helper function to update location
export function updateGpsLocation(position: GeolocationPosition | null) {
    const old = get(gpsLocation);
    if (old?.coords.latitude === position?.coords.latitude &&
        old?.coords.longitude === position?.coords.longitude &&
        old?.coords.altitude === position?.coords.altitude &&
        old?.coords.accuracy === position?.coords.accuracy &&
        old?.coords.heading === position?.coords.heading) {
        // No change in coordinates, do not update
        return;
    }

    console.debug('Updating GPS location store:', position);
    gpsLocation.set(position);
    
    // Also update capture location when GPS updates
    if (position) {
        updateCaptureLocationFromGps({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            altitude: position.coords.altitude,
            accuracy: position.coords.accuracy,
            heading: position.coords.heading
        });
    }
}

// Helper function to update tracking status
export function setLocationTracking(isTracking: boolean) {
    locationTracking.set(isTracking);
}

// Helper function to set location error
export function setLocationError(error: string | null) {
    locationError.set(error);
}