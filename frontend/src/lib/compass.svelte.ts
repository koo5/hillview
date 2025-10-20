import { writable, derived, get } from 'svelte/store';
import { TAURI, TAURI_MOBILE, tauriSensor, isSensorAvailable, type SensorData, SensorMode } from './tauri';
import {PluginListener} from "@tauri-apps/api/core";
import { invoke } from '@tauri-apps/api/core';
import { locationManager } from './locationManager';
import {bearingMode, bearingState, updateBearing} from "$lib/mapState";

export interface CompassData {
    magneticHeading: number | null;  // 0-360 degrees from magnetic north
    trueHeading: number | null;       // 0-360 degrees from true north
    headingAccuracy: number | null;   // Accuracy in degrees
    timestamp: number;
    source: string;
}

export interface DeviceOrientation {
    alpha: number | null;    // Z-axis rotation (0-360)
    beta: number | null;     // X-axis rotation (-180 to 180)
    gamma: number | null;    // Y-axis rotation (-90 to 90)
    absolute: boolean;
}

// compassData - feeds into currentCompassHeading
export const compassData = writable<CompassData>({
    magneticHeading: null,
    trueHeading: null,
    headingAccuracy: null,
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
        if ($compassData && $compassData.trueHeading !== null) {
            return {
                heading: $compassData.trueHeading,
                source: ($compassData.source + '-compass-true') as string,
                accuracy: $compassData.headingAccuracy
            };
        }
        if ($compassData && $compassData.magneticHeading !== null) {
            return {
                heading: $compassData.magneticHeading,
                source: ($compassData.source + '-compass-magnetic') as string,
                accuracy: $compassData.headingAccuracy
            };
        }
        return {
            heading: null,
            source: 'none' as const,
            accuracy: null
        };
    }
);

// Store to track if compass is active
export const compassActive = writable(false);

// Store to track compass errors
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

// Permission state
let permissionGranted = false;

// Track active listeners
let orientationHandler: ((event: DeviceOrientationEvent) => void) | null = null;
let tauriSensorListener: PluginListener | null = null;

// Accuracy polling
let accuracyPollingInterval: number | null = null;

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

// Log compass availability once
if (TAURI_MOBILE) {
    console.log('🢄📱 Tauri Mobile detected, sensor-based compass will be available');
} else if (TAURI) {
    console.log('🢄💻 Tauri Desktop detected, compass not available');
} else if ('ondeviceorientationabsolute' in window || 'ondeviceorientation' in window) {
    console.log('🢄🧭 Web DeviceOrientation API detected');
} else {
    console.log('🢄❌ No compass API available');
}

// Tauri sensor implementation
async function startTauriSensor(mode: SensorMode = SensorMode.UPRIGHT_ROTATION_VECTOR): Promise<boolean> {
    try {
        if (!isSensorAvailable()) {
            console.warn('🢄🔍 Tauri sensor not available');
            return false;
        }
        
        const sensor = tauriSensor!;
        
        console.log('🢄🔍🔄 Starting Tauri sensor with mode:', SensorMode[mode]);
        console.log('🢄🔍 About to call sensor.startSensor()...');
        try {
            await sensor.startSensor(mode);
            console.log('🢄🔍✅ sensor.startSensor() completed successfully with mode:', SensorMode[mode]);
        } catch (startError) {
            console.error('🢄🔍❌ sensor.startSensor() threw error:', startError);
            throw startError;
        }

        // Set up sensor data listener
        console.log('🢄🔍 About to set up sensor data listener...');
        
        tauriSensorListener = await sensor.onSensorData((data: SensorData) => {
            //console.log('🢄🔍📡 Native sensor data received:', JSON.stringify(data));

            // Handle potentially different event formats
            const sensorData = data;

            const compassUpdate = {
                magneticHeading: sensorData.magneticHeading,
                trueHeading: sensorData.trueHeading,
                headingAccuracy: sensorData.headingAccuracy,
                timestamp: sensorData.timestamp,
                source: sensorData.source || 'tauri'
            };
            
            scheduleCompassUpdate(compassUpdate);

            if (false) {
                const modeStr = get(currentSensorMode);
                console.log(`🔍🧭 Compass update from ${data.source || 'Unknown'} (Mode: ${SensorMode[modeStr]}):`, JSON.stringify({
                    'compass bearing (magnetic)': compassUpdate.magneticHeading?.toFixed(1) + '°',
                    'compass bearing (true)': compassUpdate.trueHeading?.toFixed(1) + '°',
                    accuracy: '±' + compassUpdate.headingAccuracy?.toFixed(1) + '°',
                    pitch: data.pitch?.toFixed(1) + '°',
                    roll: data.roll?.toFixed(1) + '°',
                    timestamp: new Date(data.timestamp).toLocaleTimeString()
                }));
            }
        });

        console.log('🢄🔍✅ Tauri sensor listener:', JSON.stringify(tauriSensorListener));

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

// Web DeviceOrientation implementation
async function startWebCompass(): Promise<boolean> {
    return new Promise((resolve) => {
        let hasResolved = false;

        orientationHandler = (event: DeviceOrientationEvent) => {
            if (!hasResolved) {
                hasResolved = true;
                console.log('🢄✅ DeviceOrientation API is working');
                resolve(true);
            }

            // Extract compass data
            const magneticHeading = event.webkitCompassHeading ?? event.alpha;
            const accuracy = event.webkitCompassAccuracy ?? null;
            
            // Some browsers provide true heading directly
            const trueHeading = event.compassHeading ?? null;

            const data = {
                magneticHeading: magneticHeading !== null ? normalizeHeading(magneticHeading) : null,
                trueHeading: trueHeading !== null ? normalizeHeading(trueHeading) : null,
                headingAccuracy: accuracy,
                timestamp: Date.now(),
                source: 'web'
            };
            
            scheduleCompassUpdate(data);
            lastSensorUpdate.set(Date.now());
            
            // Log occasional updates
            if (false) {
                console.log('🢄🌐 Web Compass update:', JSON.stringify({
                    source: event.source || 'deviceorientation',
                    magneticHeading: data.magneticHeading?.toFixed(1) + '°',
                    trueHeading: data.trueHeading?.toFixed(1) + '°',
                    accuracy: data.headingAccuracy ? '±' + data.headingAccuracy?.toFixed(1) + '°' : 'unknown',
                    alpha: event.alpha?.toFixed(1) + '°',
                    beta: event.beta?.toFixed(1) + '°',
                    gamma: event.gamma?.toFixed(1) + '°',
                    absolute: event.absolute
                }));
            }
        };

        // Try absolute orientation first
        if ('ondeviceorientationabsolute' in window) {
            window.addEventListener('deviceorientationabsolute', (e) => {orientationHandler?.({...e, source: 'ondeviceorientationabsolute'})});
        }
        // Fall back to regular orientation
        window.addEventListener('deviceorientation', (e) => {orientationHandler?.({...e, source: 'deviceorientation'})});

        // Set a timeout to check if we received any events
        setTimeout(() => {
            if (!hasResolved) {
                hasResolved = true;
                console.warn('🢄⚠️ No DeviceOrientation events received after 3 seconds');
                resolve(false);
            }
        }, 3000);
    });
}

// Stop all compass services
export async function stopCompass() {
    //console.log('🢄🛑 Stopping compass');
    compassActive.set(false);

    // Stop accuracy polling
    stopAccuracyPolling();

    // Stop Tauri sensor if active
    if (tauriSensorListener) {
        // Try to unregister listener (may fail if backend doesn't have remove_listener)
        tauriSensorListener.unregister().catch((error: unknown) => {
            // Ignore error if remove_listener command doesn't exist
            // The listener will be cleaned up when the plugin is destroyed
            console.debug('🢄🧙 Could not unregister sensor listener (expected on Android):', error);
        });
        tauriSensorListener = null;

        // Try to stop the sensor service
        if (tauriSensor) {
            tauriSensor.stopSensor().catch((error: unknown) => {
                console.error('🢄🔍 Failed to stop Tauri sensor:', error);
            });
        }

        // Release location service for compass
        if (TAURI_MOBILE) {
            try {
                await locationManager.releaseLocation('compass');
                console.log('🢄🔍 ✅ Compass released location service');
            } catch (err) {
                console.error('🢄🔍 ❌ Compass failed to release location service:', err);
            }
        }
    }

    // Stop DeviceOrientation if active
    if (orientationHandler) {
        window.removeEventListener('deviceorientation', orientationHandler);
        if ('ondeviceorientationabsolute' in window) {
            window.removeEventListener('deviceorientationabsolute', orientationHandler as any);
        }
        orientationHandler = null;
    }

    // Reset stores
    compassData.set({
        magneticHeading: null,
        trueHeading: null,
        headingAccuracy: null,
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

// Main compass start function
export async function startCompass(mode?: SensorMode) {
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
            compassActive.set(true);
            compassError.set(null);
            currentSensorMode.set(sensorMode);

            // Start accuracy polling for Android
            startAccuracyPolling();

            // Request location service for compass (needed for true north calculation)
            if (TAURI_MOBILE) {
                try {
                    await locationManager.requestLocation('compass');
                    console.log('🢄🔍 ✅ Compass requested location service successfully');
                } catch (err) {
                    console.error('🢄🔍 ❌ Compass failed to request location service:', err);
                    // Don't fail compass startup if location fails - magnetic heading still works
                }
            }

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
        compassActive.set(true);
        compassError.set(null);
        currentSensorMode.set(sensorMode);
        // Note: No accuracy polling for web compass since it doesn't have sensor accuracy
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
    return isSensorAvailable() || 
           'ondeviceorientationabsolute' in window || 
           'ondeviceorientation' in window;
}

// Reactive store for compass availability
export const compassAvailable = writable(isCompassAvailable());

// Function to switch sensor mode while running
export async function switchSensorMode(mode: SensorMode) {
    const oldMode = get(currentSensorMode);
    console.log('🢄🔄 Switching sensor mode:', SensorMode[oldMode], '→', SensorMode[mode]);

    if (!get(compassActive)) {
        console.warn('🢄⚠️ Compass not active, starting with new mode:', SensorMode[mode]);
        return startCompass(mode);
    }

    console.log('🢄🛑 Stopping current sensor...');
    // Stop current sensor
    await stopCompass();

    // Wait a bit for cleanup
    console.log('🢄⏳ Waiting for cleanup...');
    await new Promise(resolve => setTimeout(resolve, 100));

    // Start with new mode
    console.log('🢄🚀 Starting sensor with new mode:', SensorMode[mode]);
    const success = await startCompass(mode);

    if (success) {
        console.log('🢄✅ Successfully switched to mode:', SensorMode[mode]);
    } else {
        console.error('🢄❌ Failed to switch to mode:', SensorMode[mode]);
    }

    return success;
}

// Function to get current sensor accuracy status
export async function getSensorAccuracy(): Promise<{
    magnetometer: string;
    accelerometer: string;
    gyroscope: string;
    timestamp: number;
} | null> {
    if (!TAURI_MOBILE) {
        console.log('🢄🔍 Sensor accuracy not available on non-mobile platform');
        return null;
    }

    try {
        console.log('🢄🔍📊 Getting sensor accuracy from native plugin');
        const result = await invoke('plugin:hillview|getSensorAccuracy');
        console.log('🢄🔍✅ Sensor accuracy retrieved:', result);
        return result as {
            magnetometer: string;
            accelerometer: string;
            gyroscope: string;
            timestamp: number;
        };
    } catch (error) {
        console.error('🢄🔍❌ Failed to get sensor accuracy:', error);
        return null;
    }
}

// Function to start polling sensor accuracy
function startAccuracyPolling() {
    if (!TAURI_MOBILE || accuracyPollingInterval !== null) {
        return;
    }

    console.log('🢄🔍🕒 Starting sensor accuracy polling');

    // Poll every 2 seconds
    accuracyPollingInterval = window.setInterval(async () => {
        try {
            const accuracy = await getSensorAccuracy();
            if (accuracy) {
                sensorAccuracy.set(accuracy);
            }
        } catch (error) {
            console.warn('🢄🔍⚠️ Accuracy polling failed:', error);
        }
    }, 2000);
}

// Function to stop polling sensor accuracy
function stopAccuracyPolling() {
    if (accuracyPollingInterval !== null) {
        console.log('🢄🔍🛑 Stopping sensor accuracy polling');
        clearInterval(accuracyPollingInterval);
        accuracyPollingInterval = null;
    }
}

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
	if (get(bearingMode) !== 'walking') return;
    if (!compass || compass.heading === null || !get(compassActive)) return;
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
	if (isNaN(currentBearing) || currentBearing === null || (Math.abs(smoothedBearing - currentBearing) > 1)) {
		updateBearing(smoothedBearing, compass.source);
	}
});

// Reset smoothing when tracking stops
compassActive.subscribe(tracking => {
    if (!tracking) {
        lastBearing = null;
    }
});

