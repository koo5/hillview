import { startPreciseLocationUpdates, stopPreciseLocationUpdates } from './preciseLocation';
import {locationTracking, setLocationError, setLocationTracking, updateGpsLocation} from "$lib/location.svelte";
import { writable } from 'svelte/store';
import { get } from 'svelte/store';

export type LocationConsumer = 'user' | 'compass' | string;
export let locationTrackingLoading = writable<boolean>(false);

class LocationReferenceManager {
    private consumers = new Set<LocationConsumer>();
    private isServiceRunning = false;

    /**
     * Request location service for a specific consumer
     * Only starts the service if this is the first consumer
     */
    async requestLocation(consumer: LocationConsumer): Promise<void> {
        console.log(`🢄📍🔢 LocationManager: ${consumer} requesting location service`);

        const wasEmpty = this.consumers.size === 0;
        this.consumers.add(consumer);

        console.log(`🢄📍🔢 Active consumers: ${Array.from(this.consumers).join(', ')}`);

        if (wasEmpty && !this.isServiceRunning) {
            console.log(`🢄📍🔢 Starting location service (first consumer: ${consumer})`);
            try {
                await startPreciseLocationUpdates();
                this.isServiceRunning = true;
                console.log(`🢄📍🔢 ✅ Location service started successfully`);
            } catch (error) {
                console.error(`🢄📍🔢 ❌ Failed to start location service:`, error);
                // Remove the consumer since we failed to start the service
                this.consumers.delete(consumer);
                throw error;
            }
        } else if (this.consumers.size > 0 && this.isServiceRunning) {
            console.log(`🢄📍🔢 Location service already running, added ${consumer} to consumers`);
        }
    }

    /**
     * Release location service for a specific consumer
     * Only stops the service when no consumers remain
     */
    async releaseLocation(consumer: LocationConsumer): Promise<void> {
        console.log(`🢄📍🔢 LocationManager: ${consumer} releasing location service`);

        const hadConsumer = this.consumers.has(consumer);
        this.consumers.delete(consumer);

        if (!hadConsumer) {
            console.log(`🢄📍🔢 ⚠️ Consumer ${consumer} was not actively using location service`);
        }

        console.log(`🢄📍🔢 Active consumers: ${Array.from(this.consumers).join(', ') || 'none'}`);

        if (this.consumers.size === 0 && this.isServiceRunning) {
            console.log(`🢄📍🔢 No consumers left, stopping location service`);
            try {
                await stopPreciseLocationUpdates();
                this.isServiceRunning = false;
                console.log(`🢄📍🔢 ✅ Location service stopped successfully`);
            } catch (error) {
                console.error(`🢄📍🔢 ❌ Failed to stop location service:`, error);
                // Still mark as stopped since we tried
                this.isServiceRunning = false;
            }
        } else if (this.consumers.size > 0) {
            console.log(`🢄📍🔢 Location service still needed by: ${Array.from(this.consumers).join(', ')}`);
        }
    }

    /**
     * Check if a specific consumer is currently using the location service
     */
    isConsumerActive(consumer: LocationConsumer): boolean {
        return this.consumers.has(consumer);
    }

    /**
     * Get all active consumers
     */
    getActiveConsumers(): LocationConsumer[] {
        return Array.from(this.consumers);
    }

    /**
     * Get the current state of the location service
     */
    getServiceState(): { isRunning: boolean; consumerCount: number; consumers: LocationConsumer[] } {
        return {
            isRunning: this.isServiceRunning,
            consumerCount: this.consumers.size,
            consumers: this.getActiveConsumers()
        };
    }

    /**
     * Reset all consumers and stop the service
     * This should be called on page load to avoid stale references
     */
    async reset(): Promise<void> {
        console.log(`🢄📍🔢 LocationManager: Resetting (clearing ${this.consumers.size} stale consumers)`);

        const hadConsumers = this.consumers.size > 0;
        const wasRunning = this.isServiceRunning;

        // Clear all consumers
        this.consumers.clear();

        // Stop service if it was running
        if (wasRunning) {
            console.log(`🢄📍🔢 Stopping location service during reset`);
            try {
                await stopPreciseLocationUpdates();
                console.log(`🢄📍🔢 ✅ Location service stopped during reset`);
            } catch (error) {
                console.error(`🢄📍🔢 ❌ Failed to stop location service during reset:`, error);
            }
        }

        this.isServiceRunning = false;

        if (hadConsumers || wasRunning) {
            console.log(`🢄📍🔢 ✅ Reset complete - cleared stale state`);
        } else {
            console.log(`🢄📍🔢 Reset complete - no stale state found`);
        }
    }

    /**
     * Force release a specific consumer without stopping the service
     * Useful for cleanup when a consumer is destroyed unexpectedly
     */
    forceReleaseConsumer(consumer: LocationConsumer): void {
        const had = this.consumers.has(consumer);
        this.consumers.delete(consumer);

        if (had) {
            console.log(`🢄📍🔢 Force released consumer: ${consumer}`);
            console.log(`🢄📍🔢 Remaining consumers: ${Array.from(this.consumers).join(', ') || 'none'}`);
        }
    }
}

// Export a singleton instance
export const locationManager = new LocationReferenceManager();

// Auto-reset on module load to clear any stale state
// This handles page refreshes and app restarts
if (typeof window !== 'undefined') {
    // Run reset on next tick to ensure all modules are loaded
    setTimeout(async () => {
        try {
            await locationManager.reset();
        } catch (error) {
            console.error('🢄📍🔢 Failed to reset location manager on page load:', error);
        }
    }, 0);
}


    // Start tracking user location
export    async function startLocationTracking() {
        locationTrackingLoading.set(true);

        try {
            console.log("📍 Map.svelte Starting location tracking");
            await locationManager.requestLocation('user');

            locationTrackingLoading.set(false);
            console.log("📍 Location tracking started successfully");

        } catch (error: any) {
            console.error("📍 Error starting location tracking:", error);
            setLocationError(error?.message || "Unknown error");

            let errorMessage = "Unable to get your location: ";
            if (error?.name === 'GeolocationPositionError' || error?.code) {
                switch(error.code) {
                    case 1:
                        errorMessage += "Permission denied. Please allow location access.";
                        break;
                    case 2:
                        errorMessage += "Position unavailable. Please check if location services are enabled.";
                        break;
                    case 3:
                        errorMessage += "Request timed out.";
                        break;
                    default:
                        errorMessage += error?.message || "Unknown error";
                }
            } else {
                errorMessage += error?.message || "Unknown error";
            }

            alert(errorMessage);
            setLocationTracking(false);
            locationTrackingLoading.set(false);
        }
    }

    // Stop tracking user location
export    async function stopLocationTracking() {
        locationTrackingLoading.set(false);

        try {
            console.log("📍 Stopping location tracking");
            await locationManager.releaseLocation('user');
        } catch (error) {
            console.error("📍 Error stopping location tracking:", error);
        }

        // Clear the location data when stopping
        updateGpsLocation(null);
        setLocationError(null);
    }

    // Export location tracking functions for use by parent
    export function enableLocationTracking() {
        if (!get(locationTracking)) {
            setLocationTracking(true);
            startLocationTracking();
        }
    }

    export function disableLocationTracking() {
        if (get(locationTracking)) {
            setLocationTracking(false);
            stopLocationTracking();
        }
    }
