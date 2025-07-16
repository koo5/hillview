import { writable, get } from 'svelte/store';
import type { PhotoData } from './sources';
import { sources } from './sources';
import { LatLng } from 'leaflet';

export interface PlaceholderPhoto extends PhotoData {
    isPlaceholder: true;
    tempId: string;
}

// Store for placeholder photos that need immediate display
export const placeholderPhotos = writable<PlaceholderPhoto[]>([]);

export class PlaceholderInjector {
    /**
     * Injects a placeholder photo directly into the photo display system,
     * bypassing normal filtering and processing
     */
    static injectPlaceholder(
        location: { latitude: number; longitude: number; altitude?: number | null; heading?: number | null; accuracy: number },
        tempId: string
    ): void {
        const deviceSource = get(sources).find(s => s.id === 'device');
        if (!deviceSource || !deviceSource.enabled) {
            console.warn('Device source not enabled, skipping placeholder injection');
            return;
        }

        const placeholderPhoto: PlaceholderPhoto = {
            id: tempId,
            source_type: 'device',
            file: 'placeholder.jpg',
            url: 'placeholder://arrow',
            coord: new LatLng(location.latitude, location.longitude),
            bearing: location.heading || 0,
            altitude: location.altitude || 0,
            source: deviceSource,
            isDevicePhoto: true,
            isPlaceholder: true,
            tempId: tempId,
            timestamp: Date.now(),
            accuracy: location.accuracy
        };

        // Add to our placeholder store
        placeholderPhotos.update(photos => [...photos, placeholderPhoto]);
        
        console.log('📍 Injected placeholder:', tempId, 'at', location);
    }

    /**
     * Removes a placeholder when the real photo is ready
     */
    static removePlaceholder(tempId: string): void {
        placeholderPhotos.update(photos => photos.filter(p => p.tempId !== tempId));
        console.log('📍 Removed placeholder:', tempId);
    }

    /**
     * Gets all active placeholders
     */
    static getActivePlaceholders(): PlaceholderPhoto[] {
        return get(placeholderPhotos);
    }

    /**
     * Clear all placeholders (e.g., when closing camera)
     */
    static clearAll(): void {
        placeholderPhotos.set([]);
        console.log('📍 Cleared all placeholders');
    }
}

// Export singleton instance methods for convenience
export const injectPlaceholder = PlaceholderInjector.injectPlaceholder;
export const removePlaceholder = PlaceholderInjector.removePlaceholder;
export const clearPlaceholders = PlaceholderInjector.clearAll;