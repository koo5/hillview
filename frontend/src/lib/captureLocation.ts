import {get, writable, derived} from 'svelte/store';
import { fusedBearing } from './sensorFusion.svelte';
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

export interface CaptureLocationWithFusedBearing extends CaptureLocation {
    headingSource?: 'gps' | 'compass' | 'fused';
    headingConfidence?: number;
}

// Store that holds the current capture location
// Gets updated from either GPS or map movements - whichever is most recent
export const captureLocation = writable<CaptureLocation | null>(null);


// Derived store that combines capture location with fused bearing
export const captureLocationWithFusedBearing = derived(
    [captureLocation, fusedBearing],
    ([$captureLocation, $fusedBearing]): CaptureLocationWithFusedBearing | null => {
        if (!$captureLocation) return null;
        
        // If we have a fused bearing and the capture location is from GPS,
        // use the fused bearing instead of GPS heading
        if ($fusedBearing && $captureLocation.source === 'gps') {
            return {
                ...$captureLocation,
                heading: $fusedBearing.bearing,
                headingSource: $fusedBearing.source,
                headingConfidence: $fusedBearing.confidence
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