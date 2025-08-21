import { TAURI_MOBILE } from './tauri';
import { addPluginListener, type PluginListener } from '@tauri-apps/api/core';
import { invoke } from '@tauri-apps/api/core';
import { updateGpsLocation, locationTracking } from './location.svelte';
import { get } from 'svelte/store';

// Unified GeolocationPosition interface
export interface GeolocationPosition {
    coords: {
        latitude: number;
        longitude: number;
        accuracy: number;
        altitude?: number;
        altitudeAccuracy?: number;
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
        altitudeAccuracy: number | null;
        heading: number | null;
        speed: number | null;
    };
    timestamp: number;
    provider?: string;
    bearingAccuracy?: number;
    speedAccuracy?: number;
}

// Tracking variables for both platforms
let locationListener: PluginListener | null = null;  // Android plugin listener
let webWatchId: number | null = null;                // Web geolocation watch ID

// Convert precise location data to GeolocationPosition format
function toGeolocationPosition(data: PreciseLocationData): GeolocationPosition {
    return {
        coords: {
            latitude: data.coords.latitude,
            longitude: data.coords.longitude,
            accuracy: data.coords.accuracy,
            altitude: data.coords.altitude ?? undefined,
            altitudeAccuracy: data.coords.altitudeAccuracy ?? undefined,
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
            altitudeAccuracy: position.coords.altitudeAccuracy ?? undefined,
            heading: position.coords.heading ?? undefined,
            speed: position.coords.speed ?? undefined
        },
        timestamp: position.timestamp
    };
}

// Handle location update for both platforms
function handleLocationUpdate(position: GeolocationPosition, source: string) {
    console.debug(`📍 Received ${source} location update:`, {
        lat: position.coords.latitude,
        lng: position.coords.longitude,
        accuracy: position.coords.accuracy
    });
    
    // Only update GPS location if location tracking is enabled
    if (get(locationTracking)) {
        updateGpsLocation(position);
    } else {
        console.debug('📍 Ignoring location update - GPS tracking is disabled');
    }
}

// Start location tracking (platform-aware)
export async function startPreciseLocationUpdates(): Promise<void> {
    // Check if already active
    if (locationListener || webWatchId !== null) {
        console.log('📍 Location tracking already active');
        return;
    }

    if (TAURI_MOBILE) {
        // Android: Use precise location plugin
        try {
            console.log('📍 Starting Android precise location listener');
            
            // Set up the event listener first
            locationListener = await addPluginListener(
                'hillview',
                'location-update',
                (data: PreciseLocationData) => {
                    const position = toGeolocationPosition(data);
                    handleLocationUpdate(position, 'Android precise');
                    
                    // Log extra precision data
                    if (data.bearingAccuracy !== undefined) {
                        console.debug('📍 Bearing accuracy:', data.bearingAccuracy, '°');
                    }
                    if (data.speedAccuracy !== undefined) {
                        console.debug('📍 Speed accuracy:', data.speedAccuracy, 'm/s');
                    }
                }
            );
            
            // Now start the precise location service on the Android side
            await invoke('plugin:hillview|start_precise_location_listener');
            
            console.log('📍 Android precise location listener started successfully');
        } catch (error) {
            console.error('📍 Failed to start Android precise location listener:', error);
            // Clean up the listener if starting the service failed
            if (locationListener) {
                try {
                    await locationListener.unregister();
                } catch (cleanupError) {
                    console.debug('📍 Failed to cleanup listener on error:', cleanupError);
                }
                locationListener = null;
            }
            throw error;
        }
    } else {
        // Web: Use browser geolocation API
        try {
            console.log('📍 Starting web geolocation');
            
            if (!navigator.geolocation) {
                throw new Error('Geolocation is not supported by this browser');
            }
            
            webWatchId = navigator.geolocation.watchPosition(
                (position) => {
                    const geoPosition = fromBrowserGeolocation(position);
                    handleLocationUpdate(geoPosition, 'web browser');
                },
                (error) => {
                    console.error('📍 Web geolocation error:', error);
                    // Don't throw here to avoid stopping the watch
                },
                {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 5000
                }
            );
            
            console.log('📍 Web geolocation started successfully');
        } catch (error) {
            console.error('📍 Failed to start web geolocation:', error);
            throw error;
        }
    }
}

// Stop location tracking (platform-aware)
export async function stopPreciseLocationUpdates(): Promise<void> {
    console.log('📍 Stopping location tracking');
    
    // Stop Android precise location listener
    if (locationListener) {
        try {
            // Stop the Android service
            if (TAURI_MOBILE) {
                await invoke('plugin:hillview|stop_precise_location_listener');
            }
            
            // Unregister the event listener
            await locationListener.unregister();
        } catch (error) {
            // Ignore error if remove_listener command doesn't exist
            console.debug('📍 Could not stop Android location service or unregister listener (expected):', error);
        }
        locationListener = null;
    }
    
    // Stop web geolocation watch
    if (webWatchId !== null) {
        if (navigator.geolocation) {
            navigator.geolocation.clearWatch(webWatchId);
        }
        webWatchId = null;
    }
}

// Check if location tracking is active (any platform)
export function isPreciseLocationActive(): boolean {
    return locationListener !== null || webWatchId !== null;
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