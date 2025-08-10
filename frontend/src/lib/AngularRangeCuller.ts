/**
 * Angular Range Culler - Ensures uniform angular coverage around user position
 * 
 * Creates 36 angular buckets (10 degrees each, 0-360°) and uses round-robin
 * selection to ensure the user can "look" in all directions within range.
 * 
 * Uses the photo's existing bearing property (camera direction) for bucketing.
 */

import type { PhotoData } from './photoWorkerTypes';
import { calculateDistance } from './photoProcessingUtils';

interface AngularBucket {
    photos: PhotoData[];
    nextIndex: number; // For round-robin within bucket
}

export class AngularRangeCuller {
    private readonly ANGULAR_BUCKETS = 36; // 10 degrees each
    private readonly DEGREES_PER_BUCKET = 360 / this.ANGULAR_BUCKETS;

    constructor() {}

    /**
     * Cull photos for uniform angular coverage around center point
     */
    cullPhotosInRange(
        photosInArea: PhotoData[], 
        center: { lat: number; lng: number }, 
        range: number, 
        maxPhotos: number
    ): PhotoData[] {
        if (photosInArea.length === 0 || maxPhotos <= 0) {
            return [];
        }

        // Create angular buckets
        const angularBuckets = this.createAngularBuckets();
        
        // Distribute photos into angular buckets (only those within range)
        for (const photo of photosInArea) {
            const distance = calculateDistance(center.lat, center.lng, photo.coord.lat, photo.coord.lng);
            
            if (distance <= range) {
                const bucketIndex = this.getBucketIndex(photo.bearing);
                
                angularBuckets[bucketIndex].photos.push({
                    ...photo,
                    range_distance: distance
                });
            }
        }

        // Get non-empty buckets for round-robin
        const nonEmptyBuckets = angularBuckets.filter(bucket => bucket.photos.length > 0);
        
        if (nonEmptyBuckets.length === 0) {
            return [];
        }

        // Round-robin selection across angular buckets
        const selectedPhotos: PhotoData[] = [];
        let bucketIndex = 0;

        while (selectedPhotos.length < maxPhotos) {
            let foundPhoto = false;

            // Try each bucket in round-robin fashion
            for (let i = 0; i < nonEmptyBuckets.length && selectedPhotos.length < maxPhotos; i++) {
                const currentBucketIndex = (bucketIndex + i) % nonEmptyBuckets.length;
                const bucket = nonEmptyBuckets[currentBucketIndex];

                // If this bucket has photos available
                if (bucket.nextIndex < bucket.photos.length) {
                    const photo = bucket.photos[bucket.nextIndex];
                    bucket.nextIndex++;
                    selectedPhotos.push(photo);
                    foundPhoto = true;
                }
            }

            // Move to next bucket for next iteration
            bucketIndex = (bucketIndex + 1) % nonEmptyBuckets.length;

            // If no bucket produced a photo in a full round, we're done
            if (!foundPhoto) {
                break;
            }
        }

        console.log(`AngularRangeCuller: Culled ${photosInArea.length} area photos → ${selectedPhotos.length} range photos with angular coverage (${nonEmptyBuckets.length}/${this.ANGULAR_BUCKETS} angular sectors covered)`);
        
        return selectedPhotos;
    }

    private createAngularBuckets(): AngularBucket[] {
        return new Array(this.ANGULAR_BUCKETS).fill(null).map(() => ({
            photos: [],
            nextIndex: 0
        }));
    }

    private getBucketIndex(bearing: number): number {
        // Normalize bearing to 0-360 range
        const normalizedBearing = ((bearing % 360) + 360) % 360;
        return Math.floor(normalizedBearing / this.DEGREES_PER_BUCKET) % this.ANGULAR_BUCKETS;
    }

    /**
     * Get statistics about angular coverage
     */
    getAngularStats(
        photosInArea: PhotoData[], 
        culledPhotos: PhotoData[], 
        center: { lat: number; lng: number }, 
        range: number
    ): {
        totalPhotosInRange: number;
        selectedPhotos: number;
        coveredSectors: number;
        totalSectors: number;
        angularCoverage: { sector: number; startAngle: number; endAngle: number; photoCount: number }[];
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
            startAngle: sector * this.DEGREES_PER_BUCKET,
            endAngle: (sector + 1) * this.DEGREES_PER_BUCKET,
            photoCount
        }));

        const coveredSectors = sectorCounts.filter(count => count > 0).length;

        return {
            totalPhotosInRange,
            selectedPhotos: culledPhotos.length,
            coveredSectors,
            totalSectors: this.ANGULAR_BUCKETS,
            angularCoverage
        };
    }
}