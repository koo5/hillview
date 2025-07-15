// Tauri platform detection and utilities
// Based on pattern from yellow-dev project

import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { platform } from '@tauri-apps/plugin-os';

// Check if window is defined (tests/SSR may not have window)
const hasWindow = typeof window !== 'undefined';

// Avoid conflicts with other type declarations by not extending Window

// Core constants for platform detection
export const TAURI = hasWindow && Object.prototype.hasOwnProperty.call(window, '__TAURI__');
export const BROWSER = !TAURI;

// Platform detection
let platformName = 'browser';
if (TAURI && hasWindow) {
    try {
        platformName = platform();
        console.log('🔍 Platform detected:', platformName);
    } catch (error) {
        console.warn('🔍 Failed to detect Tauri platform:', error);
    }
} else {
    console.log('🔍 Not running in Tauri, platform:', platformName);
}

export const TAURI_MOBILE = TAURI && (platformName === 'android' || platformName === 'ios');
export const TAURI_DESKTOP = TAURI && !TAURI_MOBILE;

// Type definitions for sensor data
export interface SensorData {
    magneticHeading: number;  // Compass bearing in degrees from magnetic north (0-360°)
    trueHeading: number;      // Compass bearing corrected for magnetic declination
    headingAccuracy: number;
    pitch: number;
    roll: number;
    timestamp: number;
    sensorSource?: string;    // Identifies which sensor provided the data
}

// Conditional Tauri sensor API
export const tauriSensor = TAURI ? {
    startSensor: async () => {
        console.log('🔍📱 Starting Tauri sensor service');
        try {
            const result = await invoke('plugin:hillview|start_sensor');
            console.log('🔍✅ Tauri invoke start_sensor succeeded:', result);
            return result;
        } catch (error) {
            console.error('🔍❌ Tauri invoke start_sensor failed:', error);
            throw error;
        }
    },
    stopSensor: async () => {
        console.log('🔍📱 Stopping Tauri sensor service');
        try {
            const result = await invoke('plugin:hillview|stop_sensor');
            console.log('🔍✅ Tauri invoke stop_sensor succeeded:', result);
            return result;
        } catch (error) {
            console.error('🔍❌ Tauri invoke stop_sensor failed:', error);
            throw error;
        }
    },
    updateSensorLocation: async (latitude: number, longitude: number) => {
        return invoke('plugin:hillview|update_sensor_location', {
            location: { latitude, longitude }
        });
    },
    onSensorData: async (callback: (data: SensorData) => void) => {
        console.log('🔍👂 Setting up sensor data listener for event: plugin:hillview:sensor-data');
        try {
            const unlisten = await listen<SensorData>('plugin:hillview:sensor-data', (event) => {
                console.log('🔍📡 Received sensor event:', event);
                console.log('🔍📡 Event payload:', event.payload);
                callback(event.payload);
            });
            console.log('🔍✅ Sensor listener setup complete, unlisten function:', typeof unlisten);
            return unlisten;
        } catch (error) {
            console.error('🔍❌ Failed to setup sensor listener:', error);
            throw error;
        }
    }
} : null;

console.log('🔍 Tauri environment:', {
    TAURI,
    TAURI_MOBILE,
    TAURI_DESKTOP,
    platformName,
    hasTauriSensor: !!tauriSensor
});

// Utility function to check if Tauri APIs are available
export function isTauriAvailable(): boolean {
    return TAURI;
}

// Utility function to check if sensor APIs are available
export function isSensorAvailable(): boolean {
    const available = TAURI_MOBILE && tauriSensor !== null;
    console.log('🔍 isSensorAvailable():', available, { TAURI_MOBILE, hasTauriSensor: !!tauriSensor });
    return available;
}