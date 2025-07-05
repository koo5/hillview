import { writable, derived, get } from 'svelte/store';

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
    absolute: boolean;       // Whether values are absolute or relative
}

// Store for compass/magnetometer data
export const compassData = writable<CompassData | null>(null);

// Store for device orientation (gyroscope/accelerometer)
export const deviceOrientation = writable<DeviceOrientation | null>(null);

// Store for compass availability
export const compassAvailable = writable<boolean>(false);

// Store for compass permission status
export const compassPermission = writable<'granted' | 'denied' | 'prompt' | null>(null);

// Derived store for best available heading (fused from multiple sources)
export const fusedHeading = derived(
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
        return null;
    }
);

let compassWatchId: number | null = null;
let orientationHandler: ((event: DeviceOrientationEvent) => void) | null = null;

// Check if compass/orientation APIs are available
export function checkCompassAvailability(): boolean {
    const available = 'DeviceOrientationEvent' in window;
    compassAvailable.set(available);
    return available;
}

// Request compass permissions (iOS 13+ requires this)
export async function requestCompassPermission(): Promise<boolean> {
    if (typeof (DeviceOrientationEvent as any).requestPermission === 'function') {
        try {
            const permission = await (DeviceOrientationEvent as any).requestPermission();
            compassPermission.set(permission);
            return permission === 'granted';
        } catch (error) {
            console.error('Error requesting compass permission:', error);
            compassPermission.set('denied');
            return false;
        }
    } else {
        // No permission needed on this platform
        compassPermission.set('granted');
        return true;
    }
}

// Start watching compass/orientation
export async function startCompassWatch(): Promise<boolean> {
    if (!checkCompassAvailability()) {
        console.warn('Device orientation API not available');
        return false;
    }

    // Request permission if needed
    const hasPermission = await requestCompassPermission();
    if (!hasPermission) {
        console.warn('Compass permission denied');
        return false;
    }

    // Stop any existing watch
    stopCompassWatch();

    // Set up orientation handler
    orientationHandler = (event: DeviceOrientationEvent) => {
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
        
        // Log every ~10th update to avoid console spam
        if (Math.random() < 0.1) {
            console.log('Compass update:', {
                magnetic: data.magneticHeading?.toFixed(1),
                true: data.trueHeading?.toFixed(1),
                accuracy: data.headingAccuracy?.toFixed(1)
            });
        }
    };

    window.addEventListener('deviceorientation', orientationHandler);
    
    // For iOS devices, also listen to the absolute orientation event
    if ('ondeviceorientationabsolute' in window) {
        window.addEventListener('deviceorientationabsolute', orientationHandler as any);
    }

    return true;
}

// Stop watching compass/orientation
export function stopCompassWatch() {
    if (orientationHandler) {
        window.removeEventListener('deviceorientation', orientationHandler);
        if ('ondeviceorientationabsolute' in window) {
            window.removeEventListener('deviceorientationabsolute', orientationHandler as any);
        }
        orientationHandler = null;
    }
    
    compassData.set(null);
    deviceOrientation.set(null);
}

// Normalize heading to 0-360 range
function normalizeHeading(heading: number): number {
    heading = heading % 360;
    return heading < 0 ? heading + 360 : heading;
}

// Calculate heading difference (shortest angular distance)
export function headingDifference(heading1: number, heading2: number): number {
    const diff = normalizeHeading(heading1 - heading2);
    return diff > 180 ? diff - 360 : diff;
}

// Smooth heading changes using a simple moving average
class HeadingSmoother {
    private history: number[] = [];
    private maxSize: number;

    constructor(windowSize: number = 5) {
        this.maxSize = windowSize;
    }

    addHeading(heading: number): number {
        this.history.push(heading);
        if (this.history.length > this.maxSize) {
            this.history.shift();
        }

        // Use vector averaging for circular values
        let sinSum = 0;
        let cosSum = 0;
        
        for (const h of this.history) {
            const rad = (h * Math.PI) / 180;
            sinSum += Math.sin(rad);
            cosSum += Math.cos(rad);
        }

        const avgRad = Math.atan2(sinSum, cosSum);
        const avgDeg = (avgRad * 180) / Math.PI;
        
        return normalizeHeading(avgDeg);
    }

    reset() {
        this.history = [];
    }
}

export const headingSmoother = new HeadingSmoother();

// Extended TypeScript definitions for compass events
declare global {
    interface DeviceOrientationEvent {
        webkitCompassHeading?: number;
        webkitCompassAccuracy?: number;
        compassHeading?: number;
    }
}