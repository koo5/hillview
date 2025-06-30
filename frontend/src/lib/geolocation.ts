import { getCurrentPosition, watchPosition, clearWatch, type Position } from '@tauri-apps/plugin-geolocation';

// Check if we're running in Tauri
const isTauri = () => {
    return typeof window !== 'undefined' && '__TAURI__' in window;
};

export interface GeolocationPosition {
    coords: {
        latitude: number;
        longitude: number;
        accuracy: number;
        altitude?: number | null;
        altitudeAccuracy?: number | null;
        heading?: number | null;
        speed?: number | null;
    };
    timestamp: number;
}

export interface GeolocationError {
    code: number;
    message: string;
}

export const geolocation = {
    getCurrentPosition: async (
        successCallback: (position: GeolocationPosition) => void,
        errorCallback?: (error: GeolocationError) => void,
        options?: PositionOptions
    ): Promise<void> => {
        if (isTauri()) {
            try {
                const position = await getCurrentPosition({
                    enableHighAccuracy: options?.enableHighAccuracy,
                    timeout: options?.timeout,
                    maximumAge: options?.maximumAge
                });
                
                // Convert Tauri position to browser-like GeolocationPosition
                const geoPosition: GeolocationPosition = {
                    coords: {
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude,
                        accuracy: position.coords.accuracy,
                        altitude: position.coords.altitude,
                        altitudeAccuracy: position.coords.altitudeAccuracy,
                        heading: position.coords.heading,
                        speed: position.coords.speed
                    },
                    timestamp: position.timestamp
                };
                
                successCallback(geoPosition);
            } catch (error) {
                if (errorCallback) {
                    errorCallback({
                        code: 1, // PERMISSION_DENIED
                        message: error instanceof Error ? error.message : 'Unknown error'
                    });
                }
            }
        } else {
            // Fallback to browser API
            if (!navigator.geolocation) {
                if (errorCallback) {
                    errorCallback({
                        code: 2, // POSITION_UNAVAILABLE
                        message: 'Geolocation is not supported by your browser'
                    });
                }
                return;
            }
            
            navigator.geolocation.getCurrentPosition(
                successCallback,
                errorCallback,
                options
            );
        }
    },
    
    watchPosition: async (
        successCallback: (position: GeolocationPosition) => void,
        errorCallback?: (error: GeolocationError) => void,
        options?: PositionOptions
    ): Promise<number> => {
        if (isTauri()) {
            try {
                const watchId = await watchPosition(
                    {
                        enableHighAccuracy: options?.enableHighAccuracy,
                        timeout: options?.timeout,
                        maximumAge: options?.maximumAge
                    },
                    (position: Position) => {
                        // Convert Tauri position to browser-like GeolocationPosition
                        const geoPosition: GeolocationPosition = {
                            coords: {
                                latitude: position.coords.latitude,
                                longitude: position.coords.longitude,
                                accuracy: position.coords.accuracy,
                                altitude: position.coords.altitude,
                                altitudeAccuracy: position.coords.altitudeAccuracy,
                                heading: position.coords.heading,
                                speed: position.coords.speed
                            },
                            timestamp: position.timestamp
                        };
                        
                        successCallback(geoPosition);
                    }
                );
                
                return watchId;
            } catch (error) {
                if (errorCallback) {
                    errorCallback({
                        code: 1, // PERMISSION_DENIED
                        message: error instanceof Error ? error.message : 'Unknown error'
                    });
                }
                return -1;
            }
        } else {
            // Fallback to browser API
            if (!navigator.geolocation) {
                if (errorCallback) {
                    errorCallback({
                        code: 2, // POSITION_UNAVAILABLE
                        message: 'Geolocation is not supported by your browser'
                    });
                }
                return -1;
            }
            
            return navigator.geolocation.watchPosition(
                successCallback,
                errorCallback,
                options
            );
        }
    },
    
    clearWatch: async (watchId: number): Promise<void> => {
        if (isTauri()) {
            await clearWatch(watchId);
        } else if (navigator.geolocation) {
            navigator.geolocation.clearWatch(watchId);
        }
    }
};