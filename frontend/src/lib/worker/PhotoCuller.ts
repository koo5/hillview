import type { PhotoData, Bounds } from '../photoWorkerTypes';
import { CullingGrid } from '../CullingGrid';
import { AngularRangeCuller, sortPhotosByBearing } from '../AngularRangeCuller';
import type { SourceId } from './SourcePhotosState';

/**
 * PhotoCuller - Spatial Photo Processing and Culling
 *
 * This class handles the core business logic of combining photos from multiple sources
 * and applying spatial culling algorithms to provide optimal photo distribution.
 *
 * Two-Stage Culling Process:
 * 1. Area Culling: Uses CullingGrid to ensure uniform spatial coverage across the viewport
 *    - Divides area into grid cells and selects best photos per cell
 *    - Prioritizes photos by source priority (device > hillview > mapillary)
 *    - Limits total photos to prevent frontend overload
 *
 * 2. Range Culling: Uses AngularRangeCuller for uniform angular coverage around a center point
 *    - Selects photos in a radius around the area center
 *    - Ensures even angular distribution for 360° coverage
 *    - Sorts by bearing for consistent navigation order (separate step after culling)
 *
 * State Management:
 * - Maintains CullingGrid instance and recreates when area bounds change
 * - Caches grid based on area version to avoid unnecessary recreation
 * - Stateless for angular culling (recreated each time)
 */

export class PhotoCuller {
    private cullingGrid: CullingGrid | null = null;
    private angularRangeCuller = new AngularRangeCuller();
    private lastAreaUpdateId = -1;

    cullPhotos(
        photosPerSource: Map<SourceId, PhotoData[]>,
        areaBounds: Bounds,
        areaUpdateId: number,
        rangeMeters: number,
        maxPhotosInArea: number,
        maxPhotosInRange: number
    ): { photosInArea: PhotoData[], photosInRange: PhotoData[] } {

        // Early return if no data
        if (!areaBounds || photosPerSource.size === 0) {
            console.log(`PhotoCuller: Early return - areaBounds:`, areaBounds, 'sources:', photosPerSource.size);
            return { photosInArea: [], photosInRange: [] };
        }

        console.log(`PhotoCuller: Processing area bounds:`, areaBounds);
        const photosInAreaPerSourceArray = Array.from(photosPerSource.entries());
        console.log(`PhotoCuller: Source photo counts:`,
            photosInAreaPerSourceArray.map(([sourceId, photos]) => `${sourceId}: ${photos.length}`).join(', '));

        // Create/update culling grid for current area
        if (!this.cullingGrid || areaUpdateId > this.lastAreaUpdateId) {
            this.cullingGrid = new CullingGrid(areaBounds);
            this.lastAreaUpdateId = areaUpdateId;
            console.log(`PhotoCuller: Created new culling grid for area bounds:`, areaBounds);
        }

        // Stage 1: Apply spatial culling for uniform screen coverage
        const photosInArea = this.cullingGrid.cullPhotos(photosPerSource, maxPhotosInArea);
        console.log(`PhotoCuller: After spatial culling - ${photosInArea.length} photos in area (max: ${maxPhotosInArea})`);

        // Calculate center for range filtering
        const center = this.calculateCenterFromBounds(areaBounds);

        // Stage 2: Apply angular range culling for uniform angular coverage
        const photosInRange = this.angularRangeCuller.cullPhotosInRange(
            photosInArea,
            center,
            rangeMeters,
            maxPhotosInRange
        );

        // Sort photos in range by bearing for consistent navigation order
        // Note: AngularRangeCuller selects for uniform coverage but doesn't sort
        sortPhotosByBearing(photosInRange);

        console.log(`PhotoCuller: Merged ${photosPerSource.size} sources → ${photosInArea.length} in area → ${photosInRange.length} in range with angular coverage`);

        return {
            photosInArea,
            photosInRange
        };
    }

    private calculateCenterFromBounds(bounds: Bounds): { lat: number; lng: number } {
        return {
            lat: (bounds.top_left.lat + bounds.bottom_right.lat) / 2,
            lng: (bounds.top_left.lng + bounds.bottom_right.lng) / 2
        };
    }

    clearCache(): void {
        this.cullingGrid = null;
        this.lastAreaUpdateId = -1;
        console.log('PhotoCuller: Cleared culling grid cache');
    }
}