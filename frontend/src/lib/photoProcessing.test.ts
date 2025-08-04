import { describe, it, expect, beforeEach } from 'vitest';
import { LatLng } from 'leaflet';
import {
  filterPhotosByArea,
  calculatePhotoDistances,
  updatePhotoBearings,
  sortPhotosByAngularDistance,
  PhotoSpatialIndex,
  type Bounds,
} from './photoProcessing';
import type { PhotoData, PhotoWithBearing } from './types/photoTypes';

describe('photoProcessing', () => {
  const createTestPhoto = (id: string, lat: number, lng: number, bearing: number = 0): PhotoData => ({
    id,
    source_type: 'test',
    file: `${id}.jpg`,
    url: `${id}.jpg`,
    coord: new LatLng(lat, lng),
    bearing,
    altitude: 100,
  });

  const testPhotos: PhotoData[] = [
    createTestPhoto('photo1', 50.0617, 14.5146, 0),
    createTestPhoto('photo2', 50.0618, 14.5147, 90),
    createTestPhoto('photo3', 50.0619, 14.5148, 180),
    createTestPhoto('photo4', 50.0620, 14.5149, 270),
    createTestPhoto('photo5', 50.0621, 14.5150, 45),
  ];

  describe('filterPhotosByArea', () => {
    it('should filter photos within bounds', () => {
      const bounds: Bounds = {
        top_left: new LatLng(50.0620, 14.5146),
        bottom_right: new LatLng(50.0616, 14.5150),
      };

      const filtered = filterPhotosByArea(testPhotos, bounds, 0);

      // The bounds should include photos 2, 3, and 4
      expect(filtered).toHaveLength(3);
      expect(filtered.map(p => p.id)).toContain('photo2');
      expect(filtered.map(p => p.id)).toContain('photo3');
      expect(filtered.map(p => p.id)).toContain('photo4');
    });

    it('should include photos near edges with tolerance', () => {
      const bounds: Bounds = {
        top_left: new LatLng(50.0618, 14.5147),
        bottom_right: new LatLng(50.0617, 14.5148),
      };

      const withoutTolerance = filterPhotosByArea(testPhotos, bounds, 0);
      const withTolerance = filterPhotosByArea(testPhotos, bounds, 0.5);

      expect(withoutTolerance).toHaveLength(2);
      expect(withTolerance.length).toBeGreaterThan(withoutTolerance.length);
    });

    it('should handle empty photo array', () => {
      const bounds: Bounds = {
        top_left: new LatLng(50.1, 14.5),
        bottom_right: new LatLng(50.0, 14.6),
      };

      expect(filterPhotosByArea([], bounds)).toEqual([]);
    });
  });

  describe('calculatePhotoDistances', () => {
    it('should calculate distances from center point', () => {
      const center = { lat: 50.0617, lng: 14.5146 };
      const maxRange = 100; // 100 meters

      const result = calculatePhotoDistances(testPhotos, center, maxRange);

      expect(result[0].range_distance).toBe(0); // photo1 is at center
      expect(result[1].range_distance).toBeGreaterThan(0);
      expect(result[1].range_distance).toBeLessThan(100);
    });

    it('should filter out photos beyond max range', () => {
      const center = { lat: 50.0617, lng: 14.5146 };
      const maxRange = 50; // 50 meters

      const result = calculatePhotoDistances(testPhotos, center, maxRange);

      expect(result.length).toBeLessThan(testPhotos.length);
      expect(result.every(p => p.range_distance! <= maxRange)).toBe(true);
    });

    it('should handle large max range', () => {
      const center = { lat: 50.0617, lng: 14.5146 };
      const maxRange = 1000000; // 1000 km

      const result = calculatePhotoDistances(testPhotos, center, maxRange);

      expect(result).toHaveLength(testPhotos.length);
    });
  });

  describe('updatePhotoBearings', () => {
    it('should update all photos with bearing data', () => {
      const currentBearing = 45;
      const result = updatePhotoBearings(testPhotos, currentBearing);

      expect(result).toHaveLength(testPhotos.length);
      expect(result.every(p => 'abs_bearing_diff' in p)).toBe(true);
      expect(result.every(p => 'bearing_color' in p)).toBe(true);
    });

    it('should calculate correct bearing differences', () => {
      const currentBearing = 0;
      const result = updatePhotoBearings(testPhotos, currentBearing);

      expect(result[0].abs_bearing_diff).toBe(0); // 0 - 0
      expect(result[1].abs_bearing_diff).toBe(90); // 90 - 0
      expect(result[2].abs_bearing_diff).toBe(180); // 180 - 0
      expect(result[3].abs_bearing_diff).toBe(90); // 270 - 0 (abs value)
      expect(result[4].abs_bearing_diff).toBe(45); // 45 - 0
    });
  });

  describe('sortPhotosByAngularDistance', () => {
    it('should sort photos by angular distance', () => {
      const photosWithBearing = updatePhotoBearings(testPhotos, 0) as PhotoWithBearing[];
      const sorted = sortPhotosByAngularDistance(photosWithBearing, 0);

      expect(sorted[0].id).toBe('photo1'); // 0 degrees difference
      expect(sorted[1].id).toBe('photo5'); // 45 degrees difference
      expect(sorted[2].id).toBe('photo2'); // 90 degrees difference
      expect(sorted[3].id).toBe('photo4'); // 90 degrees difference (270 -> 90)
      expect(sorted[4].id).toBe('photo3'); // 180 degrees difference
    });

    it('should add angular_distance_abs property', () => {
      const photosWithBearing = updatePhotoBearings(testPhotos, 0) as PhotoWithBearing[];
      const sorted = sortPhotosByAngularDistance(photosWithBearing, 0);

      expect(sorted.every(p => typeof p.angular_distance_abs === 'number')).toBe(true);
    });
  });

  describe('PhotoSpatialIndex', () => {
    let index: PhotoSpatialIndex;

    beforeEach(() => {
      index = new PhotoSpatialIndex(0.001); // ~100m grid
    });

    it('should add and retrieve photos', () => {
      index.addPhoto('photo1', 50.0617, 14.5146);
      index.addPhoto('photo2', 50.0618, 14.5147);

      const bounds: Bounds = {
        top_left: new LatLng(50.0620, 14.5145),
        bottom_right: new LatLng(50.0615, 14.5150),
      };

      const results = index.getPhotoIdsInBounds(bounds);

      expect(results).toContain('photo1');
      expect(results).toContain('photo2');
    });

    it('should remove photos', () => {
      index.addPhoto('photo1', 50.0617, 14.5146);
      index.removePhoto('photo1');

      const bounds: Bounds = {
        top_left: new LatLng(50.0620, 14.5145),
        bottom_right: new LatLng(50.0615, 14.5150),
      };

      const results = index.getPhotoIdsInBounds(bounds);

      expect(results).not.toContain('photo1');
    });

    it('should handle large bounds gracefully', () => {
      index.addPhoto('photo1', 50.0617, 14.5146);

      const largeBounds: Bounds = {
        top_left: new LatLng(90, -180),
        bottom_right: new LatLng(-90, 180),
      };

      const results = index.getPhotoIdsInBounds(largeBounds);

      expect(results).toEqual([]); // Should return empty for too large bounds
    });

    it('should respect max results limit', () => {
      // Add many photos
      for (let i = 0; i < 100; i++) {
        index.addPhoto(`photo${i}`, 50.0617 + i * 0.0001, 14.5146 + i * 0.0001);
      }

      const bounds: Bounds = {
        top_left: new LatLng(50.1, 14.5),
        bottom_right: new LatLng(50.0, 14.6),
      };

      const results = index.getPhotoIdsInBounds(bounds, 10);

      expect(results.length).toBeLessThanOrEqual(10);
    });

    it('should track size correctly', () => {
      expect(index.size()).toBe(0);

      index.addPhoto('photo1', 50.0617, 14.5146);
      expect(index.size()).toBe(1);

      index.addPhoto('photo2', 50.0618, 14.5147);
      expect(index.size()).toBe(2);

      index.removePhoto('photo1');
      expect(index.size()).toBe(1);

      index.clear();
      expect(index.size()).toBe(0);
    });

    it('should not add duplicate photos to results', () => {
      // Add photo that spans multiple grid cells
      index.addPhoto('photo1', 50.0617, 14.5146);

      const bounds: Bounds = {
        top_left: new LatLng(50.1, 14.5),
        bottom_right: new LatLng(50.0, 14.6),
      };

      const results = index.getPhotoIdsInBounds(bounds);

      expect(results.filter(id => id === 'photo1')).toHaveLength(1);
    });
  });
});