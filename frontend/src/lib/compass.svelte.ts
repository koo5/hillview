import { writable, derived, get } from 'svelte/store';
import { gpsCoordinates } from './location.svelte';
import type { UnlistenFn } from '@tauri-apps/api/event';
import { TAURI, TAURI_MOBILE, tauriSensor, isSensorAvailable, type SensorData } from './tauri';
import {PluginListener} from "@tauri-apps/api/core";

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

// Initialize stores
export const compassData = writable<CompassData>({
    magneticHeading: null,
    trueHeading: null,
    headingAccuracy: null,
    timestamp: Date.now(),
    source: 'unknown'
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

// Permission state
let permissionGranted = false;

// Track active listeners
let orientationHandler: ((event: DeviceOrientationEvent) => void) | null = null;
let tauriSensorListener: PluginListener | null = null;

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
            console.warn('🔍 Tauri sensor not available');
            return false;
        }
        
        const sensor = tauriSensor!;
        
        console.log('🔍🔄 Starting Tauri TYPE_ROTATION_VECTOR sensor');
        console.log('🔍 About to call sensor.startSensor()...');
        try {
            await sensor.startSensor();
            console.log('🔍✅ sensor.startSensor() completed successfully');
        } catch (startError) {
            console.error('🔍❌ sensor.startSensor() threw error:', startError);
            throw startError;
        }

        // Set up sensor data listener
        console.log('🔍 About to set up sensor data listener...');
        
        tauriSensorListener = await sensor.onSensorData((data: SensorData) => {
            console.log('🔍📡 Native sensor data received:', JSON.stringify(data));

            // Handle potentially different event formats
            const sensorData = data;

            const compassUpdate = {
                magneticHeading: sensorData.magneticHeading,
                trueHeading: sensorData.trueHeading,
                headingAccuracy: sensorData.headingAccuracy,
                timestamp: sensorData.timestamp,
                source: sensorData.source || 'tauri'
            };
            
            compassData.set(compassUpdate);

            // Log every ~10th update
            if (Math.random() < 1.1) {
                console.log(`🔍🧭 Compass update from ${data.source || 'Unknown'}:`, JSON.stringify({
                    'compass bearing (magnetic)': compassUpdate.magneticHeading?.toFixed(1) + '°',
                    'compass bearing (true)': compassUpdate.trueHeading?.toFixed(1) + '°',
                    accuracy: '±' + compassUpdate.headingAccuracy?.toFixed(1) + '°',
                    pitch: data.pitch?.toFixed(1) + '°',
                    roll: data.roll?.toFixed(1) + '°',
                    timestamp: new Date(data.timestamp).toLocaleTimeString()
                }));
            }
        });

        console.log('🔍✅ Tauri sensor listener:', JSON.stringify(tauriSensorListener));

        return true;
    } catch (error) {
        console.error('🔍❌ Failed to start Tauri sensor:', error);
        console.error('🔍 Error details:', JSON.stringify( {
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
        let lastUpdate = 0;
        const THROTTLE_MS = 300; // Minimum ms between updates

        orientationHandler = (event: DeviceOrientationEvent) => {
            const now = Date.now();
            if (now - lastUpdate < THROTTLE_MS) return;
            lastUpdate = now;

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
                timestamp: Date.now(),
                source: 'web'
            };
            
            compassData.set(data);
            lastSensorUpdate.set(Date.now());
            
            // Log occasional updates
            if (Math.random() < 1.1) {
                console.log('Web Compass update:',JSON.stringify( data ));
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
                console.warn('⚠️ No DeviceOrientation events received after 3 seconds');
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
    if (tauriSensorListener) {
        tauriSensorListener.unregister();
        tauriSensorListener = null;
        
        // Try to stop the sensor service
        if (tauriSensor) {
            tauriSensor.stopSensor().catch((error: unknown) => {
                console.error('🔍 Failed to stop Tauri sensor:', error);
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
        timestamp: Date.now(),
        source: 'unknown'
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
            console.log('🔍✅ Tauri sensor started successfully');
            compassActive.set(true);
            compassError.set(null);
            return true;
        }
        console.warn('🔍⚠️ Tauri sensor failed, falling back to web APIs');
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