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
    it('should return green with varying opacity for bearing differences', () => {
      // All colors are green (hue 120), opacity decreases as bearing diff increases
      expect(getBearingColor(0)).toBe('hsla(120, 100%, 70%, 1)');   // step=0, full opacity
      expect(getBearingColor(20)).toBe('hsla(120, 100%, 70%, 1)');  // step=1, full opacity
      expect(getBearingColor(45)).toBe('hsla(120, 100%, 70%, 0.5)'); // step=2
      expect(getBearingColor(90)).toMatch(/^hsla\(120, 100%, 70%, 0\.3+\)$/); // step=3
      expect(getBearingColor(135)).toBe('hsla(120, 100%, 70%, 0.2)'); // step=5
      expect(getBearingColor(180)).toMatch(/^hsla\(120, 100%, 70%, 0\.16+\)$/); // step=6
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
      expect(updated.bearing_color).toBe('hsla(120, 100%, 70%, 0.5)'); // step=2, opacity=0.5
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
      expect(updated.bearing_color).toBe('hsla(120, 100%, 70%, 1)'); // step=1, full opacity
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
        captured_at: 12345,
        accuracy: 10,
      };

      const updated = updatePhotoBearingDiffData(photo, 0);

      expect(updated.id).toBe(photo.id);
      expect(updated.captured_at).toBe(photo.captured_at);
      expect(updated.accuracy).toBe(photo.accuracy);
      expect(updated.abs_bearing_diff).toBe(0);
      expect(updated.bearing_color).toBe('hsla(120, 100%, 70%, 1)'); // step=0, full opacity
    });
  });
});