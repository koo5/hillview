import type { PhotoData } from '../photoWorkerTypes';

export interface NavigationResult {
    photoInFront: PhotoData | null;
    photoToLeft: PhotoData | null;
    photoToRight: PhotoData | null;
    photosToLeft: PhotoData[];
    photosToRight: PhotoData[];
}

/**
 * Build navigation structure from sorted photos
 * @param sortedPhotos Photos sorted by angular distance (closest first)
 * @param allPhotos All photos in the current view (for circular navigation)
 * @param maxSidePhotos Maximum number of photos to include on each side (default: 7)
 */
export function buildNavigationStructure(
    sortedPhotos: PhotoData[], 
    allPhotos: PhotoData[],
    maxSidePhotos: number = 7
): NavigationResult {
    if (sortedPhotos.length === 0 || allPhotos.length === 0) {
        return {
            photoInFront: null,
            photoToLeft: null,
            photoToRight: null,
            photosToLeft: [],
            photosToRight: []
        };
    }
    
    const front = sortedPhotos[0];
    const idx = allPhotos.findIndex(p => p.id === front.id);
    
    if (idx === -1) {
        return {
            photoInFront: front,
            photoToLeft: null,
            photoToRight: null,
            photosToLeft: [],
            photosToRight: []
        };
    }
    
    const result: NavigationResult = {
        photoInFront: front,
        photoToLeft: null,
        photoToRight: null,
        photosToLeft: [],
        photosToRight: []
    };
    
    if (allPhotos.length > 1) {
        // Get immediate neighbors
        const leftIdx = (idx - 1 + allPhotos.length) % allPhotos.length;
        const rightIdx = (idx + 1) % allPhotos.length;
        
        result.photoToLeft = allPhotos[leftIdx];
        result.photoToRight = allPhotos[rightIdx];
        
        // Build arrays for left and right navigation
        const phsl: PhotoData[] = [];
        const phsr: PhotoData[] = [];
        
        const maxPhotos = Math.min(maxSidePhotos, Math.floor(allPhotos.length / 2));
        
        for (let i = 1; i <= maxPhotos; i++) {
            const leftPhotoIdx = (idx - i + allPhotos.length * 2) % allPhotos.length;
            const rightPhotoIdx = (idx + i) % allPhotos.length;
            
            const leftPhoto = allPhotos[leftPhotoIdx];
            const rightPhoto = allPhotos[rightPhotoIdx];
            
            if (leftPhoto && !phsl.includes(leftPhoto) && !phsr.includes(leftPhoto)) {
                phsl.push(leftPhoto);
            }
            if (rightPhoto && !phsl.includes(rightPhoto) && !phsr.includes(rightPhoto)) {
                phsr.push(rightPhoto);
            }
        }
        
        phsl.reverse();
        result.photosToLeft = phsl;
        result.photosToRight = phsr;
    }
    
    return result;
}