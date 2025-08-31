import { writable, get } from 'svelte/store';
import type { PlaceholderPhoto } from './types/photoTypes';
import { sources } from './data.svelte';
import { createPlaceholderPhoto, type PlaceholderLocation } from './utils/placeholderUtils';

// Store for placeholder photos that need immediate display
export const placeholderPhotos = writable<PlaceholderPhoto[]>([]);

export class PlaceholderInjector {
    /**
     * Injects a placeholder photo directly into the photo display system,
     * bypassing normal filtering and processing
     */
    static injectPlaceholder(
        location: PlaceholderLocation,
        tempId: string
    ): void {
        const deviceSource = get(sources).find(s => s.id === 'device');
        if (!deviceSource || !deviceSource.enabled) {
            console.log('🢄Device source not enabled, skipping placeholder injection');
            return;
        }

        const placeholderPhoto = createPlaceholderPhoto(location, tempId, deviceSource);

        // Add to our placeholder store
        placeholderPhotos.update(photos => [...photos, placeholderPhoto]);

        console.log('🢄📍 Injected placeholder:', tempId, 'at', location);
    }

    /**
     * Removes a placeholder when the real photo is ready
     */
    static removePlaceholder(tempId: string): void {
        placeholderPhotos.update(photos => photos.filter(p => p.tempId !== tempId));
        console.log('🢄📍 Removed placeholder:', tempId);
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
        console.log('🢄📍 Cleared all placeholders');
    }
}

// Export singleton instance methods for convenience
export const injectPlaceholder = PlaceholderInjector.injectPlaceholder;
export const removePlaceholder = PlaceholderInjector.removePlaceholder;
export const clearPlaceholders = PlaceholderInjector.clearAll;
