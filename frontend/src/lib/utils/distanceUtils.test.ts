import { describe, it, expect } from 'vitest';
import {
  calculateDistance,
  isInBounds,
  calculateCenterFromBounds,
  metersToKilometers,
  kilometersToMeters,
} from './distanceUtils';
import type { Bounds } from '../photoProcessing';

describe('distanceUtils', () => {
  describe('calculateDistance', () => {
    it('should calculate distance between two points', () => {
      const point1 = { lat: 50.0617, lng: 14.5146 };
      const point2 = { lat: 50.0627, lng: 14.5156 };
      
      const distance = calculateDistance(point1, point2);
      
      // Distance should be approximately 139 meters
      expect(distance).toBeGreaterThan(130);
      expect(distance).toBeLessThan(150);
    });

    it('should return 0 for same points', () => {
      const point = { lat: 50.0617, lng: 14.5146 };
      
      expect(calculateDistance(point, point)).toBe(0);
    });

    it('should handle antipodal points', () => {
      const northPole = { lat: 90, lng: 0 };
      const southPole = { lat: -90, lng: 0 };
      
      const distance = calculateDistance(northPole, southPole);
      
      // Distance should be approximately half Earth's circumference (~20,000 km)
      expect(distance).toBeGreaterThan(19900000);
      expect(distance).toBeLessThan(20100000);
    });

    it('should handle equatorial points', () => {
      const point1 = { lat: 0, lng: 0 };
      const point2 = { lat: 0, lng: 90 };
      
      const distance = calculateDistance(point1, point2);
      
      // Distance should be approximately 1/4 of Earth's circumference (~10,000 km)
      expect(distance).toBeGreaterThan(9900000);
      expect(distance).toBeLessThan(10100000);
    });
  });

  describe('isInBounds', () => {
    const bounds: Bounds = {
      top_left: { lat: 50.1, lng: 14.4 } as any,
      bottom_right: { lat: 50.0, lng: 14.5 } as any,
    };

    it('should return true for points inside bounds', () => {
      expect(isInBounds({ lat: 50.05, lng: 14.45 }, bounds)).toBe(true);
      expect(isInBounds({ lat: 50.08, lng: 14.42 }, bounds)).toBe(true);
      expect(isInBounds({ lat: 50.02, lng: 14.48 }, bounds)).toBe(true);
    });

    it('should return false for points outside bounds', () => {
      expect(isInBounds({ lat: 50.15, lng: 14.45 }, bounds)).toBe(false);
      expect(isInBounds({ lat: 49.95, lng: 14.45 }, bounds)).toBe(false);
      expect(isInBounds({ lat: 50.05, lng: 14.35 }, bounds)).toBe(false);
      expect(isInBounds({ lat: 50.05, lng: 14.55 }, bounds)).toBe(false);
    });

    it('should handle points on boundaries', () => {
      expect(isInBounds({ lat: 50.1, lng: 14.45 }, bounds)).toBe(true);
      expect(isInBounds({ lat: 50.0, lng: 14.45 }, bounds)).toBe(true);
      expect(isInBounds({ lat: 50.05, lng: 14.4 }, bounds)).toBe(true);
      expect(isInBounds({ lat: 50.05, lng: 14.5 }, bounds)).toBe(true);
    });

    it('should handle bounds crossing dateline', () => {
      const datelineBounds: Bounds = {
        top_left: { lat: 50, lng: 170 } as any,
        bottom_right: { lat: 40, lng: -170 } as any,
      };

      expect(isInBounds({ lat: 45, lng: 175 }, datelineBounds)).toBe(true);
      expect(isInBounds({ lat: 45, lng: -175 }, datelineBounds)).toBe(true);
      expect(isInBounds({ lat: 45, lng: 0 }, datelineBounds)).toBe(false);
    });
  });

  describe('calculateCenterFromBounds', () => {
    it('should calculate center of bounds', () => {
      const bounds: Bounds = {
        top_left: { lat: 50.1, lng: 14.4 } as any,
        bottom_right: { lat: 50.0, lng: 14.5 } as any,
      };

      const center = calculateCenterFromBounds(bounds);

      expect(center.lat).toBeCloseTo(50.05, 5);
      expect(center.lng).toBeCloseTo(14.45, 5);
    });

    it('should handle bounds crossing dateline', () => {
      const bounds: Bounds = {
        top_left: { lat: 50, lng: 170 } as any,
        bottom_right: { lat: 40, lng: -170 } as any,
      };

      const center = calculateCenterFromBounds(bounds);

      expect(center.lat).toBeCloseTo(45, 5);
      expect(center.lng).toBeCloseTo(180, 5);
    });

    it('should handle bounds at poles', () => {
      const polarBounds: Bounds = {
        top_left: { lat: 90, lng: -180 } as any,
        bottom_right: { lat: 80, lng: 180 } as any,
      };

      const center = calculateCenterFromBounds(polarBounds);

      expect(center.lat).toBeCloseTo(85, 5);
      expect(center.lng).toBe(0);
    });
  });

  describe('unit conversions', () => {
    describe('metersToKilometers', () => {
      it('should convert meters to kilometers', () => {
        expect(metersToKilometers(1000)).toBe(1);
        expect(metersToKilometers(2500)).toBe(2.5);
        expect(metersToKilometers(500)).toBe(0.5);
        expect(metersToKilometers(0)).toBe(0);
      });

      it('should round to specified decimal places', () => {
        expect(metersToKilometers(1234, 0)).toBe(1);
        expect(metersToKilometers(1234, 1)).toBe(1.2);
        expect(metersToKilometers(1234, 2)).toBe(1.23);
        expect(metersToKilometers(1234, 3)).toBe(1.234);
      });
    });

    describe('kilometersToMeters', () => {
      it('should convert kilometers to meters', () => {
        expect(kilometersToMeters(1)).toBe(1000);
        expect(kilometersToMeters(2.5)).toBe(2500);
        expect(kilometersToMeters(0.5)).toBe(500);
        expect(kilometersToMeters(0)).toBe(0);
      });
    });
  });
});