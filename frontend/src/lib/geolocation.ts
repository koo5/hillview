import { getCurrentPosition, watchPosition, clearWatch, checkPermissions, requestPermissions, type Position } from '@tauri-apps/plugin-geolocation';

// Check if we're running in Tauri
const isTauri = () => {
    return typeof window !== 'undefined' && '__TAURI__' in window;
};

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

export interface GeolocationError {
    code: number;
    message: string;
}

export interface PositionOptions {
    enableHighAccuracy?: boolean;
    timeout?: number;
    maximumAge?: number;
}

export const geolocation = {
    requestPermissions: async (): Promise<boolean> => {
        if (isTauri()) {
            try {
                const result = await requestPermissions();
                console.log('Geolocation permission result:', result);
                return result.location === 'granted' || result.location === 'prompt';
            } catch (error) {
                console.error('Failed to request geolocation permissions:', error);
                return false;
            }
        }
        // Browser API doesn't have explicit permission request
        return true;
    },
    
    checkPermissions: async (): Promise<boolean> => {
        if (isTauri()) {
            try {
                const result = await checkPermissions();
                console.log('Current geolocation permissions:', result);
                return result.location === 'granted';
            } catch (error) {
                console.error('Failed to check geolocation permissions:', error);
                return false;
            }
        }
        // Browser API doesn't have permission check
        return true;
    },
    
    getCurrentPosition: async (
        successCallback: (position: GeolocationPosition) => void,
        errorCallback?: (error: GeolocationError) => void,
        options?: PositionOptions
    ): Promise<void> => {
        if (isTauri()) {
            try {
                // Check and request permissions first
                const hasPermission = await geolocation.checkPermissions();
                if (!hasPermission) {
                    const granted = await geolocation.requestPermissions();
                    if (!granted) {
                        if (errorCallback) {
                            errorCallback({
                                code: 1, // PERMISSION_DENIED
                                message: 'Location permission denied'
                            });
                        }
                        return;
                    }
                }
                const position = await getCurrentPosition({
                    enableHighAccuracy: options?.enableHighAccuracy ?? true,
                    timeout: options?.timeout ?? 10000,
                    maximumAge: options?.maximumAge ?? 0
                } as any);
                
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
                // Check and request permissions first
                const hasPermission = await geolocation.checkPermissions();
                if (!hasPermission) {
                    const granted = await geolocation.requestPermissions();
                    if (!granted) {
                        if (errorCallback) {
                            errorCallback({
                                code: 1, // PERMISSION_DENIED
                                message: 'Location permission denied'
                            });
                        }
                        return -1;
                    }
                }
                const watchId = await watchPosition(
                    {
                        enableHighAccuracy: options?.enableHighAccuracy ?? true,
                        timeout: options?.timeout ?? 10000,
                        maximumAge: options?.maximumAge ?? 0
                    } as any,
                    (position: Position | null, error?: string) => {
                        if (!position) {
                            if (errorCallback && error) {
                                errorCallback({
                                    code: 1,
                                    message: error
                                });
                            }
                            return;
                        }
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