import { writable, get } from 'svelte/store';
import { gpsLocation } from './location.svelte';
import { updateBearingByDiff } from './mapState';
import { isOnMapRoute } from './compass.svelte';
import { locationManager } from './locationManager';

// User preference - simple enabled/disabled
export const gpsOrientationEnabled = writable(false);

// Internal state for tracking GPS orientation functionality
export type GpsOrientationInternalState =
  | 'inactive'        // Not running
  | 'starting'        // Waiting for first GPS data
  | 'active'          // Successfully tracking GPS heading changes
  | 'error';          // Failed (no GPS heading available)

export const gpsOrientationInternalState = writable<GpsOrientationInternalState>('inactive');
export const gpsOrientationError = writable<string | null>(null);

// Track last GPS heading for differential updates
// When GPS heading changes, apply the difference to map bearing (not absolute positioning)
let lastGpsHeading: number | null = null;

// Flag to prevent recursion when reverting user preference
let revertingUserPreference = false;

// Simple user-level API functions
export function enableGpsOrientation() {
    console.log('🚗 User enabled GPS orientation tracking');
    gpsOrientationEnabled.set(true);
}

export function disableGpsOrientation() {
    console.log('🚗 User disabled GPS orientation tracking');
    gpsOrientationEnabled.set(false);
}

// Stop GPS orientation tracking internally
async function stopGpsOrientationInternal() {
    console.log('🚗 Stopping GPS orientation tracking internal state');
    gpsOrientationInternalState.set('inactive');
    lastGpsHeading = null;
    gpsOrientationError.set(null);
    await locationManager.releaseLocation('gps-orientation');
}

// State machine that manages GPS orientation tracking based on user preferences + route state
async function updateGpsOrientationState() {
    // Don't process updates if we're reverting user preference to avoid recursion
    if (revertingUserPreference) {
        return;
    }

    const userEnabled = get(gpsOrientationEnabled);
    const onMapRoute = get(isOnMapRoute);
    const currentInternalState = get(gpsOrientationInternalState);

    console.log('🚗🎛️ GPS orientation state update:', JSON.stringify(
		{ userEnabled, onMapRoute, currentInternalState }));

    if (!userEnabled || !onMapRoute) {
        // User disabled or not on map route - stop internal tracking
        if (currentInternalState !== 'inactive') {
            await stopGpsOrientationInternal();
        }
    } else {
        // User enabled and on map route - should start internal tracking
        if (currentInternalState === 'inactive') {
            gpsOrientationInternalState.set('starting');
            gpsOrientationError.set(null);
            lastGpsHeading = null;
            console.log('🚗 GPS orientation tracking starting, waiting for GPS data');

            // Request location service
            try {
                await locationManager.requestLocation('gps-orientation');
                console.log('🚗 GPS orientation requested location service successfully');
            } catch (error) {
                console.error('🚗 GPS orientation failed to request location service:', error);
                gpsOrientationInternalState.set('error');
                gpsOrientationError.set('Failed to start location service');
            }
        }
    }
}

// Subscribe to state changes
gpsOrientationEnabled.subscribe(updateGpsOrientationState);
isOnMapRoute.subscribe(updateGpsOrientationState);

// Subscribe to GPS location updates for orientation tracking
gpsLocation.subscribe((position) => {
    const internalState = get(gpsOrientationInternalState);

	console.log('🚗 GPS orientation received location update:', JSON.stringify(position));

    // Only process GPS heading if internal tracking is active or starting
    if (internalState !== 'active' && internalState !== 'starting') {
        return;
    }

    if (!position || position.coords.heading === null || position.coords.heading === undefined || isNaN(position.coords.heading)) {
        // No valid GPS heading available
        if (internalState === 'starting' || internalState === 'active') {
            console.log('🚗 No GPS heading available in this sample');
            /*gpsOrientationInternalState.set('error');
            gpsOrientationError.set('GPS heading not available');
            lastGpsHeading = null;*/
        }
        return;
    }

    const currentGpsHeading = (position.coords.heading + 360) % 360;

    // Transition from starting to active on first valid GPS data
    if (internalState === 'starting') {
        gpsOrientationInternalState.set('active');
        gpsOrientationError.set(null);
        lastGpsHeading = currentGpsHeading;
        console.log('🚗 GPS orientation: first heading locked at', currentGpsHeading.toFixed(1), '°');
        return;
    }

    // Apply differential updates when active
    if (internalState === 'active' && lastGpsHeading !== null) {
        // Calculate the shortest angular difference between old and new GPS heading
        let headingDiff = currentGpsHeading - lastGpsHeading;

        // Apply the difference to the current map bearing
        if (Math.abs(headingDiff) > 1) { // Ignore tiny changes to reduce noise
            updateBearingByDiff(headingDiff);
            console.log(`🚗 GPS orientation: heading changed by ${headingDiff.toFixed(1)}°, applied to map bearing`);
        }

        lastGpsHeading = currentGpsHeading;
    }
});

// Reset tracking when internal state changes to inactive
gpsOrientationInternalState.subscribe(state => {
    if (state === 'inactive') {
        lastGpsHeading = null;
    }
});
