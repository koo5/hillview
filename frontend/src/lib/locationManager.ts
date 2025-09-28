import { startPreciseLocationUpdates, stopPreciseLocationUpdates } from './preciseLocation';

export type LocationConsumer = 'user' | 'compass' | string;

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