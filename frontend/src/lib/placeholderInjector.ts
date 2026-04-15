import { writable, get } from 'svelte/store';
import type { PlaceholderPhoto } from './types/photoTypes';
import { sources } from './data.svelte';
import { createPlaceholderPhoto, type PlaceholderLocation } from './utils/placeholderUtils';
import { photosInArea, photosInRange, spatialState, type Bounds } from './mapState';
import { isInBounds, getDistance } from './utils/distanceUtils';

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
			const spatial = get(spatialState);
			const withPlaceholders = embedPlaceholders(get(photosInArea), get(photosInRange), get(placeholderPhotos), spatial.bounds, spatial.center, spatial.range);
            photosInArea.set(withPlaceholders.photos_in_area);
            photosInRange.set(withPlaceholders.photos_in_range);
        }

        console.log('🢄📍 Injected placeholder:', sharedId, 'at', location);
    }

    /**
     * Removes a placeholder when the real photo is ready
     * Uses the photo ID (which is now the same as sharedId/temp_id)
     */
    static removePlaceholder(photoId: string): void {
        placeholderPhotos.update(photos => photos.filter(p => p.id !== photoId && p.temp_id !== photoId));
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


// Render placeholders only when they sit inside the current map view:
//   photos_in_area -> bounds check (on-screen)
//   photos_in_range -> bounds + range check (inside the navigation/gallery radius)
// Without this, a placeholder follows the user as an off-screen "ghost": the placeholder
// store is not cleared until the real device photo appears in a worker photosUpdate,
// which may never happen if the user doesn't return to the capture location.
export function embedPlaceholders(
	currentPhotosInArea: any[],
	currentPhotosInRange: any[],
	currentPlaceholders: PlaceholderPhoto[],
	bounds: Bounds | null,
	center: { lat: number; lng: number },
	range: number
): { photos_in_area: any[]; photos_in_range: any[] } {
	if (!bounds) {
		// Pre-mapReady: no spatial reference yet, include all placeholders defensively
		return {
			photos_in_area: [...currentPhotosInArea, ...currentPlaceholders],
			photos_in_range: [...currentPhotosInRange, ...currentPlaceholders]
		};
	}
	const inArea = currentPlaceholders.filter(p => isInBounds(p.coord, bounds));
	const inRange = inArea.filter(p => getDistance(p.coord, center) <= range);
	return {
		photos_in_area: [...currentPhotosInArea, ...inArea],
		photos_in_range: [...currentPhotosInRange, ...inRange]
	};
}
