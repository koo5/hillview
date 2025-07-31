import { derived } from 'svelte/store';
import { photosInArea, visualState } from './mapState';
import { placeholderPhotos } from './placeholderInjector';
import type { PhotoData } from './types/photoTypes';
import { calculateBearingData } from './utils/bearingUtils';

/**
 * Combined store that merges photos_in_area with active placeholders
 * This provides immediate display of placeholders without waiting for the photo pipeline
 */
export const combinedPhotosInArea = derived(
    [photosInArea, placeholderPhotos, visualState],
    ([$photosInArea, $placeholderPhotos, $visualState]) => {
        // Create a map to track photo IDs and avoid duplicates
        const photoMap = new Map<string, PhotoData>();
        
        // Add all regular photos (they already have abs_bearing_diff)
        $photosInArea.forEach(photo => {
            photoMap.set(photo.id, photo);
        });
        
        // Add placeholders with calculated abs_bearing_diff
        $placeholderPhotos.forEach(placeholder => {
            const bearingData = calculateBearingData(placeholder.bearing, $visualState.bearing);
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