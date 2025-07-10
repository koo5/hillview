import { get } from 'svelte/store';
import { gpsCoordinates } from './location.svelte';
import { compassHeading } from './compass.svelte';
import { captureLocation } from './captureLocation';

// This module manages the capture location by subscribing to both GPS and compass changes

let lastGpsCoords: { lat: number; lng: number; alt?: number; acc?: number } | null = null;

// Subscribe to GPS coordinates
gpsCoordinates.subscribe(coords => {
    if (!coords) return;
    
    const currentCapture = get(captureLocation);
    
    // Only update if source is GPS or not set
    if (!currentCapture || currentCapture.source === 'gps') {
        lastGpsCoords = {
            lat: coords.latitude,
            lng: coords.longitude,
            alt: coords.altitude,
            acc: coords.accuracy
        };
        
        // Use compass heading for bearing, never GPS bearing
        const compass = get(compassHeading);
        
        captureLocation.set({
            latitude: coords.latitude,
            longitude: coords.longitude,
            altitude: coords.altitude,
            accuracy: coords.accuracy,
            heading: compass ? compass.heading : undefined, // Only use compass bearing
            source: 'gps',
            timestamp: Date.now()
        });
        
        console.log('Capture location updated from GPS:', 
            `pos=${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}`,
            `heading=${compass ? compass.heading.toFixed(1) + '°' : 'none'}`,
            'source=compass'
        );
    }
});

// Subscribe to compass heading changes
compassHeading.subscribe(compass => {
    if (!compass) {
        console.log('No compass heading data');
        return;
    }
    
    const currentCapture = get(captureLocation);
    
    // Only update heading if we have a capture location (from either GPS or map)
    if (currentCapture) {
        // Always update with the latest compass heading
        captureLocation.set({
            ...currentCapture,
            heading: compass.heading,
            timestamp: Date.now()
        });
        
        console.log('✅ Capture heading updated:', 
            `bearing=${compass.heading.toFixed(1)}°`,
            `source=${currentCapture.source}`,
            `compassSource=${compass.source}`,
            `accuracy=${compass.accuracy?.toFixed(0) || 'N/A'}°`
        );
    } else {
        console.log('❌ No capture location available');
    }
});

// Export a function to force refresh from current sensors
export function refreshCaptureLocation() {
    const coords = get(gpsCoordinates);
    const compass = get(compassHeading);
    const currentCapture = get(captureLocation);
    
    if (coords && (!currentCapture || currentCapture.source === 'gps')) {
        captureLocation.set({
            latitude: coords.latitude,
            longitude: coords.longitude,
            altitude: coords.altitude,
            accuracy: coords.accuracy,
            heading: compass ? compass.heading : undefined, // Only use compass bearing
            source: 'gps',
            timestamp: Date.now()
        });
    }
}