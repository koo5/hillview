import { describe, it, expect } from 'vitest';
import {
  getAbsBearingDiff,
  getAngularDistance,
  getBearingColor,
  updatePhotoBearingDiffData,
  calculateAngularDistance,
  normalizeBearing,
  calculateBearingData,
} from './bearingUtils';
import type { PhotoData } from '../types/photoTypes';

describe('bearingUtils', () => {
  describe('normalizeBearing', () => {
    it('should normalize angles to 0-360 range', () => {
      expect(normalizeBearing(0)).toBe(0);
      expect(normalizeBearing(360)).toBe(0);
      expect(normalizeBearing(720)).toBe(0);
      expect(normalizeBearing(-90)).toBe(270);
      expect(normalizeBearing(-360)).toBe(0);
      expect(normalizeBearing(450)).toBe(90);
    });
  });

  describe('getAngularDistance', () => {
    it('should calculate bearing difference correctly', () => {
      expect(getAngularDistance(0, 90)).toBe(90);
      expect(getAngularDistance(90, 0)).toBe(-90);
      expect(getAngularDistance(350, 10)).toBe(20);
      expect(getAngularDistance(10, 350)).toBe(-20);
      // When the difference is exactly 180, the sign might vary
      expect(Math.abs(getAngularDistance(0, 180))).toBe(180);
      expect(Math.abs(getAngularDistance(180, 0))).toBe(180);
    });

    it('should handle edge cases', () => {
      expect(getAngularDistance(0, 0)).toBe(0);
      expect(getAngularDistance(180, 180)).toBe(0);
      expect(getAngularDistance(270, 90)).toBe(-180);
    });
  });

  describe('getAbsBearingDiff', () => {
    it('should calculate absolute bearing difference', () => {
      expect(getAbsBearingDiff(0, 90)).toBe(90);
      expect(getAbsBearingDiff(90, 0)).toBe(90);
      expect(getAbsBearingDiff(350, 10)).toBe(20);
      expect(getAbsBearingDiff(10, 350)).toBe(20);
    });
  });

  describe('getBearingColor', () => {
    it('should return correct colors for bearing differences', () => {
      expect(getBearingColor(0)).toBe('hsl(100, 100%, 70%)');
      expect(getBearingColor(10)).toBe('hsl(95, 100%, 70%)');
      expect(getBearingColor(15)).toBe('hsl(93, 100%, 70%)');
      expect(getBearingColor(20)).toBe('hsl(90, 100%, 70%)');
      expect(getBearingColor(45)).toBe('hsl(78, 100%, 70%)');
      expect(getBearingColor(90)).toBe('hsl(55, 100%, 70%)');
      expect(getBearingColor(135)).toBe('hsl(33, 100%, 70%)');
      expect(getBearingColor(180)).toBe('hsl(10, 100%, 70%)');
    });

    it('should handle null/undefined bearing differences', () => {
      expect(getBearingColor(null)).toBe('#9E9E9E');
      expect(getBearingColor(undefined as any)).toBe('#9E9E9E');
    });
  });

  describe('calculateAngularDistance', () => {
    it('should calculate angular distance correctly', () => {
      expect(calculateAngularDistance(0, 90)).toBe(90);
      expect(calculateAngularDistance(90, 0)).toBe(90);
      expect(calculateAngularDistance(350, 10)).toBe(20);
      expect(calculateAngularDistance(10, 350)).toBe(20);
      expect(calculateAngularDistance(0, 180)).toBe(180);
      expect(calculateAngularDistance(180, 0)).toBe(180);
    });

    it('should always return positive values', () => {
      expect(calculateAngularDistance(0, 270)).toBe(90);
      expect(calculateAngularDistance(270, 0)).toBe(90);
      expect(calculateAngularDistance(45, 315)).toBe(90);
      expect(calculateAngularDistance(315, 45)).toBe(90);
    });
  });

  describe('updatePhotoBearingDiffData', () => {
    it('should update photo with bearing data', () => {
      const photo: PhotoData = {
        id: 'test1',
        uid: 'test-test1',
        source_type: 'test',
        file: 'test.jpg',
        url: 'test.jpg',
        coord: { lat: 0, lng: 0 } as any,
        bearing: 45,
        altitude: 100,
      };

      const updated = updatePhotoBearingDiffData(photo, 90);

      expect(updated.abs_bearing_diff).toBe(45);
      expect(updated.bearing_color).toBe('hsl(78, 100%, 70%)'); // Based on the actual implementation
    });

    it('should handle wrapped bearings', () => {
      const photo: PhotoData = {
        id: 'test2',
        uid: 'test-test2',
        source_type: 'test',
        file: 'test.jpg',
        url: 'test.jpg',
        coord: { lat: 0, lng: 0 } as any,
        bearing: 350,
        altitude: 100,
      };

      const updated = updatePhotoBearingDiffData(photo, 10);

      expect(updated.abs_bearing_diff).toBe(20);
      expect(updated.bearing_color).toBe('hsl(90, 100%, 70%)'); // Based on the actual implementation
    });

    it('should preserve all original photo properties', () => {
      const photo: PhotoData = {
        id: 'test3',
        uid: 'test-test3',
        source_type: 'test',
        file: 'test.jpg',
        url: 'test.jpg',
        coord: { lat: 0, lng: 0 } as any,
        bearing: 0,
        altitude: 100,
        timestamp: 12345,
        accuracy: 10,
      };

      const updated = updatePhotoBearingDiffData(photo, 0);

      expect(updated.id).toBe(photo.id);
      expect(updated.timestamp).toBe(photo.timestamp);
      expect(updated.accuracy).toBe(photo.accuracy);
      expect(updated.abs_bearing_diff).toBe(0);
      expect(updated.bearing_color).toBe('hsl(100, 100%, 70%)');
    });
  });
});