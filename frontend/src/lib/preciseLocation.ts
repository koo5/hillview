import { TAURI_MOBILE } from './tauri';
import { addPluginListener, type PluginListener } from '@tauri-apps/api/core';
import { updateGpsLocation } from './location.svelte';
import type { GeolocationPosition } from './geolocation';

// Interface for precise location data from Android
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

let locationListener: PluginListener | null = null;

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

// Start listening for precise location updates
export async function startPreciseLocationUpdates(): Promise<void> {
    if (locationListener) {
        console.log('📍 Precise location listener already active');
        return;
    }

    try {
        console.log('📍 Starting precise location listener');
        
        locationListener = await addPluginListener(
            'hillview',
            'location-update',
            (data: PreciseLocationData) => {
                console.debug('📍 Received precise location update:', {
                    lat: data.coords.latitude,
                    lng: data.coords.longitude,
                    accuracy: data.coords.accuracy,
                    provider: data.provider
                });
                
                // Convert to GeolocationPosition and update the store
                const position = toGeolocationPosition(data);
                updateGpsLocation(position);
                
                // Log if we have extra precision data
                if (data.bearingAccuracy !== undefined) {
                    console.debug('📍 Bearing accuracy:', data.bearingAccuracy, '°');
                }
                if (data.speedAccuracy !== undefined) {
                    console.debug('📍 Speed accuracy:', data.speedAccuracy, 'm/s');
                }
            }
        );
        
        console.log('📍 Precise location listener started successfully');
    } catch (error) {
        console.error('📍 Failed to start precise location listener:', error);
    }
}

// Stop listening for precise location updates
export async function stopPreciseLocationUpdates(): Promise<void> {
    if (locationListener) {
        console.log('📍 Stopping precise location listener');
        try {
            await locationListener.unregister();
        } catch (error) {
            // Ignore error if remove_listener command doesn't exist
            // The listener will be cleaned up when the plugin is destroyed
            console.debug('📍 Could not unregister listener (expected on Android):', error);
        }
        locationListener = null;
    }
}

// Check if we're using precise location
export function isPreciseLocationActive(): boolean {
    return locationListener !== null;
}