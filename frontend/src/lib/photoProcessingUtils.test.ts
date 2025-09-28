import { describe, it, expect } from 'vitest';
import { LatLng } from 'leaflet';
import {
  calculateDistance,
  isPhotoInBounds,
  filterPhotosByArea
} from './workerUtils';
import type { Bounds } from './photoWorkerTypes';
import { CullingGrid } from './CullingGrid';
import { AngularRangeCuller } from './AngularRangeCuller';
import type { PhotoData, PhotoId } from './types/photoTypes';

describe('photoProcessingUtils', () => {
  const createTestPhoto = (id: PhotoId, lat: number, lng: number, bearing: number = 0): PhotoData => ({
    id,
    uid: `test-${id}`,
    source_type: 'test',
    file: `photo_${id}.jpg`,
    url: `https://example.com/photo_${id}.jpg`,
    coord: new LatLng(lat, lng),
    bearing,
    altitude: 0
  });

  describe('calculateDistance', () => {
    it('should calculate distance between two points', () => {
      // Distance between two points roughly 111km apart (1 degree latitude)
      const distance = calculateDistance(0, 0, 1, 0);
      expect(distance).toBeCloseTo(111320, -3); // Within 1000m
    });

    it('should return 0 for same point', () => {
      const distance = calculateDistance(50.123, 10.456, 50.123, 10.456);
      expect(distance).toBe(0);
    });
  });

  describe('CullingGrid', () => {
    const bounds = {
      top_left: { lat: 60, lng: 10 },
      bottom_right: { lat: 50, lng: 20 }
    };

    it('should cull photos for uniform screen coverage', () => {
      const cullingGrid = new CullingGrid(bounds);
      
      // Create many photos clustered in one area
      const source1Photos = Array.from({ length: 100 }, (_, i) => 
        createTestPhoto(`clustered_${i}`, 55 + (i % 10) * 0.01, 15 + (i % 10) * 0.01)
      );
      
      // Create fewer photos spread across the area
      const source2Photos = [
        createTestPhoto('spread_1', 52, 12),
        createTestPhoto('spread_2', 58, 18),
        createTestPhoto('spread_3', 54, 16)
      ];

      const photosPerSource = new Map([
        ['source1', source1Photos],
        ['source2', source2Photos]
      ]);

      const culled = cullingGrid.cullPhotos(photosPerSource, 20);
      
      expect(culled.length).toBeLessThanOrEqual(20);
      expect(culled.length).toBeGreaterThan(0);
      
      // Should include photos from both sources
      const source1Count = culled.filter(p => p.id.startsWith('clustered')).length;
      const source2Count = culled.filter(p => p.id.startsWith('spread')).length;
      expect(source1Count).toBeGreaterThan(0);
      expect(source2Count).toBeGreaterThan(0);
    });

    it('should return empty array for empty input', () => {
      const cullingGrid = new CullingGrid(bounds);
      const culled = cullingGrid.cullPhotos(new Map(), 10);
      expect(culled).toEqual([]);
    });

    it('should respect maxPhotos limit', () => {
      const cullingGrid = new CullingGrid(bounds);
      const photos = Array.from({ length: 50 }, (_, i) => 
        createTestPhoto(`photo_${i}`, 55, 15)
      );
      
      const photosPerSource = new Map([['source1', photos]]);
      const culled = cullingGrid.cullPhotos(photosPerSource, 10);
      
      expect(culled.length).toBeLessThanOrEqual(10);
    });
  });

  describe('AngularRangeCuller', () => {
    it('should cull photos for uniform angular coverage', () => {
      const culler = new AngularRangeCuller();
      const center = { lat: 55, lng: 15 };
      
      // Create photos with different bearings
      const photos = [
        createTestPhoto('north', 55.001, 15, 0),
        createTestPhoto('east', 55, 15.001, 90),
        createTestPhoto('south', 54.999, 15, 180),
        createTestPhoto('west', 55, 14.999, 270),
        createTestPhoto('northeast', 55.0007, 15.0007, 45)
      ];

      const culled = culler.cullPhotosInRange(photos, center, 1000, 4);
      
      expect(culled.length).toBeLessThanOrEqual(4);
      expect(culled.length).toBeGreaterThan(0);
      
      // Should include photos with range_distance
      culled.forEach(photo => {
        expect(photo.range_distance).toBeDefined();
        expect(photo.range_distance).toBeGreaterThanOrEqual(0);
      });
    });

    it('should filter by range distance', () => {
      const culler = new AngularRangeCuller();
      const center = { lat: 55, lng: 15 };
      
      // Create photos at different distances
      const photos = [
        createTestPhoto('close', 55.001, 15, 0),  // ~111m
        createTestPhoto('far', 55.01, 15, 0)     // ~1111m
      ];

      const culled = culler.cullPhotosInRange(photos, center, 500, 10);
      
      expect(culled.length).toBe(1);
      expect(culled[0].id).toBe('close');
    });

    it('should return empty for no photos in range', () => {
      const culler = new AngularRangeCuller();
      const center = { lat: 55, lng: 15 };
      
      const photos = [createTestPhoto('far', 56, 16, 0)]; // Very far
      const culled = culler.cullPhotosInRange(photos, center, 10, 10);
      
      expect(culled).toEqual([]);
    });
  });
});