/**
 * Angular Range Culler - Ensures uniform angular coverage around user position
 *
 * Creates 36 angular buckets (10 degrees each, 0-360°) and uses round-robin
 * selection to ensure the user can "look" in all directions within range.
 *
 * Uses the photo's existing bearing property (camera direction) for bucketing.
 */

import { calculateDistance } from './workerUtils';
import { normalizeBearing } from './utils/bearingUtils';


export class AngularRangeCuller {
    private readonly ANGULAR_BUCKETS = 36; // 10 degrees each
    private readonly DEGREES_PER_BUCKET = 360 / this.ANGULAR_BUCKETS;

    constructor() {}

    /**
     * Cull photos for uniform angular coverage around center point
     */
    cullPhotosInRange<T extends { bearing: number; coord: { lat: number; lng: number }; id: string; uid: string }>(
        photosInArea: T[],
        center: { lat: number; lng: number },
        range: number,
        maxPhotos: number
    ): T[] {
        if (photosInArea.length === 0 || maxPhotos <= 0) {
            return [];
        }

        // Create angular buckets and filter photos within range
        const buckets: T[][] = new Array(this.ANGULAR_BUCKETS).fill(null).map(() => []);

        for (const photo of photosInArea) {
            const distance = calculateDistance(center.lat, center.lng, photo.coord.lat, photo.coord.lng);

            if (distance <= range) {
                const bucketIndex = this.getBucketIndex(photo.bearing);
                buckets[bucketIndex].push({
                    ...photo,
                    range_distance: distance
                } as T);
            }
        }

        // Remove empty buckets initially
        let activeBuckets = buckets.filter(bucket => bucket.length > 0);

        if (activeBuckets.length === 0) {
            return [];
        }

        // Round-robin: outer loop = rounds, inner loop = buckets
        const selectedPhotos: T[] = [];

        for (let round = 0; activeBuckets.length && selectedPhotos.length < maxPhotos; round++) {
            let bucketIndex = 0;

            while (bucketIndex < activeBuckets.length && selectedPhotos.length < maxPhotos) {
                // Remove exhausted bucket if no photo at this round
                if (!activeBuckets[bucketIndex][round]) {
                    activeBuckets[bucketIndex] = activeBuckets[activeBuckets.length - 1];
                    activeBuckets.pop();
                    // Don't increment bucketIndex - check the swapped bucket
                } else {
                    // Take photo and move to next bucket
                    selectedPhotos.push(activeBuckets[bucketIndex][round]);
                    bucketIndex++;
                }
            }
        }

        //console.log(`AngularRangeCuller: Culled ${photosInArea.length} area photos → ${selectedPhotos.length} range photos with angular coverage (${activeBuckets.length}/${this.ANGULAR_BUCKETS} angular sectors covered)`);

        return selectedPhotos;
    }


    private getBucketIndex(bearing: number): number {
        const normalizedBearing = normalizeBearing(bearing);
        return Math.floor(normalizedBearing / this.DEGREES_PER_BUCKET) % this.ANGULAR_BUCKETS;
    }

    /**
     * Get statistics about angular coverage
     */
    getAngularStats<T extends { bearing: number; coord: { lat: number; lng: number } }>(
        photosInArea: T[],
        culledPhotos: T[],
        center: { lat: number; lng: number },
        range: number
    ): {
        total_photos_in_range: number;
        selected_photos: number;
        covered_sectors: number;
        total_sectors: number;
        angular_coverage: { sector: number; start_angle: number; end_angle: number; photo_count: number }[];
    } {
        // Count photos per angular sector in result
        const sectorCounts = new Array(this.ANGULAR_BUCKETS).fill(0);

        for (const photo of culledPhotos) {
            const bucketIndex = this.getBucketIndex(photo.bearing);
            sectorCounts[bucketIndex]++;
        }

        // Count total photos in range (before culling)
        const totalPhotosInRange = photosInArea.filter(photo => {
            const distance = calculateDistance(center.lat, center.lng, photo.coord.lat, photo.coord.lng);
            return distance <= range;
        }).length;

        // Build angular coverage info
        const angularCoverage = sectorCounts.map((photoCount, sector) => ({
            sector,
            start_angle: sector * this.DEGREES_PER_BUCKET,
            end_angle: (sector + 1) * this.DEGREES_PER_BUCKET,
            photo_count: photoCount
        }));

        const coveredSectors = sectorCounts.filter(count => count > 0).length;

        return {
            total_photos_in_range: totalPhotosInRange,
            selected_photos: culledPhotos.length,
            covered_sectors: coveredSectors,
            total_sectors: this.ANGULAR_BUCKETS,
            angular_coverage: angularCoverage
        };
    }
}

export function sortPhotosByBearing(photos: { bearing: number; id: string; uid: string }[]) {
    photos.sort((a, b) => {
        if (a.bearing !== b.bearing) {
            return a.bearing - b.bearing;
        }
        return a.uid.localeCompare(b.uid); // Stable sort with UID as tiebreaker for cross-source consistency
    });
}
