import { describe, it, expect, beforeEach } from 'vitest';
import { LatLng } from 'leaflet';
import {
  calculateDistance,
  isPhotoInBounds,
  filterPhotosByArea,
  calculatePhotoDistances,
  normalizeBearing,
  calculateBearingDifference,
  getBearingColor,
  updatePhotoBearings,
  calculateAngularDistance,
  sortPhotosByAngularDistance,
  PhotoSpatialIndex,
  type Bounds
} from './photoProcessingUtils';
import type { PhotoData, PhotoWithBearing, PhotoId } from './types/photoTypes';

describe('photoProcessingUtils', () => {
  const createTestPhoto = (id: PhotoId, lat: number, lng: number, bearing: number = 0): PhotoData => ({
    id,
    source_type: 'test',
    file: `${id}.jpg`,
    url: `http://example.com/${id}.jpg`,
    coord: new LatLng(lat, lng),
    bearing,
    altitude: 0,
  });

  const testPhotos: PhotoData[] = [
    createTestPhoto('photo1', 50.0617, 14.5146, 90),  // Prague center
    createTestPhoto('photo2', 50.0627, 14.5156, 180), // Slightly north-east
    createTestPhoto('photo3', 50.0607, 14.5136, 270), // Slightly south-west
    createTestPhoto('photo4', 50.0637, 14.5166, 0),   // Further north-east
    createTestPhoto('photo5', 50.0597, 14.5126, 45),  // Further south-west
  ];

  describe('calculateDistance', () => {
    it('should calculate distance between two points', () => {
      const distance = calculateDistance(50.0617, 14.5146, 50.0627, 14.5156);
      expect(distance).toBeGreaterThan(0);
      expect(distance).toBeLessThan(200); // Should be less than 200m for nearby points
    });

    it('should return 0 for identical points', () => {
      const distance = calculateDistance(50.0617, 14.5146, 50.0617, 14.5146);
      expect(distance).toBeCloseTo(0, 2);
    });
  });

  describe('isPhotoInBounds', () => {
    const bounds: Bounds = {
      top_left: new LatLng(50.0640, 14.5140),
      bottom_right: new LatLng(50.0600, 14.5180)
    };

    it('should identify photos within bounds', () => {
      const photoInBounds = createTestPhoto('inside', 50.0620, 14.5160);
      const photoOutside = createTestPhoto('outside', 50.0650, 14.5200);

      expect(isPhotoInBounds(photoInBounds, bounds)).toBe(true);
      expect(isPhotoInBounds(photoOutside, bounds)).toBe(false);
    });

    it('should handle tolerance correctly', () => {
      const photoNearEdge = createTestPhoto('edge', 50.0641, 14.5160);
      
      expect(isPhotoInBounds(photoNearEdge, bounds, 0)).toBe(false);
      expect(isPhotoInBounds(photoNearEdge, bounds, 0.002)).toBe(true);
    });
  });

  describe('filterPhotosByArea', () => {
    const bounds: Bounds = {
      top_left: new LatLng(50.0640, 14.5140),
      bottom_right: new LatLng(50.0600, 14.5180)
    };

    it('should filter photos by area bounds', () => {
      const filtered = filterPhotosByArea(testPhotos, bounds, 0);

      // Should include photos 1, 2, 3 which are within bounds
      expect(filtered.length).toBeGreaterThan(0);
      expect(filtered.length).toBeLessThan(testPhotos.length);
      expect(filtered.some(p => p.id === 'photo1')).toBe(true);
    });

    it('should include photos near edges with tolerance', () => {
      const tightBounds: Bounds = {
        top_left: new LatLng(50.0625, 14.5150),
        bottom_right: new LatLng(50.0615, 14.5155)
      };

      const withoutTolerance = filterPhotosByArea(testPhotos, tightBounds, 0);
      const withTolerance = filterPhotosByArea(testPhotos, tightBounds, 0.002);

      expect(withTolerance.length).toBeGreaterThanOrEqual(withoutTolerance.length);
    });

    it('should return empty array for empty input', () => {
      expect(filterPhotosByArea([], bounds, 0)).toEqual([]);
    });
  });

  describe('calculatePhotoDistances', () => {
    const center = { lat: 50.0617, lng: 14.5146 };

    it('should calculate distances and filter by range', () => {
      const maxRange = 100; // 100 meters
      const result = calculatePhotoDistances(testPhotos, center, maxRange);

      expect(result.length).toBeLessThan(testPhotos.length);
      expect(result.every((p: PhotoData) => p.range_distance! <= maxRange)).toBe(true);
    });

    it('should handle large max range', () => {
      const maxRange = 10000; // 10km
      const result = calculatePhotoDistances(testPhotos, center, maxRange);

      expect(result).toHaveLength(testPhotos.length);
      expect(result.every((p: PhotoData) => typeof p.range_distance === 'number')).toBe(true);
    });
  });

  describe('bearing utilities', () => {
    describe('normalizeBearing', () => {
      it('should normalize bearings to 0-360 range', () => {
        expect(normalizeBearing(0)).toBe(0);
        expect(normalizeBearing(360)).toBe(0);
        expect(normalizeBearing(370)).toBe(10);
        expect(normalizeBearing(-10)).toBe(350);
        expect(normalizeBearing(720)).toBe(0);
      });
    });

    describe('calculateBearingDifference', () => {
      it('should calculate correct bearing differences', () => {
        expect(calculateBearingDifference(0, 90)).toBe(90);
        expect(calculateBearingDifference(350, 10)).toBe(20);
        expect(calculateBearingDifference(180, 180)).toBe(0);
        expect(calculateBearingDifference(0, 270)).toBe(90);
      });
    });

    describe('getBearingColor', () => {
      it('should return correct colors for bearing differences', () => {
        expect(getBearingColor(10)).toBe('green');
        expect(getBearingColor(30)).toBe('yellow');
        expect(getBearingColor(60)).toBe('orange');
        expect(getBearingColor(120)).toBe('red');
      });
    });

    describe('updatePhotoBearings', () => {
      it('should add bearing information to photos', () => {
        const currentBearing = 90;
        const result = updatePhotoBearings(testPhotos, currentBearing);

        expect(result).toHaveLength(testPhotos.length);
        expect(result.every((p: PhotoWithBearing) => 'abs_bearing_diff' in p)).toBe(true);
        expect(result.every((p: PhotoWithBearing) => 'bearing_color' in p)).toBe(true);
      });

      it('should calculate correct bearing differences', () => {
        const currentBearing = 0;
        const result = updatePhotoBearings(testPhotos, currentBearing);
        
        const photo1 = result.find(p => p.id === 'photo1')!;
        expect(photo1.abs_bearing_diff).toBe(90); // 90 - 0 = 90
      });
    });

    describe('sortPhotosByAngularDistance', () => {
      it('should sort photos by angular distance', () => {
        const photosWithBearing = updatePhotoBearings(testPhotos, 0) as PhotoWithBearing[];
        const sorted = sortPhotosByAngularDistance(photosWithBearing, 0);

        expect(sorted).toHaveLength(testPhotos.length);
        
        // Should be sorted by angular distance
        for (let i = 1; i < sorted.length; i++) {
          expect(sorted[i].angular_distance_abs! >= sorted[i-1].angular_distance_abs!).toBe(true);
        }
      });

      it('should add angular_distance_abs property', () => {
        const photosWithBearing = updatePhotoBearings(testPhotos, 0) as PhotoWithBearing[];
        const sorted = sortPhotosByAngularDistance(photosWithBearing, 0);

        expect(sorted.every((p: PhotoData) => typeof p.angular_distance_abs === 'number')).toBe(true);
      });
    });
  });

  describe('PhotoSpatialIndex', () => {

    it('should create grid index from photos and bounds', () => {
      const bounds: Bounds = {
        top_left: new LatLng(50.0640, 14.5140),
        bottom_right: new LatLng(50.0600, 14.5180)
      };

      const index = new PhotoSpatialIndex(testPhotos, bounds);
      
      // Test that we can get photos from a cell
      // Cell 00 would be top-left corner
      const cellPhotos = index.getPhotosInCell('00');
      expect(cellPhotos).toBeDefined();
    });

    it('should return empty array for empty cells', () => {
      const bounds: Bounds = {
        top_left: new LatLng(50.0640, 14.5140),
        bottom_right: new LatLng(50.0600, 14.5180)
      };

      const index = new PhotoSpatialIndex(testPhotos, bounds);
      
      // Test a cell that likely has no photos
      const cellPhotos = index.getPhotosInCell('99');
      expect(cellPhotos).toEqual([]);
    });

    it('should distribute photos across grid cells', () => {
      const bounds: Bounds = {
        top_left: new LatLng(50.0640, 14.5140),
        bottom_right: new LatLng(50.0600, 14.5180)
      };

      const index = new PhotoSpatialIndex(testPhotos, bounds);
      
      // Check that at least some cells have photos
      let foundPhotos = false;
      for (let lat = 0; lat < 10; lat++) {
        for (let lng = 0; lng < 10; lng++) {
          const cellKey = `${lat}${lng}`;
          const photos = index.getPhotosInCell(cellKey);
          if (photos.length > 0) {
            foundPhotos = true;
            break;
          }
        }
        if (foundPhotos) break;
      }
      
      expect(foundPhotos).toBe(true);
    });

    it('should skip photos outside bounds', () => {
      const bounds: Bounds = {
        top_left: new LatLng(60.0, 20.0),
        bottom_right: new LatLng(59.0, 21.0)
      };

      const index = new PhotoSpatialIndex(testPhotos, bounds);
      
      // All test photos are outside these bounds, so all cells should be empty
      let totalPhotos = 0;
      for (let lat = 0; lat < 10; lat++) {
        for (let lng = 0; lng < 10; lng++) {
          const cellKey = `${lat}${lng}`;
          totalPhotos += index.getPhotosInCell(cellKey).length;
        }
      }
      
      expect(totalPhotos).toBe(0);
    });

    it('should handle single photo case', () => {
      const singlePhoto = [testPhotos[0]];
      const bounds: Bounds = {
        top_left: new LatLng(50.0618, 14.5145),
        bottom_right: new LatLng(50.0616, 14.5147)
      };

      const index = new PhotoSpatialIndex(singlePhoto, bounds);
      
      // Should find the photo in at least one cell
      let found = false;
      for (let lat = 0; lat < 10; lat++) {
        for (let lng = 0; lng < 10; lng++) {
          const cellKey = `${lat}${lng}`;
          if (index.getPhotosInCell(cellKey).length > 0) {
            found = true;
            break;
          }
        }
        if (found) break;
      }
      
      expect(found).toBe(true);
    });
  });
});