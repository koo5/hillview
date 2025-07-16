import { derived } from 'svelte/store';
import { photos_in_area, bearing } from './data.svelte';
import { placeholderPhotos } from './placeholderInjector';
import type { PhotoData } from './types/photoTypes';
import { calculateBearingData } from './utils/bearingUtils';

/**
 * Combined store that merges photos_in_area with active placeholders
 * This provides immediate display of placeholders without waiting for the photo pipeline
 */
export const combinedPhotosInArea = derived(
    [photos_in_area, placeholderPhotos, bearing],
    ([$photos_in_area, $placeholderPhotos, $bearing]) => {
        // Create a map to track photo IDs and avoid duplicates
        const photoMap = new Map<string, PhotoData>();
        
        // Add all regular photos (they already have abs_bearing_diff)
        $photos_in_area.forEach(photo => {
            photoMap.set(photo.id, photo);
        });
        
        // Add placeholders with calculated abs_bearing_diff
        $placeholderPhotos.forEach(placeholder => {
            const bearingData = calculateBearingData(placeholder.bearing, $bearing);
            const photoWithBearing = {
                ...placeholder,
                ...bearingData
            };
            photoMap.set(placeholder.id, photoWithBearing);
        });
        
        // Convert back to array and sort by timestamp (newest first)
        const combined = Array.from(photoMap.values());
        combined.sort((a, b) => {
            const aTime = (a as any).timestamp || 0;
            const bTime = (b as any).timestamp || 0;
            return bTime - aTime;
        });
        
        return combined;
    }
);