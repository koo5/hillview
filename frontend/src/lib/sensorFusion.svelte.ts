import { derived, get } from 'svelte/store';
import { gpsCoordinates } from './location.svelte';
import { fusedHeading, headingDifference, headingSmoother } from './compass.svelte';

export interface FusedBearing {
    bearing: number;           // 0-360 degrees
    source: 'compass';         // Always compass now
    confidence: number;        // 0-1 confidence level
    accuracy: number | null;   // Accuracy in degrees
    timestamp: number;
}

// Complementary filter parameters
const COMPASS_WEIGHT_STATIONARY = 0.9;  // High compass weight when not moving
const COMPASS_WEIGHT_MOVING = 0.3;      // Lower compass weight when moving
const SPEED_THRESHOLD = 0.5;            // m/s - below this we're "stationary"
const HEADING_CHANGE_THRESHOLD = 45;    // degrees - large changes indicate unreliable data

// Store for the final fused bearing
export const fusedBearing = derived(
    [gpsCoordinates, fusedHeading],
    ([$gpsCoords, $compass]) => {
        const now = Date.now();
        
        // No compass data available - return null (never use GPS bearing)
        if (!$compass) {
            return null;
        }

        // Use compass data exclusively
        return {
            bearing: $compass.heading,
            source: 'compass' as const,
            confidence: 0.7,
            accuracy: $compass.accuracy,
            timestamp: now
        };
    }
);

// Utility to get instantaneous bearing without smoothing
export function getInstantBearing(): FusedBearing | null {
    const compass = get(fusedHeading);

    if (!compass) return null;

    // Always use compass data exclusively
    return {
        bearing: compass.heading,
        source: 'compass',
        confidence: 0.7,
        accuracy: compass.accuracy,
        timestamp: Date.now()
    };
}

// Reset the heading smoother (useful when starting fresh)
export function resetBearingSmoothing() {
    headingSmoother.reset();
}