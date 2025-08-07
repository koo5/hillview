import { describe, it, expect } from 'vitest';
import {
  filterPhotosByArea,
  calculatePhotoDistances,
  updatePhotoBearings,
  sortPhotosByAngularDistance
} from './photoProcessingUtils';

// Simple test to verify the functions are importable and work
describe('photoProcessing (smoke test)', () => {
  it('should import functions successfully', () => {
    expect(filterPhotosByArea).toBeDefined();
    expect(calculatePhotoDistances).toBeDefined();
    expect(updatePhotoBearings).toBeDefined();
    expect(sortPhotosByAngularDistance).toBeDefined();
  });

  it('should handle empty arrays gracefully', () => {
    // Mock bounds object without Leaflet dependency
    const bounds = {
      top_left: { lat: 50.1, lng: 14.1 },
      bottom_right: { lat: 50.0, lng: 14.2 }
    } as any;

    expect(filterPhotosByArea([], bounds, 0)).toEqual([]);
    expect(calculatePhotoDistances([], { lat: 50.0, lng: 14.0 }, 100)).toEqual([]);
    expect(updatePhotoBearings([], 90)).toEqual([]);
    expect(sortPhotosByAngularDistance([], 0)).toEqual([]);
  });
});