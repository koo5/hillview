import { get } from 'svelte/store';
import { locationTracking } from './location.svelte';
import { compassHeading } from './compass.svelte';
import { bearing as mapBearing } from './data.svelte';

// This module syncs the map arrow bearing with sensor data when GPS tracking is active

let isTracking = false;
let lastBearing: number | null = null;
const SMOOTHING_FACTOR = 0.9; // 0 = no smoothing, 1 = no change

// Subscribe to location tracking status
locationTracking.subscribe(tracking => {
    isTracking = tracking;
    console.log('Location tracking:', tracking ? 'active' : 'inactive');
});

// Helper function to calculate shortest angular distance
function angleDifference(a: number, b: number): number {
    const diff = ((a - b + 180) % 360) - 180;
    return diff < -180 ? diff + 360 : diff;
}

// Helper function to interpolate between angles
function lerpAngle(current: number, target: number, factor: number): number {
    const diff = angleDifference(target, current);
    const result = current + diff * (1 - factor);
    return (result + 360) % 360;
}

// Subscribe to compass heading changes
compassHeading.subscribe(compass => {
    if (!compass || !isTracking) return;
    
    // Negate the compass bearing for map view
    // When device rotates clockwise, map should rotate counter-clockwise
    const targetBearing = (360 - compass.heading) % 360;
    
    // Apply smoothing
    let smoothedBearing: number;
    if (lastBearing === null) {
        // First update, no smoothing
        smoothedBearing = targetBearing;
    } else {
        // Smooth the bearing change
        smoothedBearing = lerpAngle(lastBearing, targetBearing, SMOOTHING_FACTOR);
    }
    
    lastBearing = smoothedBearing;
    
    // Update map bearing
    mapBearing.set(smoothedBearing);
    
    // Log only significant changes
    if (Math.random() < 0.1) { // Log ~10% of updates
        console.log('Map bearing synced:',
            `compass=${compass.heading.toFixed(1)}°`,
            `target=${targetBearing.toFixed(1)}°`, 
            `smoothed=${smoothedBearing.toFixed(1)}°`
        );
    }
});

// Export function to manually sync bearings
export function syncMapBearing() {
    const compass = get(compassHeading);
    if (compass && isTracking) {
        const targetBearing = (360 - compass.heading) % 360;
        lastBearing = targetBearing;
        mapBearing.set(targetBearing);
    }
}

// Reset smoothing when tracking stops
locationTracking.subscribe(tracking => {
    if (!tracking) {
        lastBearing = null;
    }
});