import { get } from 'svelte/store';
import { gpsCoordinates } from './location.svelte';
import { fusedBearing } from './sensorFusion.svelte';
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
        
        // ALWAYS use the fused bearing, never GPS bearing
        const fused = get(fusedBearing);
        
        captureLocation.set({
            latitude: coords.latitude,
            longitude: coords.longitude,
            altitude: coords.altitude,
            accuracy: coords.accuracy,
            heading: fused ? fused.bearing : undefined, // Only use fused bearing
            source: 'gps',
            timestamp: Date.now()
        });
        
        console.log('Capture location updated from GPS:', 
            `pos=${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}`,
            `heading=${fused ? fused.bearing.toFixed(1) + '°' : 'none'}`,
            'source=fused'
        );
    }
});

// Subscribe to fused bearing changes
fusedBearing.subscribe(fused => {
    if (!fused) {
        console.log('No fused bearing data');
        return;
    }
    
    const currentCapture = get(captureLocation);
    
    // Only update heading if we have a capture location (from either GPS or map)
    if (currentCapture) {
        // Always update with the latest fused bearing
        captureLocation.set({
            ...currentCapture,
            heading: fused.bearing,
            timestamp: Date.now()
        });
        
        console.log('✅ Capture heading updated:', 
            `bearing=${fused.bearing.toFixed(1)}°`,
            `source=${currentCapture.source}`,
            `fusedSource=${fused.source}`,
            `confidence=${(fused.confidence * 100).toFixed(0)}%`
        );
    } else {
        console.log('❌ No capture location available');
    }
});

// Export a function to force refresh from current sensors
export function refreshCaptureLocation() {
    const coords = get(gpsCoordinates);
    const fused = get(fusedBearing);
    const currentCapture = get(captureLocation);
    
    if (coords && (!currentCapture || currentCapture.source === 'gps')) {
        captureLocation.set({
            latitude: coords.latitude,
            longitude: coords.longitude,
            altitude: coords.altitude,
            accuracy: coords.accuracy,
            heading: fused ? fused.bearing : undefined, // Only use fused bearing
            source: 'gps',
            timestamp: Date.now()
        });
    }
}