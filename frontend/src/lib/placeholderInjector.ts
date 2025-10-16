import { writable, get } from 'svelte/store';
import type { PlaceholderPhoto } from './types/photoTypes';
import { sources } from './data.svelte';
import { createPlaceholderPhoto, type PlaceholderLocation } from './utils/placeholderUtils';
import { photosInArea, photosInRange } from './mapState';

// Store for placeholder photos that need immediate display
export const placeholderPhotos = writable<PlaceholderPhoto[]>([]);

export class PlaceholderInjector {
    /**
     * Injects a placeholder photo directly into the photo display system,
     * bypassing normal filtering and processing
     */
    static injectPlaceholder(
        location: PlaceholderLocation,
        sharedId: string
    ): void {
        const deviceSource = get(sources).find(s => s.id === 'device');
        if (!deviceSource) {
            console.log('🢄📍 ERROR: Device source not found, skipping placeholder injection');
            return;
        }

        const placeholderPhoto = createPlaceholderPhoto(location, sharedId, deviceSource);

        // Add to our placeholder store
        placeholderPhotos.update(photos => {
            const newPhotos = [...photos, placeholderPhoto];
            return newPhotos;
        });

        // Also add directly to map photo stores for immediate display
        if (deviceSource.enabled) {
			const withPlaceholders = embedPlaceholders(get(photosInArea), get(photosInRange), get(placeholderPhotos));
            photosInArea.set(withPlaceholders.photosInArea);
            photosInRange.set(withPlaceholders.photosInRange);
        }

        console.log('🢄📍 Injected placeholder:', sharedId, 'at', location);
    }

    /**
     * Removes a placeholder when the real photo is ready
     * Uses the photo ID (which is now the same as sharedId/tempId)
     */
    static removePlaceholder(photoId: string): void {
        placeholderPhotos.update(photos => photos.filter(p => p.id !== photoId && p.tempId !== photoId));
        console.log('🢄📍 Removed placeholder:', photoId);
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


export function embedPlaceholders(
	currentPhotosInArea: any[],
	currentPhotosInRange: any[],
	currentPlaceholders: PlaceholderPhoto[]
): { photosInArea: any[]; photosInRange: any[] } {
	return {
		photosInArea: [currentPhotosInArea, ...currentPlaceholders],
		photosInRange: [currentPhotosInRange, ...currentPlaceholders]
	};
}
