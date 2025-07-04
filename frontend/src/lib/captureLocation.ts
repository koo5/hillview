import { writable } from 'svelte/store';

export interface CaptureLocation {
    latitude: number;
    longitude: number;
    altitude: number | null;
    accuracy: number;
    heading: number;
    source: 'gps' | 'map';
    timestamp: number;
}

// Store that holds the current capture location
// Gets updated from either GPS or map movements - whichever is most recent
export const captureLocation = writable<CaptureLocation | null>(null);

// Helper function to update capture location from GPS
export function updateCaptureLocationFromGps(coords: { 
    latitude: number;
    longitude: number;
    altitude: number | null;
    accuracy: number;
    heading?: number | null;
}, heading?: number | null) {
    captureLocation.set({
        latitude: coords.latitude,
        longitude: coords.longitude,
        altitude: coords.altitude,
        accuracy: coords.accuracy,
        heading: heading ?? coords.heading ?? 0,
        source: 'gps',
        timestamp: Date.now()
    });
}

// Helper function to update capture location from map
export function updateCaptureLocationFromMap(lat: number, lng: number, mapBearing: number) {
    captureLocation.set({
        latitude: lat,
        longitude: lng,
        altitude: null,
        accuracy: 10, // Default accuracy for map-based location
        heading: mapBearing,
        source: 'map',
        timestamp: Date.now()
    });
}