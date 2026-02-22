import { writable, derived, get } from 'svelte/store';
import { TAURI, TAURI_MOBILE, tauriSensor, isSensorAvailable, type SensorData, SensorMode } from './tauri';
import {PluginListener} from "@tauri-apps/api/core";
import {bearingMode, bearingState, updateBearing} from "$lib/mapState";
import {getSettings, settings, settingsDefaults} from "$lib/settings";

export interface CompassData {
    magnetic_heading: number | null;  // 0-360 degrees from magnetic north
    true_heading: number | null;       // 0-360 degrees from true north
    accuracy_level: number | null;
    timestamp: number;
    source: string;
    debug?: {
        // Raw event inputs
        alpha: number | null;
        beta: number | null;
        gamma: number | null;
        absolute: boolean;
        screenAngle: number;
        // Browser-specific inputs
        webkitCompassHeading: number | null;
        webkitCompassAccuracy: number | null;
        compassHeading: number | null;
        // Which code path ran
        headingMethod: 'webkitCompassHeading' | 'tiltCompensated' | 'none';
        // Intermediate values
        rawHeading: number | null;        // before normalizeHeading
        normalizedHeading: number | null; // after normalizeHeading
        screenOrientation: number | null; // window.screen.orientation.angle
        // Face-down workaround (like EnhancedSensorService.kt)
        faceDown: boolean;                    // abs(beta) > 90
        landscapeWorkaroundApplied: boolean;  // negation applied
    };
}

export interface DeviceOrientation {
    alpha: number | null;    // Z-axis rotation (0-360)
    beta: number | null;     // X-axis rotation (-180 to 180)
    gamma: number | null;    // Y-axis rotation (-90 to 90)
    absolute: boolean;
}

// compassData - feeds into currentCompassHeading
export const compassData = writable<CompassData>({
    magnetic_heading: null,
    true_heading: null,
    accuracy_level: null,
    timestamp: Date.now(),
    source: 'unknown'
});

// deviceOrientation - just for debugging
export const deviceOrientation = writable<DeviceOrientation>({
    alpha: null,
    beta: null,
    gamma: null,
    absolute: false
});

// Derived store for current heading with source information, feeds into bearingState
export const currentCompassHeading = derived(
    [compassData],
    ([$compassData]) => {
        //console.log('🢄🧭 currentCompassHeading derived - compassData:', $compassData);
        if ($compassData && $compassData.true_heading !== null) {
            return {
                heading: $compassData.true_heading,
                source: ($compassData.source + '-compass-true') as string,
                accuracy_level: $compassData.accuracy_level
            };
        }
        if ($compassData && $compassData.magnetic_heading !== null) {
            return {
                heading: $compassData.magnetic_heading,
                source: ($compassData.source + '-compass-magnetic') as string,
                accuracy_level: $compassData.accuracy_level
            };
        }
        return {
            heading: null,
            source: 'none' as const,
            accuracy_level: null
        };
    }
);

// Compass state machine - single source of truth
export type CompassState =
  | 'inactive'        // User hasn't enabled compass or not on map
  | 'starting'        // User enabled, trying to start (permissions, sensor init)
  | 'active'          // Compass working successfully
  | 'error';          // Failed to start (permissions denied, no sensor, etc.)

export const compassState = writable<CompassState>('inactive');
export const compassError = writable<string | null>(null);

// Store to track last sensor update time
export const lastSensorUpdate = writable<number | null>(null);

// Store to track current sensor mode
export const currentSensorMode = writable<SensorMode>(SensorMode.UPRIGHT_ROTATION_VECTOR);

// Store to track sensor accuracy status
export const sensorAccuracy = writable<{
    magnetometer: string | null;
    accelerometer: string | null;
    gyroscope: string | null;
    timestamp: number;
}>({
    magnetometer: null,
    accelerometer: null,
    gyroscope: null,
    timestamp: 0
});

// Store to track compass lag (time since last update)
export const compassLag = writable<number | null>(null);

// Route state - whether we're on map route where compass should work
export const isOnMapRoute = writable<boolean>(false);

// Permission state
let permissionGranted = false;

// Track active listeners
let orientationHandler: ((event: DeviceOrientationEvent) => void) | null = null;
let absoluteOrientationListener: ((event: DeviceOrientationEvent) => void) | null = null;
let regularOrientationListener: ((event: DeviceOrientationEvent) => void) | null = null;
let tauriSensorListener: PluginListener | null = null;

// Accuracy polling
let accuracyPollingInterval: number | null = null;

// Lag monitoring
let lagMonitoringInterval: number | null = null;

let absoluteReadingsCount = 0; // Count of absolute events received to determine if we should drop regular listener
// Throttling for compass updates using requestAnimationFrame
let pendingCompassUpdate: CompassData | null = null;
let compassUpdateScheduled = false;

function scheduleCompassUpdate(data: CompassData) {
    pendingCompassUpdate = data;

    if (!compassUpdateScheduled) {
        compassUpdateScheduled = true;
        requestAnimationFrame(() => {
            if (pendingCompassUpdate) {
                compassData.set(pendingCompassUpdate);
                pendingCompassUpdate = null;
            }
            compassUpdateScheduled = false;
        });
    }
}

// Helper to normalize heading to 0-360 range
function normalizeHeading(heading: number): number {
    return ((heading % 360) + 360) % 360;
}

/**
 * Compute a tilt-compensated compass heading from DeviceOrientation Euler angles.
 *
 * The raw `alpha` value is only a reliable compass bearing when the device is flat.
 * This function builds the ZXY rotation matrix from (alpha, beta, gamma), projects
 * the Earth-frame north vector onto the device screen plane, and returns a heading
 * in [0, 360) degrees that stays correct regardless of device tilt.
 *
 * This is the web equivalent of the Kotlin code that calls
 * SensorManager.remapCoordinateSystem + SensorManager.getOrientation.
 */
function computeTiltCompensatedHeading(
    alpha: number,
    beta: number,
    gamma: number,
    landscapeWorkaround: boolean
): { heading: number; faceDown: boolean; landscapeWorkaroundApplied: boolean } {
    const degToRad = Math.PI / 180;
    const _x = beta * degToRad;   // beta  -> rotation around X
    const _y = gamma * degToRad;  // gamma -> rotation around Y
    const _z = alpha * degToRad;  // alpha -> rotation around Z

    const cX = Math.cos(_x);
    const cY = Math.cos(_y);
    const cZ = Math.cos(_z);
    const sX = Math.sin(_x);
    const sY = Math.sin(_y);
    const sZ = Math.sin(_z);

    // Project the north vector onto the device screen plane.
    // Vx, Vy are components of the Earth-frame north direction expressed
    // in the device X/Y axes (derived from the ZXY rotation matrix).
    const Vx = -cZ * sY - sZ * sX * cY;
    const Vy = -sZ * sY + cZ * sX * cY;

    let compassHeading = Math.atan2(Vx, Vy) * (180 / Math.PI); // degrees, (-180, 180]

    // Match EnhancedSensorService.kt: detect face-down orientation
    // In web API, beta (pitch) > 90 means device screen faces away from user
    const faceDown = Math.abs(beta) > 90;
    let landscapeWorkaroundApplied = false;
	const screenAngle = window.screen?.orientation?.angle ?? 0;

    // Apply landscape_armor22_workaround: negate heading when face-down
    if (landscapeWorkaround && faceDown && (screenAngle === 90 || screenAngle === 270)) {
        compassHeading = 0 - compassHeading;
        landscapeWorkaroundApplied = true;
    }

    // normalizeHeading handles the (-180,180] → [0,360) mapping
    return {
        heading: normalizeHeading(compassHeading),
        faceDown,
        landscapeWorkaroundApplied
    };
}

// Log compass availability once
/*if (TAURI_MOBILE) {
    console.log('🢄📱 Tauri Mobile detected, sensor-based compass will be available');
} else if (TAURI) {
    console.log('🢄💻 Tauri Desktop detected, compass not available');
} else if ('ondeviceorientationabsolute' in window || 'ondeviceorientation' in window) {
    console.log('🢄🧭 Web DeviceOrientation API detected');
} else {
    console.log('🢄❌ No compass API available');
}*/

// Tauri sensor implementation
async function startTauriSensor(mode: SensorMode = SensorMode.UPRIGHT_ROTATION_VECTOR): Promise<boolean> {
    try {
        if (!isSensorAvailable()) {
            console.warn('🢄🔍 Tauri sensor not available');
            return false;
        }

        const sensor = tauriSensor!;

        console.log('🢄🔍🔄 Starting Tauri sensor with mode:', SensorMode[mode]);
        try {
            await sensor.startSensor(mode);
        } catch (startError) {
            console.error('🢄🔍❌ sensor.startSensor() threw error:', startError);
            throw startError;
        }

		if (!tauriSensorListener)
		{
			tauriSensorListener = await sensor.onSensorData((data: SensorData) => {
				//console.log('🢄🔍📡 Native sensor data received:', JSON.stringify(data));

				// Handle potentially different event formats
				const sensorData = data;

				const compassUpdate = {
					magnetic_heading: sensorData.magnetic_heading,
					true_heading: sensorData.true_heading,
					accuracy_level: sensorData.accuracy_level,
					timestamp: sensorData.timestamp,
					source: sensorData.source || 'tauri'
				};

				scheduleCompassUpdate(compassUpdate);

				/*
					const modeStr = get(currentSensorMode);
					console.log(`🔍🧭 Compass update from ${data.source || 'Unknown'} (Mode: ${SensorMode[modeStr]}):`, JSON.stringify({
						'compass bearing (magnetic)': compassUpdate.magnetic_heading?.toFixed(1) + '°',
						'compass bearing (true)': compassUpdate.true_heading?.toFixed(1) + '°',
						accuracy_level: compassUpdate.accuracy_level,
						pitch: data.pitch?.toFixed(1) + '°',
						roll: data.roll?.toFixed(1) + '°',
						timestamp: new Date(data.timestamp).toLocaleTimeString()
					}));
				*/
			});
		}

        //console.log('🢄🔍✅ Tauri sensor listener:', JSON.stringify(tauriSensorListener));

        return true;
    } catch (error) {
        console.error('🢄🔍❌ Failed to start Tauri sensor:', error);
        console.error('🢄🔍 Error details:', JSON.stringify( {
            message: error instanceof Error ? error.message : String(error),
            stack: error instanceof Error ? error.stack : undefined,
            type: error instanceof Error ? error.constructor.name : typeof error
        }));
        return false;
    }
}

/**
 * Extract heading data from a DeviceOrientationEvent, choosing between
 * webkitCompassHeading (iOS) and tilt-compensated computation (Android/desktop),
 * and populating a debug trace of all inputs and intermediate values.
 */
async function extractHeadingFromEvent(event: DeviceOrientationEvent): Promise<{
    magnetic_heading: number | null;
    true_heading: number | null;
    accuracy_level: number | null;
    source: string;
    debug: CompassData['debug'];
}> {
    const isAbsolute = event.absolute;
    const screenAngle = window.screen?.orientation?.angle;

    const debug: CompassData['debug'] = {
        alpha: event.alpha ?? null,
        beta: event.beta ?? null,
        gamma: event.gamma ?? null,
        absolute: isAbsolute,
        screenAngle,
        webkitCompassHeading: event.webkitCompassHeading ?? null,
        webkitCompassAccuracy: event.webkitCompassAccuracy ?? null,
        compassHeading: event.compassHeading ?? null,
        headingMethod: 'none',
        rawHeading: null,
        normalizedHeading: null,
        screenOrientation: window.screen?.orientation?.angle,
        faceDown: false,
        landscapeWorkaroundApplied: false
    };

    let rawHeading: number | null = null;

    if (event.webkitCompassHeading != null) {
        debug.headingMethod = 'webkitCompassHeading';
        rawHeading = event.webkitCompassHeading;
    } else if (event.alpha != null && event.beta != null && event.gamma != null) {
        debug.headingMethod = 'tiltCompensated';
        const currentSettings = await getSettings();
        const landscapeWorkaround = currentSettings?.landscape_armor22_workaround ?? settingsDefaults.landscape_armor22_workaround;
        const result = computeTiltCompensatedHeading(event.alpha, event.beta, event.gamma, landscapeWorkaround);
        rawHeading = result.heading;
        debug.faceDown = result.faceDown;
        debug.landscapeWorkaroundApplied = result.landscapeWorkaroundApplied;
    }

    debug.rawHeading = rawHeading;
    const normalizedHeading = rawHeading !== null ? normalizeHeading(rawHeading) : null;
    debug.normalizedHeading = normalizedHeading;

    const accuracy = event.webkitCompassAccuracy ?? null;

    return {
        magnetic_heading: isAbsolute ? null : normalizedHeading,
        true_heading: isAbsolute
            ? normalizedHeading
            : (event.compassHeading != null ? normalizeHeading(event.compassHeading) : null),
        accuracy_level: accuracy,
        source: isAbsolute ? 'web-absolute' : 'web-magnetic',
        debug,
    };
}

// Web DeviceOrientation implementation
async function startWebCompass(): Promise<boolean> {
    return new Promise((resolve) => {
        let hasResolved = false;
        let usingAbsolute = false;

        orientationHandler = async (event: DeviceOrientationEvent) => {
            const isAbsolute = event.absolute;

            // Once we receive an absolute event, drop the regular listener
            // to avoid duplicate updates with different north references
            // (absolute = true north, regular = magnetic north).
			if (isAbsolute)
			{
				absoluteReadingsCount++;
			}
            if ((absoluteReadingsCount > 3) && !usingAbsolute) {
                usingAbsolute = true;
                if (regularOrientationListener) {
                    console.log('🢄🌐 Got deviceorientationabsolute, dropping deviceorientation listener');
                    window.removeEventListener('deviceorientation', regularOrientationListener);
                    regularOrientationListener = null;
                }
            }

            // If we already have absolute events, ignore regular ones
            // DISABLED: Some browsers only fire absolute once, so we need regular as fallback
            // if (usingAbsolute && !isAbsolute) return;

            if (!hasResolved) {
                hasResolved = true;
                console.log('🢄✅ DeviceOrientation API is working (absolute:', isAbsolute, ')');
                resolve(true);
            }

            const extracted = await extractHeadingFromEvent(event);

            const data: CompassData = {
                ...extracted,
                timestamp: Date.now(),
            };

            scheduleCompassUpdate(data);
            lastSensorUpdate.set(Date.now());
        };

        // Register both; once absolute fires, the regular one gets dropped.
        if ('ondeviceorientationabsolute' in window) {
            absoluteOrientationListener = (e) => orientationHandler?.(e);
            window.addEventListener('deviceorientationabsolute', absoluteOrientationListener);
        }
        regularOrientationListener = (e) => orientationHandler?.(e);
        window.addEventListener('deviceorientation', regularOrientationListener);

        // Set a timeout to check if we received any events
        setTimeout(() => {
            if (!hasResolved) {
                hasResolved = true;
                console.warn('🢄⚠️ [compass] No DeviceOrientation events received after 3 seconds');
                resolve(false);
            }
        }, 3000);
    });
}

// Simple user-level API functions
export const compassEnabled = writable(false);

export function enableCompass() {
	if (!get(compassEnabled)) {
    	console.log('🢄🧭 User enables orientation tracking..');
	}
    compassEnabled.set(true);
}

export function disableCompass() {
	if (get(compassEnabled)) {
    	console.log('🢄🛑 User disabled compass');
	}
    compassEnabled.set(false);
}

export function setCompassMode(mode: SensorMode) {
    console.log('🢄🔄 User changed compass mode to:', SensorMode[mode]);
    compassMode.set(mode);
}


async function stopCompassInternal() {
    // Stop accuracy polling
    //stopAccuracyPolling();

    // Stop lag monitoring
    //stopLagMonitoring();

    // Stop Tauri sensor if active
    // if (tauriSensorListener) {
    //     // Try to unregister listener (may fail if backend doesn't have remove_listener)
    //     tauriSensorListener.unregister().catch((error: unknown) => {
    //         // Ignore error if remove_listener command doesn't exist
    //         // The listener will be cleaned up when the plugin is destroyed
    //         console.debug('🢄🧙 Could not unregister sensor listener (expected on Android):', error);
    //     });
    //     tauriSensorListener = null;

        if (TAURI_MOBILE) {
			// Try to stop the sensor service
			if (tauriSensor) {
				tauriSensor.stopSensor().catch((error: unknown) => {
					console.error('🢄🔍 Failed to stop Tauri sensor:', error);
				});
			}
        }
    // }

    // Stop DeviceOrientation if active
    if (regularOrientationListener) {
        window.removeEventListener('deviceorientation', regularOrientationListener);
        regularOrientationListener = null;
    }
    if (absoluteOrientationListener) {
        window.removeEventListener('deviceorientationabsolute', absoluteOrientationListener as any);
        absoluteOrientationListener = null;
    }
    orientationHandler = null;

    // Reset stores
    compassData.set({
        magnetic_heading: null,
        true_heading: null,
        accuracy_level: null,
        timestamp: Date.now(),
        source: 'unknown'
    });

    // Reset sensor accuracy store
    sensorAccuracy.set({
        magnetometer: null,
        accelerometer: null,
        gyroscope: null,
        timestamp: 0
    });

    // Reset throttling state
    pendingCompassUpdate = null;
    compassUpdateScheduled = false;

    compassError.set(null);
    lastSensorUpdate.set(null);
}

// Check if compass permission is needed (iOS 13+)
export async function requestCompassPermission(): Promise<boolean> {
    // Skip permission check for Tauri
    if (TAURI) {
        //console.log('🢄📱 Tauri app - skipping web permission check');
        permissionGranted = true;
        return true;
    }

    // Check if we need permission (iOS 13+)
    if (typeof (DeviceOrientationEvent as any).requestPermission === 'function') {
        try {
            //console.log('🢄📱 Requesting DeviceOrientation permission...');
            const response = await (DeviceOrientationEvent as any).requestPermission();
            permissionGranted = response === 'granted';
            //console.log('🢄Permission response:', response);
            return permissionGranted;
        } catch (error) {
            console.error('🢄Permission request failed:', error);
            compassError.set('Failed to request compass permission');
            return false;
        }
    }

    // No permission needed
    permissionGranted = true;
    return true;
}

// User preference stores - UI controls these directly
export const compassMode = writable<SensorMode>(SensorMode.UPRIGHT_ROTATION_VECTOR);

// Track if compass is actually running internally (separate from user preference and success state)
let compassInternallyActive = false;

// Flag to prevent recursion when reverting user preference
let revertingUserPreference = false;

// State machine that manages compass based on user preferences + route state
async function updateCompassState() {
	//console.log('updateCompassState()');

	// Don't process updates if we're reverting user preference to avoid recursion
	if (revertingUserPreference) {
		return;
	}
	const userEnabled = get(compassEnabled);
	const onMapRoute = get(isOnMapRoute);
	const currentState = get(compassState);
	const userMode = get(compassMode);

	/*console.log('🢄️ Compass state update:', JSON.stringify(
		{ userEnabled, onMapRoute, currentState })
	);*/

	if (!userEnabled || !onMapRoute) {
		// User disabled or not on map route - set to inactive
		if (currentState !== 'inactive') {
			compassState.set('inactive');
			if (compassInternallyActive) {
				compassInternallyActive = false;
				await stopCompassInternal();
			}
		}
	} else {
		// User enabled and on map route - should be active
		if (currentState === 'inactive') {
			compassState.set('starting');
			compassError.set(null);

			// Try to start sensor
			compassInternallyActive = true;
			const success = await startCompassInternal(userMode);

			if (success) {
				compassState.set('active');
			} else {
				compassState.set('error');
				compassInternallyActive = false;
				// Revert user preference on failure (permission denied, etc.)
				console.log('🢄🧭 Compass start failed, reverting user preference');
				revertingUserPreference = true;
				compassEnabled.set(false);
				// After setting compassEnabled to false, reset the state to inactive and clear the flag
				compassState.set('inactive');
				revertingUserPreference = false;
			}
		}
	}
}

// Subscribe to state changes
compassEnabled.subscribe(updateCompassState);
compassMode.subscribe(updateCompassState);
isOnMapRoute.subscribe(updateCompassState);

async function startCompassInternal(mode?: SensorMode) {
    const sensorMode = mode ?? get(currentSensorMode);
    //console.log('🢄🧭 Starting compass with mode:', SensorMode[sensorMode]);

    // If WEB_DEVICE_ORIENTATION mode is selected, skip Tauri and go straight to web API
    if (sensorMode === SensorMode.WEB_DEVICE_ORIENTATION) {
        console.log('🢄🌐 WEB_DEVICE_ORIENTATION mode selected, using web API');
        // Skip directly to web API
    } else if (isSensorAvailable()) {
        // Try Tauri sensor first (Android native sensor)
        //console.log('🢄🔍 Tauri sensor API available, attempting to start...');
        const success = await startTauriSensor(sensorMode);
        if (success) {
            //console.log('🢄🔍✅ Tauri sensor started successfully');
            compassError.set(null);
            currentSensorMode.set(sensorMode);

            // Note: Location for magnetic declination comes from frontend's update_location calls to Kotlin
            // No need to request location separately - sensor service uses whatever location is available

            return true;
        }
        console.warn('🢄🔍⚠️ Tauri sensor failed, falling back to web APIs');
    }

    // Check permission for web APIs
    if (!permissionGranted) {
        const granted = await requestCompassPermission();
        if (!granted) {
            compassError.set('Compass permission denied');
            return false;
        }
    }

    // Try web compass
    const webSuccess = await startWebCompass();
    if (webSuccess) {
        compassError.set(null);
        currentSensorMode.set(sensorMode);
        // Note: No accuracy polling for web compass since it doesn't have sensor accuracy

        // Start lag monitoring for web compass too
        //startLagMonitoring();

        return true;
    }

    compassError.set('No compass available on this device');
    return false;
}

// Extended TypeScript definitions for compass events
declare global {
    interface DeviceOrientationEvent {
        webkitCompassHeading?: number;
        webkitCompassAccuracy?: number;
        compassHeading?: number;
        source?: string;
    }
}

// Export a function to get compass availability
export function isCompassAvailable(): boolean {
    if (typeof window === 'undefined') return false;
    return isSensorAvailable() ||
           'ondeviceorientationabsolute' in window ||
           'ondeviceorientation' in window;
}

// Reactive store for compass availability
export const compassAvailable = writable(isCompassAvailable());



let lastBearing: number | null = null;
/* refactor, smoothing happens in EnhancedSensorService.kt already (and also it only fires on changes), so smoothing on the frontend would only be useful if we need to smoothen web compass api
* but also consider car mode...
*  */
const SMOOTHING_FACTOR = 0; // 0 = no smoothing, 1 = no change

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
currentCompassHeading.subscribe(compass => {
	//console.log('🢄🧭 Compass subscription fired - mode:', get(bearingMode), 'state:', get(compassState), 'heading:', compass?.heading);
	if (get(bearingMode) !== 'walking') return;
    if (!compass || compass.heading === null || get(compassState) !== 'active') return;
	if (isNaN(compass.heading)) return;

    const targetBearing = (360 + compass.heading) % 360;

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
	const currentBearing = get(bearingState).bearing;
	//console.log('🢄🧭 About to updateBearing? current:', currentBearing, 'smoothed:', smoothedBearing);
	if (isNaN(currentBearing) || currentBearing === null || (Math.abs(smoothedBearing - currentBearing) > 1)) {
		updateBearing(smoothedBearing, compass.source, undefined, compass.accuracy_level);
	}
});

// Reset smoothing when compass stops
compassState.subscribe(state => {
    if (state !== 'active') {
        lastBearing = null;
    }
});

export const compassWalkingActive = derived(
    [compassEnabled, bearingMode],
    ([$compassEnabled, $bearingMode]) => {
		//console.log(`compassWalkingActive: $compassEnabled: ${$compassEnabled}, $bearingMode: ${$bearingMode}`);
        return $compassEnabled && $bearingMode === 'walking';
    }
);

