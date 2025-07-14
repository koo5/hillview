import { writable, derived, get } from 'svelte/store';
import { gpsCoordinates } from './location.svelte';
import type { UnlistenFn } from '@tauri-apps/api/event';
import { TAURI, TAURI_MOBILE, tauriSensor, isSensorAvailable, type SensorData } from './tauri';

export interface CompassData {
    magneticHeading: number | null;  // 0-360 degrees from magnetic north
    trueHeading: number | null;       // 0-360 degrees from true north
    headingAccuracy: number | null;   // Accuracy in degrees
    timestamp: number;
}

export interface DeviceOrientation {
    alpha: number | null;    // Z-axis rotation (0-360)
    beta: number | null;     // X-axis rotation (-180 to 180)
    gamma: number | null;    // Y-axis rotation (-90 to 90)
    absolute: boolean;
}

// Initialize stores
export const compassData = writable<CompassData>({
    magneticHeading: null,
    trueHeading: null,
    headingAccuracy: null,
    timestamp: Date.now()
});

export const deviceOrientation = writable<DeviceOrientation>({
    alpha: null,
    beta: null,
    gamma: null,
    absolute: false
});

// Derived store for current heading with source information
export const currentHeading = derived(
    [compassData],
    ([$compassData]) => {
        if ($compassData && $compassData.trueHeading !== null) {
            return {
                heading: $compassData.trueHeading,
                source: 'compass-true' as const,
                accuracy: $compassData.headingAccuracy
            };
        }
        if ($compassData && $compassData.magneticHeading !== null) {
            return {
                heading: $compassData.magneticHeading,
                source: 'compass-magnetic' as const,
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

// Permission state
let permissionGranted = false;

// Track active listeners
let orientationHandler: ((event: DeviceOrientationEvent) => void) | null = null;
let tauriSensorUnlisten: UnlistenFn | null = null;

// Helper to normalize heading to 0-360 range
function normalizeHeading(heading: number): number {
    return ((heading % 360) + 360) % 360;
}

// Log compass availability once
if (TAURI_MOBILE) {
    console.log('📱 Tauri Mobile detected, sensor-based compass will be available');
} else if (TAURI) {
    console.log('💻 Tauri Desktop detected, compass not available');
} else if ('ondeviceorientationabsolute' in window || 'ondeviceorientation' in window) {
    console.log('🧭 Web DeviceOrientation API detected');
} else {
    console.log('❌ No compass API available');
}

// Tauri sensor implementation
async function startTauriSensor(): Promise<boolean> {
    try {
        if (!isSensorAvailable()) {
            console.warn('Tauri sensor not available');
            return false;
        }
        
        const sensor = tauriSensor!;
        
        console.log('🔄 Starting Tauri TYPE_ROTATION_VECTOR sensor');
        await sensor.startSensor();
        
        // Set up location update listener
        const unsubscribe = gpsCoordinates.subscribe(coords => {
            if (coords && coords.latitude !== null && coords.longitude !== null) {
                if (Math.random() < 0.1) { // Log 10% of updates
                    console.log('📍 Updating sensor location:', coords.latitude.toFixed(6), coords.longitude.toFixed(6));
                }
                
                // Update sensor location (fire and forget)
                if (sensor) {
                    sensor.updateSensorLocation(coords.latitude, coords.longitude).catch(error => {
                        console.error('Failed to update sensor location:', error);
                    });
                }
            }
        });
        
        // Set up sensor data listener
        tauriSensorUnlisten = await sensor.onSensorData((data: SensorData) => {
            const compassUpdate = {
                magneticHeading: data.magneticHeading,
                trueHeading: data.trueHeading,
                headingAccuracy: data.headingAccuracy,
                timestamp: data.timestamp
            };
            
            compassData.set(compassUpdate);
            
            // Also update device orientation for compatibility
            deviceOrientation.set({
                alpha: data.magneticHeading,
                beta: data.pitch,
                gamma: data.roll,
                absolute: true
            });
            
            // Log every ~10th update
            if (Math.random() < 0.1) {
                console.log('🧭 Tauri TYPE_ROTATION_VECTOR update:', {
                    magnetic: compassUpdate.magneticHeading?.toFixed(1) + '°',
                    true: compassUpdate.trueHeading?.toFixed(1) + '°',
                    accuracy: '±' + compassUpdate.headingAccuracy?.toFixed(1) + '°',
                    pitch: data.pitch?.toFixed(1) + '°',
                    roll: data.roll?.toFixed(1) + '°',
                    timestamp: new Date(data.timestamp).toLocaleTimeString()
                });
            }
        });
        
        // Start the sensor
        await sensor.startSensor();
        
        return true;
    } catch (error) {
        console.error('❌ Failed to start Tauri sensor:', error);
        console.error('Error details:', {
            message: error instanceof Error ? error.message : String(error),
            stack: error instanceof Error ? error.stack : undefined,
            type: error instanceof Error ? error.constructor.name : typeof error
        });
        // Clean up
        if (tauriSensorUnlisten) {
            tauriSensorUnlisten();
            tauriSensorUnlisten = null;
        }
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
                console.log('✅ DeviceOrientation API is working');
                resolve(true);
            }
            
            // Update device orientation
            deviceOrientation.set({
                alpha: event.alpha,
                beta: event.beta,
                gamma: event.gamma,
                absolute: event.absolute || false
            });

            // Extract compass data
            const magneticHeading = event.webkitCompassHeading ?? event.alpha;
            const accuracy = event.webkitCompassAccuracy ?? null;
            
            // Some browsers provide true heading directly
            const trueHeading = event.compassHeading ?? null;

            const data = {
                magneticHeading: magneticHeading !== null ? normalizeHeading(magneticHeading) : null,
                trueHeading: trueHeading !== null ? normalizeHeading(trueHeading) : null,
                headingAccuracy: accuracy,
                timestamp: Date.now()
            };
            
            compassData.set(data);
            lastSensorUpdate.set(Date.now());
            
            // Log occasional updates
            if (Math.random() < 0.1) {
                console.log('Compass update:', {
                    magnetic: data.magneticHeading?.toFixed(1),
                    true: data.trueHeading?.toFixed(1),
                    accuracy: data.headingAccuracy?.toFixed(1)
                });
            }
        };

        // Try absolute orientation first
        if ('ondeviceorientationabsolute' in window) {
            window.addEventListener('deviceorientationabsolute', orientationHandler as any);
        }
        // Fall back to regular orientation
        window.addEventListener('deviceorientation', orientationHandler);

        // Set a timeout to check if we received any events
        setTimeout(() => {
            if (!hasResolved) {
                hasResolved = true;
                console.warn('⚠️ No DeviceOrientation events received');
                resolve(false);
            }
        }, 3000);
    });
}

// Stop all compass services
export function stopCompass() {
    console.log('🛑 Stopping compass');
    compassActive.set(false);
    
    // Stop Tauri sensor if active
    if (tauriSensorUnlisten) {
        tauriSensorUnlisten();
        tauriSensorUnlisten = null;
        
        // Try to stop the sensor service
        if (tauriSensor) {
            tauriSensor.stopSensor().catch((error: unknown) => {
                console.error('Failed to stop Tauri sensor:', error);
            });
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
        timestamp: Date.now()
    });
    
    deviceOrientation.set({
        alpha: null,
        beta: null,
        gamma: null,
        absolute: false
    });
    
    compassError.set(null);
    lastSensorUpdate.set(null);
}

// Check if compass permission is needed (iOS 13+)
export async function requestCompassPermission(): Promise<boolean> {
    // Skip permission check for Tauri
    if (TAURI) {
        console.log('📱 Tauri app - skipping web permission check');
        permissionGranted = true;
        return true;
    }
    
    // Check if we need permission (iOS 13+)
    if (typeof (DeviceOrientationEvent as any).requestPermission === 'function') {
        try {
            console.log('📱 Requesting DeviceOrientation permission...');
            const response = await (DeviceOrientationEvent as any).requestPermission();
            permissionGranted = response === 'granted';
            console.log('Permission response:', response);
            return permissionGranted;
        } catch (error) {
            console.error('Permission request failed:', error);
            compassError.set('Failed to request compass permission');
            return false;
        }
    }
    
    // No permission needed
    permissionGranted = true;
    return true;
}

// Main compass start function
export async function startCompass() {
    console.log('🧭 Starting compass...');
    
    // Try Tauri sensor first (Android native sensor)
    if (isSensorAvailable()) {
        console.log('🔍 Tauri sensor API available, attempting to start...');
        const success = await startTauriSensor();
        if (success) {
            console.log('✅ Tauri sensor started successfully');
            compassActive.set(true);
            compassError.set(null);
            return true;
        }
        console.warn('⚠️ Tauri sensor failed, falling back to web APIs');
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
    }
    
    interface Window {
        __TAURI__?: any;
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