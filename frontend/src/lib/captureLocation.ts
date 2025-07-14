import {get, writable, derived} from 'svelte/store';
import { currentHeading } from './compass.svelte';
import { gpsCoordinates } from './location.svelte';

export interface CaptureLocation {
    latitude: number;
    longitude: number;
    altitude?: number;
    accuracy?: number;
    heading?: number;
    source?: 'gps' | 'map';
    timestamp?: number;
}

export interface CaptureLocationWithCompassBearing extends CaptureLocation {
    headingSource?: 'compass';
    headingAccuracy?: number;
}

// Store that holds the current capture location
// Gets updated from either GPS or map movements - whichever is most recent
export const captureLocation = writable<CaptureLocation | null>(null);


// Derived store that combines capture location with compass bearing
export const captureLocationWithCompassBearing = derived(
    [captureLocation, currentHeading],
    ([$captureLocation, $currentHeading]): CaptureLocationWithCompassBearing | null => {
        if (!$captureLocation) return null;
        
        // If we have a compass heading and the capture location is from GPS,
        // use the compass heading instead of GPS heading
        if ($currentHeading && $currentHeading.heading !== null && $captureLocation.source === 'gps') {
            return {
                ...$captureLocation,
                heading: $currentHeading.heading,
                headingSource: 'compass',
                headingAccuracy: $currentHeading.accuracy ?? undefined
            };
        }
        
        // Otherwise use the original capture location
        return $captureLocation;
    }
);

// Helper function to update capture location from GPS
export function updateCaptureLocationFromGps(coords: { 
    latitude: number;
    longitude: number;
    altitude?: number;
    accuracy?: number;
    heading?: number;
}) {
    const old = get(captureLocation);
    const v = { ...(old || {}), ...coords, source: 'gps' as const}
    
    // Always update to ensure we have the latest position
    console.debug('Updating capture location from GPS:', {
        oldHeading: old?.heading,
        newHeading: v.heading,
        source: v.source
    });
    captureLocation.set({...v, timestamp: Date.now()});
}

// Helper function to update capture location from map
export function updateCaptureLocationFromMap(lat: number, lng: number, mapBearing: number) {
    captureLocation.set({
        latitude: lat,
        longitude: lng,
        altitude: undefined, // No altitude from map
        accuracy: 1,
        heading: mapBearing,
        source: 'map',
        timestamp: Date.now()
    });
}