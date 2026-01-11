import { TAURI_MOBILE } from './tauri';
import { addPluginListener, type PluginListener } from '@tauri-apps/api/core';
import { invoke } from '@tauri-apps/api/core';
import { updateGpsLocation, locationTracking, setLocationTracking } from './location.svelte';
import { get } from 'svelte/store';

// Unified GeolocationPosition interface
export interface GeolocationPosition {
    coords: {
        latitude: number;
        longitude: number;
        accuracy: number;
        altitude?: number;
        altitude_accuracy?: number;
        heading?: number;
        speed?: number;
    };
    timestamp: number;
}

// Interface for precise location data from Android plugin
interface PreciseLocationData {
    coords: {
        latitude: number;
        longitude: number;
        accuracy: number;
        altitude: number | null;
        altitude_accuracy: number | null;
        heading: number | null;
        speed: number | null;
    };
    timestamp: number;
    provider?: string;
    bearing_accuracy?: number;
    speed_accuracy?: number;
}

// Persistent listeners - set up once and kept active
let locationListener: PluginListener | null = null;  // Android plugin listener
let locationStoppedListener: PluginListener | null = null;  // Android location stopped listener
let webWatchId: number | null = null;                // Web geolocation watch ID
let listenersInitialized = false;

// Convert precise location data to GeolocationPosition format
function toGeolocationPosition(data: PreciseLocationData): GeolocationPosition {
    return {
        coords: {
            latitude: data.coords.latitude,
            longitude: data.coords.longitude,
            accuracy: data.coords.accuracy,
            altitude: data.coords.altitude ?? undefined,
            altitude_accuracy: data.coords.altitude_accuracy ?? undefined,
            heading: data.coords.heading ?? undefined,
            speed: data.coords.speed ?? undefined
        },
        timestamp: data.timestamp
    };
}

// Convert browser GeolocationPosition to our unified interface
function fromBrowserGeolocation(position: globalThis.GeolocationPosition): GeolocationPosition {
    return {
        coords: {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracy: position.coords.accuracy,
            altitude: position.coords.altitude ?? undefined,
            altitude_accuracy: position.coords.altitudeAccuracy ?? undefined,
            heading: position.coords.heading ?? undefined,
            speed: position.coords.speed ?? undefined
        },
        timestamp: position.timestamp
    };
}

// Handle location update for both platforms
function handleLocationUpdate(position: GeolocationPosition, source: string) {
    /*console.debug(`📍 Received "${source}" location update:`, JSON.stringify({
        lat: position.coords.latitude,
        lng: position.coords.longitude,
        accuracy: position.coords.accuracy
    }));*/

    // Only update GPS location if location tracking is enabled
    //if (get(locationTracking)) {
        updateGpsLocation(position);
    //} else {
        //console.debug('🢄📍 Ignoring location update - user-level GPS tracking is disabled');
    //}
}

// Initialize persistent listeners (similar to sensor onSensorData)
async function initializeLocationListeners(): Promise<void> {
    if (listenersInitialized) {
        console.debug('🢄📍 Location listeners already initialized');
        return;
    }

    if (TAURI_MOBILE) {
        try {
            console.log('🢄📍 Initializing persistent Android location listeners');

            // Set up the location update event listener (persistent)
            locationListener = await addPluginListener(
                'hillview',
                'location-update',
                (data: PreciseLocationData) => {
                    const position = toGeolocationPosition(data);
                    handleLocationUpdate(position, 'Android precise');

                    // Log extra precision data
                    if (data.bearing_accuracy !== undefined) {
                        //console.debug('🢄📍 Bearing accuracy:', data.bearing_accuracy, '°');
                    }
                    if (data.speed_accuracy !== undefined) {
                        //console.debug('🢄📍 Speed accuracy:', data.speed_accuracy, 'm/s');
                    }
                }
            );

            // Set up the location stopped event listener (persistent)
            locationStoppedListener = await addPluginListener(
                'hillview',
                'location-stopped',
                () => {
                    console.log('🢄📍 Android location service stopped - updating frontend state');
                    setLocationTracking(false);
                }
            );

            listenersInitialized = true;
            console.log('🢄📍 Android location listeners initialized successfully');
        } catch (error) {
            console.error('🢄📍 Failed to initialize Android location listeners:', error);
            throw error;
        }
    } else {
        // Web: Initialize browser geolocation (persistent)
        if (!navigator.geolocation) {
            throw new Error('Geolocation is not supported by this browser');
        }

        console.log('🢄📍 Initializing web geolocation listener');
        webWatchId = navigator.geolocation.watchPosition(
            (position) => {
                const geoPosition = fromBrowserGeolocation(position);
                handleLocationUpdate(geoPosition, 'web browser');
            },
            (error) => {
                console.error('🢄📍 Web geolocation error:', error);
                // Don't throw here to avoid stopping the watch
            },
            {
                enableHighAccuracy: true,
                timeout: 10000,
                maximumAge: 5000
            }
        );

        listenersInitialized = true;
        console.log('🢄📍 Web geolocation listener initialized successfully');
    }
}

// Check and request location permission via Tauri's permission system
async function ensureLocationPermission(): Promise<boolean> {
    console.log('🢄📍 Checking location permission via Tauri...');
    const permissionStatus = await invoke('plugin:hillview|check_tauri_permissions') as Record<string, string>;
    console.log('🢄📍 Permission status:', JSON.stringify(permissionStatus));

    if (permissionStatus?.location === 'Granted') {
        console.log('🢄📍 Location permission already granted');
        return true;
    }

    // Need to request permission
    console.log('🢄📍 Requesting location permission via Tauri...');
    const result = await invoke('plugin:hillview|request_tauri_permission', {
        permission: 'location'
    }) as string;
    console.log('🢄📍 Permission request result:', result);

    return result === 'Granted' || result === 'granted';
}

// Start location tracking (platform-aware)
export async function startPreciseLocationUpdates(): Promise<void> {
    // Initialize listeners if not already done
    await initializeLocationListeners();

    if (TAURI_MOBILE) {
        // First ensure we have location permission via Tauri's system
        const hasPermission = await ensureLocationPermission();
        if (!hasPermission) {
            throw new Error('Location permission denied');
        }

        console.log('🢄📍 Starting Android precise location service');
        await invoke('plugin:hillview|start_precise_location_listener');
        console.log('🢄📍 Android precise location service started successfully');
    } else {
        // Web: Browser geolocation is already active, nothing more to do
        console.log('🢄📍 Web geolocation already active');
    }
}

// Stop location tracking (platform-aware)
export async function stopPreciseLocationUpdates(): Promise<void> {
    console.log('🢄📍 Stopping location tracking');

    if (TAURI_MOBILE) {
        // Just stop the Android service - listeners remain active
        await invoke('plugin:hillview|stop_precise_location_listener');
        console.log('🢄📍 Android precise location service stopped');
    } else {
        // Web: For now, don't clear the watch to keep it persistent
        // In the future, we could add a flag to control whether web geolocation
        // should keep running in the background
        console.log('🢄📍 Web geolocation remains active (persistent mode)');
    }
}

// Check if listeners are initialized (persistent)
export function isPreciseLocationListenersInitialized(): boolean {
    return listenersInitialized;
}

// Add a function to get current position (useful for Map component's getCurrentPosition needs)
export async function getCurrentPosition(): Promise<GeolocationPosition> {
    if (TAURI_MOBILE) {
        // For Android, we don't have a direct getCurrentPosition in our plugin
        // This would need to be implemented in the plugin if needed
        throw new Error('getCurrentPosition not implemented for Android precise location');
    } else {
        // Web: Use browser geolocation API
        if (!navigator.geolocation) {
            throw new Error('Geolocation is not supported by this browser');
        }

        return new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    resolve(fromBrowserGeolocation(position));
                },
                (error) => {
                    reject(error);
                },
                {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 5000
                }
            );
        });
    }
}
