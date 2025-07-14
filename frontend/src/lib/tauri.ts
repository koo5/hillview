// Tauri platform detection and utilities
// Based on pattern from yellow-dev project

import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { platform } from '@tauri-apps/plugin-os';

// Check if window is defined (tests/SSR may not have window)
const hasWindow = typeof window !== 'undefined';

// Extend the global Window interface to include Tauri properties
declare global {
    interface Window {
        __TAURI__?: any;
        __TAURI_INTERNALS__?: any;
        __TAURI_OS_PLUGIN_INTERNALS__?: any;
    }
}

// Core constants for platform detection
export const TAURI = hasWindow && Object.prototype.hasOwnProperty.call(window, '__TAURI__');
export const BROWSER = !TAURI;

// Platform detection
let platformName = 'browser';
if (TAURI && hasWindow) {
    try {
        platformName = platform();
    } catch (error) {
        console.warn('Failed to detect Tauri platform:', error);
    }
}

export const TAURI_MOBILE = TAURI && (platformName === 'android' || platformName === 'ios');
export const TAURI_DESKTOP = TAURI && !TAURI_MOBILE;

// Type definitions for sensor data
export interface SensorData {
    magneticHeading: number;
    trueHeading: number;
    headingAccuracy: number;
    pitch: number;
    roll: number;
    timestamp: number;
}

// Conditional Tauri sensor API
export const tauriSensor = TAURI ? {
    startSensor: async () => {
        console.log('📱 Starting Tauri sensor service');
        return invoke('plugin:hillview|start_sensor');
    },
    stopSensor: async () => {
        console.log('📱 Stopping Tauri sensor service');
        return invoke('plugin:hillview|stop_sensor');
    },
    updateSensorLocation: async (latitude: number, longitude: number) => {
        return invoke('plugin:hillview|update_sensor_location', {
            location: { latitude, longitude }
        });
    },
    onSensorData: async (callback: (data: SensorData) => void) => {
        console.log('👂 Setting up sensor data listener');
        return listen<SensorData>('plugin:hillview:sensor-data', (event) => {
            callback(event.payload);
        });
    }
} : null;

// Utility function to check if Tauri APIs are available
export function isTauriAvailable(): boolean {
    return TAURI;
}

// Utility function to check if sensor APIs are available
export function isSensorAvailable(): boolean {
    return TAURI_MOBILE && tauriSensor !== null;
}