import { derived, get } from 'svelte/store';
import { gpsCoordinates } from './location.svelte';
import { fusedHeading, headingDifference, headingSmoother } from './compass.svelte';

export interface FusedBearing {
    bearing: number;           // 0-360 degrees
    source: 'gps' | 'compass' | 'fused';
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
        
        // No data available
        if (!$gpsCoords && !$compass) {
            return null;
        }

        // Only compass available
        if (!$gpsCoords && $compass) {
            return {
                bearing: $compass.heading,
                source: 'compass' as const,
                confidence: 0.7,
                accuracy: $compass.accuracy,
                timestamp: now
            };
        }

        // Only GPS available
        if ($gpsCoords && !$compass) {
            if ($gpsCoords.heading !== null && $gpsCoords.heading !== undefined) {
                return {
                    bearing: $gpsCoords.heading,
                    source: 'gps' as const,
                    confidence: ($gpsCoords.speed || 0) > SPEED_THRESHOLD ? 0.8 : 0.3,
                    accuracy: null,
                    timestamp: now
                };
            }
            return null;
        }

        // Both available - perform sensor fusion
        if ($gpsCoords && $compass) {
            const gpsHeading = $gpsCoords.heading;
            const compassHeading = $compass.heading;
            const speed = $gpsCoords.speed || 0;

            // Determine compass weight based on movement
            let compassWeight = speed < SPEED_THRESHOLD ? 
                COMPASS_WEIGHT_STATIONARY : 
                COMPASS_WEIGHT_MOVING;

            // Adjust weight based on GPS accuracy
            if ($gpsCoords.accuracy > 20) {
                compassWeight = Math.min(compassWeight + 0.2, 0.95);
            }

            // Check for large discrepancies
            if (gpsHeading !== null && gpsHeading !== undefined) {
                const diff = Math.abs(headingDifference(gpsHeading, compassHeading));
                if (diff > HEADING_CHANGE_THRESHOLD) {
                    // Large difference - trust compass more if stationary
                    if (speed < SPEED_THRESHOLD) {
                        compassWeight = 0.95;
                    } else {
                        // Moving - GPS is usually more reliable
                        compassWeight = 0.2;
                    }
                }
            }

            // Calculate fused bearing
            let fusedValue: number;
            let confidence: number;

            if (gpsHeading === null || gpsHeading === undefined) {
                // No GPS heading - use compass only
                fusedValue = compassHeading;
                confidence = 0.7;
            } else {
                // Weighted circular mean
                const gpsRad = (gpsHeading * Math.PI) / 180;
                const compassRad = (compassHeading * Math.PI) / 180;
                
                const x = (1 - compassWeight) * Math.cos(gpsRad) + compassWeight * Math.cos(compassRad);
                const y = (1 - compassWeight) * Math.sin(gpsRad) + compassWeight * Math.sin(compassRad);
                
                const fusedRad = Math.atan2(y, x);
                fusedValue = (fusedRad * 180) / Math.PI;
                if (fusedValue < 0) fusedValue += 360;

                // Calculate confidence based on agreement and speed
                const agreement = 1 - Math.abs(headingDifference(gpsHeading, compassHeading)) / 180;
                confidence = 0.5 + 0.3 * agreement + 0.2 * Math.min(speed / 5, 1);
            }

            // Apply smoothing
            const smoothedBearing = headingSmoother.addHeading(fusedValue);
            
            // Debug log every few updates
            if (Math.random() < 0.1) { // Log ~10% of updates
                console.debug('Sensor fusion update:', {
                    gpsHeading: gpsHeading?.toFixed(1),
                    compassHeading: compassHeading.toFixed(1),
                    fusedBearing: smoothedBearing.toFixed(1),
                    compassWeight: compassWeight.toFixed(2),
                    speed: speed.toFixed(1) + ' m/s',
                    confidence: (confidence * 100).toFixed(0) + '%'
                });
            }

            return {
                bearing: smoothedBearing,
                source: 'fused' as const,
                confidence: Math.min(confidence, 1),
                accuracy: $compass.accuracy,
                timestamp: now
            };
        }

        return null;
    }
);

// Utility to get instantaneous bearing without smoothing
export function getInstantBearing(): FusedBearing | null {
    const gps = get(gpsCoordinates);
    const compass = get(fusedHeading);

    if (!gps && !compass) return null;

    if (compass && (!gps || !gps.heading)) {
        return {
            bearing: compass.heading,
            source: 'compass',
            confidence: 0.7,
            accuracy: compass.accuracy,
            timestamp: Date.now()
        };
    }

    if (gps && gps.heading !== null && gps.heading !== undefined && !compass) {
        return {
            bearing: gps.heading,
            source: 'gps',
            confidence: (gps.speed || 0) > SPEED_THRESHOLD ? 0.8 : 0.3,
            accuracy: null,
            timestamp: Date.now()
        };
    }

    // Return current fused value
    return get(fusedBearing);
}

// Reset the heading smoother (useful when starting fresh)
export function resetBearingSmoothing() {
    headingSmoother.reset();
}