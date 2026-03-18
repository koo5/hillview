import {addPluginListener, invoke} from '@tauri-apps/api/core';

// Check if window is defined (tests/SSR may not have window)
const hasWindow = typeof window !== 'undefined';

// Avoid conflicts with other type declarations by not extending Window

// Core constants for platform detection
export const TAURI = hasWindow && Object.prototype.hasOwnProperty.call(window, '__TAURI_INTERNALS__');
export const BROWSER = hasWindow && !TAURI;

// Platform detection
let platformName = 'browser';
if (TAURI && hasWindow) {
    try {
        platformName = 'android' // window.__TAURI_OS_PLUGIN_INTERNALS__  //  platform(); // TypeError: Cannot read properties of undefined (reading 'platform')
        //console.log('🢄🔍 [TAURI] Platform detected:', platformName);
    } catch (error) {
        console.warn('🢄🔍 [TAURI] Failed to detect Tauri platform:', error);
    }
} else {
    //console.log('🢄🔍 [TAURI] Not running in Tauri, platform:', platformName);
}

export const TAURI_MOBILE = TAURI && (platformName === 'android' || platformName === 'ios');
export const TAURI_DESKTOP = TAURI && !TAURI_MOBILE;

// Type definitions for sensor data
export interface SensorData {
    magnetic_heading: number;  // Compass bearing in degrees from magnetic north (0-360°)
    true_heading: number;      // Compass bearing corrected for magnetic declination
    accuracy_level: number;
    pitch: number;
    roll: number;
    timestamp: number;
    source?: string;    // Identifies which sensor provided the data
}

// Sensor modes for enhanced sensor service
export enum SensorMode {
    ROTATION_VECTOR = 0,
    GAME_ROTATION_VECTOR = 1,  // Better for upright phone
    MADGWICK_AHRS = 2,         // Advanced sensor fusion
    COMPLEMENTARY_FILTER = 3,
    UPRIGHT_ROTATION_VECTOR = 4, // Optimized for portrait/upright orientation
    WEB_DEVICE_ORIENTATION = 5   // Force web DeviceOrientation API
}

// Conditional Tauri sensor API
export const tauriSensor = TAURI ? {
    startSensor: async (mode: SensorMode = SensorMode.UPRIGHT_ROTATION_VECTOR) => {
        console.log('🢄🔍📱 Starting Tauri sensor service with mode:', mode, `(${SensorMode[mode]})`);
        try {
            const result = await invoke('plugin:hillview|start_sensor', { mode });
            //console.log('🢄🔍✅ Tauri invoke start_sensor succeeded:', result);
            return result;
        } catch (error) {
            console.error('🢄🔍❌ Tauri invoke start_sensor failed:', error);
            throw error;
        }
    },
    stopSensor: async () => {
        console.log('🢄🔍📱 Stopping Tauri sensor service');
        try {
            const result = await invoke('plugin:hillview|stop_sensor');
            console.log('🢄🔍✅ Tauri invoke stop_sensor succeeded:', result);
            return result;
        } catch (error) {
            console.error('🢄🔍❌ Tauri invoke stop_sensor failed:', error);
            throw error;
        }
    },
    onSensorData: async (callback: (data: SensorData) => void) => {
        console.log('🢄🔍👂 Setting up sensor data listener using addPluginListener');
        try {
            // Use addPluginListener as per Tauri mobile plugin documentation
            const unlisten = await addPluginListener('hillview', 'sensor-data', (data: any) => {
                //console.log('🢄🔍📡 Received sensor event from plugin:', JSON.stringify(data));
                callback(data as SensorData);
            });
            //console.log('🢄🔍✅ Sensor listener setup complete, unlisten function:', typeof unlisten);
            return unlisten;
        } catch (error) {
            console.error('🢄🔍❌ Failed to setup sensor listener:', error);
            throw error;
        }
    }
} : null;

/*console.log('🢄🔍 environment:', JSON.stringify({
    TAURI,
    hasWindow,
    platformName,
    TAURI_MOBILE,
    TAURI_DESKTOP,
    hasTauriSensor: !!tauriSensor
}));*/

// Utility function to check if Tauri APIs are available
export function isTauriAvailable(): boolean {
    return TAURI;
}

// Utility function to check if sensor APIs are available
export function isSensorAvailable(): boolean {
    const available = TAURI_MOBILE && tauriSensor !== null;
    //console.log('🢄🔍 isSensorAvailable():', available, { TAURI_MOBILE, hasTauriSensor: !!tauriSensor });
    return available;
}

// Camera permission checking
export const tauriCamera = TAURI ? {
    checkCameraPermission: async (): Promise<boolean> => {
        try {
            const result = await invoke('plugin:hillview|check_camera_permission');
            return (result as { granted: boolean }).granted;
        } catch (err) {
            console.error('🢄📷 Failed to check camera permission:', err);
            return false;
        }
    },

    requestCameraPermission: async (): Promise<{ granted: boolean; error?: string }> => {
        try {
            const result = await invoke('plugin:hillview|request_camera_permission');
            return result as { granted: boolean; error?: string };
        } catch (err) {
            console.error('🢄📷 Failed to request camera permission:', err);
            return { granted: false, error: String(err) };
        }
    }
} : null;

// Utility function to check if camera permission can be checked via Tauri
export function isCameraPermissionCheckAvailable(): boolean {
    return TAURI && tauriCamera !== null;
}

// Geo tracking auto-export state
import { writable } from 'svelte/store';

export const autoExportEnabled = writable(false);
export const autoExportChecked = writable(false);

export async function fetchAutoExportState() {
    if (!TAURI) return;
    try {
        const result = await invoke('plugin:hillview|cmd', {
            command: 'geo_tracking_get_auto_export'
        }) as { enabled: boolean };
        autoExportEnabled.set(result.enabled);
    } catch (error) {
        console.error('Failed to get auto export setting:', error);
    }
    autoExportChecked.set(true);
}

export async function setAutoExportEnabled(enabled: boolean) {
    await invoke('plugin:hillview|cmd', {
        command: 'geo_tracking_set_auto_export',
        params: { enabled }
    });
    autoExportEnabled.set(enabled);
}
