/**
 * Simplified tests for AngularRangeCuller - Testing the actual cullPhotosInRange method
 */
import { describe, it, expect } from 'vitest';
import { AngularRangeCuller } from './AngularRangeCuller';
import type { PhotoData } from './photoWorkerTypes';

describe('AngularRangeCuller', () => {
    const center = { lat: 50.05, lng: 14.35 };

    const createPhotoData = (overrides: Partial<PhotoData> = {}): PhotoData => ({
        id: 'photo1',
        uid: 'test-photo1',
        source_type: 'device',
        file: 'test.jpg',
        url: 'file://test.jpg',
        coord: { lat: 50.05, lng: 14.35 },
        bearing: 0,
        altitude: 100,
        source: { id: 'device', name: 'Device', type: 'device', enabled: true },
        ...overrides
    });

    describe('Angular distribution', () => {
        it('should distribute photos across angular buckets within range', () => {
            const culler = new AngularRangeCuller();

            const photos = [
                createPhotoData({
                    id: 'photo1',
                    bearing: 0,
                    coord: { lat: 50.051, lng: 14.351 } // Close to center
                }),
                createPhotoData({
                    id: 'photo2',
                    bearing: 90,
                    coord: { lat: 50.052, lng: 14.352 } // Close to center, different bearing
                }),
                createPhotoData({
                    id: 'photo3',
                    bearing: 180,
                    coord: { lat: 50.053, lng: 14.353 } // Close to center, different bearing
                }),
                createPhotoData({
                    id: 'photo_far',
                    bearing: 270,
                    coord: { lat: 60.0, lng: 20.0 } // Far from center, should be filtered out
                }),
            ];

            const result = culler.cullPhotosInRange(photos, center, 1000, 10); // 1km range

            expect(result.length).toBeGreaterThan(0);
            expect(result.length).toBeLessThanOrEqual(3); // Should exclude the far photo

            // All results should be within range and have different bearings
            const bearings = result.map(p => p.bearing);
            const uniqueBearings = new Set(bearings);
            expect(uniqueBearings.size).toBe(result.length); // All different bearings
        });

        it('should respect maxPhotos limit', () => {
            const culler = new AngularRangeCuller();

            const photos = Array.from({ length: 100 }, (_, i) =>
                createPhotoData({
                    id: `photo${i}`,
                    bearing: i * 3.6, // Spread across 360 degrees
                    coord: { lat: center.lat + (i * 0.001), lng: center.lng + (i * 0.001) }
                })
            );

            const result = culler.cullPhotosInRange(photos, center, 1000, 5);

            expect(result).toHaveLength(5);
        });

        it('should filter photos outside range', () => {
            const culler = new AngularRangeCuller();

            const photos = [
                createPhotoData({
                    id: 'near',
                    coord: { lat: center.lat + 0.001, lng: center.lng + 0.001 } // ~100m away
                }),
                createPhotoData({
                    id: 'far',
                    coord: { lat: center.lat + 1.0, lng: center.lng + 1.0 } // ~100km away
                }),
            ];

            const result = culler.cullPhotosInRange(photos, center, 1000, 10); // 1km range

            expect(result).toHaveLength(1);
            expect(result[0].id).toBe('near');
        });

        it('should handle empty input gracefully', () => {
            const culler = new AngularRangeCuller();

            const result = culler.cullPhotosInRange([], center, 1000, 10);

            expect(result).toHaveLength(0);
        });

        it('should handle zero maxPhotos', () => {
            const culler = new AngularRangeCuller();

            const photos = [
                createPhotoData({
                    id: 'photo1',
                    coord: { lat: center.lat + 0.001, lng: center.lng + 0.001 }
                })
            ];

            const result = culler.cullPhotosInRange(photos, center, 1000, 0);

            expect(result).toHaveLength(0);
        });

        it('should add range_distance to photos', () => {
            const culler = new AngularRangeCuller();

            const photos = [
                createPhotoData({
                    id: 'photo1',
                    coord: { lat: center.lat + 0.001, lng: center.lng + 0.001 }
                })
            ];

            const result = culler.cullPhotosInRange(photos, center, 1000, 10);

            expect(result).toHaveLength(1);
            expect((result[0] as any).range_distance).toBeDefined();
            expect(typeof (result[0] as any).range_distance).toBe('number');
            expect((result[0] as any).range_distance).toBeGreaterThan(0);
        });
    });

    describe('Bucket optimization', () => {
        it('should handle multiple photos in same angular bucket', () => {
            const culler = new AngularRangeCuller();

            // Multiple photos with similar bearings (same bucket)
            const photos = [
                createPhotoData({
                    id: 'photo1',
                    bearing: 45,
                    coord: { lat: center.lat + 0.001, lng: center.lng + 0.001 }
                }),
                createPhotoData({
                    id: 'photo2',
                    bearing: 46,
                    coord: { lat: center.lat + 0.002, lng: center.lng + 0.002 }
                }),
                createPhotoData({
                    id: 'photo3',
                    bearing: 47,
                    coord: { lat: center.lat + 0.003, lng: center.lng + 0.003 }
                }),
            ];

            const result = culler.cullPhotosInRange(photos, center, 1000, 3);

            expect(result.length).toBeGreaterThan(0);
            expect(result.length).toBeLessThanOrEqual(3);
        });

        it('should normalize bearings correctly', () => {
            const culler = new AngularRangeCuller();

            const photos = [
                createPhotoData({
                    id: 'negative',
                    bearing: -10,
                    coord: { lat: center.lat + 0.001, lng: center.lng + 0.001 }
                }),
                createPhotoData({
                    id: 'over360',
                    bearing: 370,
                    coord: { lat: center.lat + 0.002, lng: center.lng + 0.002 }
                }),
                createPhotoData({
                    id: 'normal',
                    bearing: 180,
                    coord: { lat: center.lat + 0.003, lng: center.lng + 0.003 }
                }),
            ];

            const result = culler.cullPhotosInRange(photos, center, 1000, 3);

            expect(result.length).toBeGreaterThan(0);
            // Should handle all bearings without errors
            expect(result.every(p => p.id)).toBe(true);
        });
    });
});