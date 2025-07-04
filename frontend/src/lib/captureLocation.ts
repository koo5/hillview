import {get, writable} from 'svelte/store';

export interface CaptureLocation {
    latitude: number;
    longitude: number;
    altitude?: number;
    accuracy?: number;
    heading?: number;
    source?: 'gps' | 'map';
    timestamp?: number;
}

// Store that holds the current capture location
// Gets updated from either GPS or map movements - whichever is most recent
export const captureLocation = writable<CaptureLocation | null>(null);

// Helper function to update capture location from GPS
export function updateCaptureLocationFromGps(coords: { 
    latitude: number;
    longitude: number;
    altitude?: number;
    accuracy?: number;
    heading?: number;
}) {
    const old = get(captureLocation);
    const v = { ...(old || {}), ...coords, source: 'gps'}
    if (v.latitude !== old?.latitude ||
        v.longitude !== old?.longitude ||
        v.altitude !== old?.altitude ||
        v.accuracy !== old?.accuracy ||
        v.heading !== old?.heading ||
        v.source !== old?.source)
    {
        captureLocation.set({...v, timestamp: Date.now()});
    }
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