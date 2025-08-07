import { LatLng } from 'leaflet';
import type { PhotoData, PhotoWithBearing, PhotoId } from './types/photoTypes';

/**
 * Simple bounds interface for photo filtering
 */
export interface Bounds {
  top_left: LatLng;
  bottom_right: LatLng;
}

/**
 * Calculate the distance between two geographic points in meters
 */
export function calculateDistance(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371e3; // Earth's radius in meters
  const φ1 = lat1 * Math.PI / 180;
  const φ2 = lat2 * Math.PI / 180;
  const Δφ = (lat2 - lat1) * Math.PI / 180;
  const Δλ = (lng1 - lng2) * Math.PI / 180;

  const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
            Math.cos(φ1) * Math.cos(φ2) *
            Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return R * c;
}

/**
 * Check if a photo is within given bounds with optional tolerance
 */
export function isPhotoInBounds(photo: PhotoData, bounds: Bounds, tolerance: number = 0): boolean {
  const lat = photo.coord.lat;
  const lng = photo.coord.lng;
  
  const topLat = bounds.top_left.lat + tolerance;
  const leftLng = bounds.top_left.lng - tolerance;
  const bottomLat = bounds.bottom_right.lat - tolerance;
  const rightLng = bounds.bottom_right.lng + tolerance;

  return lat <= topLat && lat >= bottomLat && lng >= leftLng && lng <= rightLng;
}

/**
 * Filter photos by geographic area
 */
export function filterPhotosByArea(photos: PhotoData[], bounds: Bounds, tolerance: number = 0): PhotoData[] {
  return photos.filter(photo => isPhotoInBounds(photo, bounds, tolerance));
}

/**
 * Calculate distances from a center point and filter by maximum range
 */
export function calculatePhotoDistances(
  photos: PhotoData[], 
  center: { lat: number; lng: number }, 
  maxRange: number
): PhotoData[] {
  return photos.map(photo => {
    const distance = calculateDistance(center.lat, center.lng, photo.coord.lat, photo.coord.lng);
    return {
      ...photo,
      range_distance: distance
    };
  }).filter(photo => photo.range_distance! <= maxRange);
}

/**
 * Normalize bearing to 0-360 range
 */
export function normalizeBearing(bearing: number): number {
  return ((bearing % 360) + 360) % 360;
}

/**
 * Calculate the absolute difference between two bearings
 */
export function calculateBearingDifference(bearing1: number, bearing2: number): number {
  const diff = Math.abs(normalizeBearing(bearing1) - normalizeBearing(bearing2));
  return Math.min(diff, 360 - diff);
}

/**
 * Get color for bearing difference (green=close, red=far)
 */
export function getBearingColor(bearingDifference: number): string {
  if (bearingDifference <= 15) return 'green';
  if (bearingDifference <= 45) return 'yellow';
  if (bearingDifference <= 90) return 'orange';
  return 'red';
}

/**
 * Update photos with bearing information
 */
export function updatePhotoBearings(photos: PhotoData[], currentBearing: number): PhotoWithBearing[] {
  return photos.map(photo => {
    const absBearingDiff = calculateBearingDifference(photo.bearing, currentBearing);
    const bearingColor = getBearingColor(absBearingDiff);
    
    return {
      ...photo,
      abs_bearing_diff: absBearingDiff,
      bearing_color: bearingColor
    };
  });
}

/**
 * Calculate angular distance for sorting photos
 */
export function calculateAngularDistance(photo: PhotoData, viewBearing: number): number {
  return calculateBearingDifference(photo.bearing, viewBearing);
}

/**
 * Sort photos by angular distance from a viewing bearing
 */
export function sortPhotosByAngularDistance(photos: PhotoWithBearing[], viewBearing: number): PhotoData[] {
  return photos.map(photo => ({
    ...photo,
    angular_distance_abs: calculateAngularDistance(photo, viewBearing)
  })).sort((a, b) => (a.angular_distance_abs || 0) - (b.angular_distance_abs || 0));
}

/**
 * Simple spatial index for photo locations using a grid-based approach
 */
export class PhotoSpatialIndex {
  private gridSize: number;
  private photoGrid: Map<string, Set<PhotoId>> = new Map();
  private photoLocations: Map<PhotoId, { lat: number; lng: number }> = new Map();

  constructor(gridSize: number = 0.001) {
    this.gridSize = gridSize;
  }

  private getGridKey(lat: number, lng: number): string {
    const gridLat = Math.floor(lat / this.gridSize);
    const gridLng = Math.floor(lng / this.gridSize);
    return `${gridLat},${gridLng}`;
  }

  addPhoto(photoId: PhotoId, lat: number, lng: number): void {
    const gridKey = this.getGridKey(lat, lng);
    
    if (!this.photoGrid.has(gridKey)) {
      this.photoGrid.set(gridKey, new Set<PhotoId>());
    }
    
    this.photoGrid.get(gridKey)!.add(photoId);
    this.photoLocations.set(photoId, { lat, lng });
  }

  removePhoto(photoId: PhotoId): void {
    const location = this.photoLocations.get(photoId);
    if (!location) return;

    const gridKey = this.getGridKey(location.lat, location.lng);
    const gridSet = this.photoGrid.get(gridKey);
    if (gridSet) {
      gridSet.delete(photoId);
      if (gridSet.size === 0) {
        this.photoGrid.delete(gridKey);
      }
    }
    
    this.photoLocations.delete(photoId);
  }

  getPhotosInBounds(bounds: Bounds): PhotoId[] {
    const results: PhotoId[] = [];
    const topLat = bounds.top_left.lat;
    const leftLng = bounds.top_left.lng;
    const bottomLat = bounds.bottom_right.lat;
    const rightLng = bounds.bottom_right.lng;

    // Calculate grid range
    const minGridLat = Math.floor(bottomLat / this.gridSize);
    const maxGridLat = Math.ceil(topLat / this.gridSize);
    const minGridLng = Math.floor(leftLng / this.gridSize);
    const maxGridLng = Math.ceil(rightLng / this.gridSize);

    // Check each grid cell in range
    for (let gridLat = minGridLat; gridLat <= maxGridLat; gridLat++) {
      for (let gridLng = minGridLng; gridLng <= maxGridLng; gridLng++) {
        const gridKey = `${gridLat},${gridLng}`;
        const photosInGrid = this.photoGrid.get(gridKey);
        
        if (photosInGrid) {
          for (const photoId of photosInGrid) {
            const location = this.photoLocations.get(photoId);
            if (location && 
                location.lat <= topLat && location.lat >= bottomLat &&
                location.lng >= leftLng && location.lng <= rightLng) {
              results.push(photoId);
            }
          }
        }
      }
    }

    return results;
  }

  clear(): void {
    this.photoGrid.clear();
    this.photoLocations.clear();
  }
}