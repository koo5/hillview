import { LatLng } from 'leaflet';
import { Coordinate } from "tsgeo/Coordinate";
import { Vincenty } from "tsgeo/Distance/Vincenty";
import Angles from 'angles';

// Re-declare PhotoData interface to avoid circular dependencies
export interface PhotoData {
  id: string;
  source_type: string;
  file: string;
  url: string;
  coord: LatLng;
  bearing: number;
  altitude: number;
  source?: any;
  sizes?: Record<string, PhotoSize>;
  isUserPhoto?: boolean;
  isDevicePhoto?: boolean;
  timestamp?: number;
  accuracy?: number;
  abs_bearing_diff?: number;
  bearing_color?: string;
  range_distance?: number | null;
  angular_distance_abs?: number;
}

export interface PhotoSize {
  url: string;
  width: number;
  height: number;
}

const calculator = new Vincenty();

export interface Bounds {
  top_left: LatLng;
  bottom_right: LatLng;
}

export interface PhotoWithDistance extends PhotoData {
  range_distance: number | null;
}

export interface PhotoWithBearing extends PhotoData {
  abs_bearing_diff: number;
  bearing_color: string;
  angular_distance_abs?: number;
}

// Heavy computation functions extracted from data.svelte.ts

export function filterPhotosByArea(
  photos: PhotoData[], 
  bounds: Bounds,
  tolerance: number = 0.1
): PhotoData[] {
  const window_x = bounds.bottom_right.lng - bounds.top_left.lng;
  const window_y = bounds.top_left.lat - bounds.bottom_right.lat;
  
  // Add tolerance for photos near edges
  const x_tolerance = window_x * tolerance;
  const y_tolerance = window_y * tolerance;
  
  return photos.filter(photo => {
    return photo.coord.lat < bounds.top_left.lat + y_tolerance && 
           photo.coord.lat > bounds.bottom_right.lat - y_tolerance &&
           photo.coord.lng > bounds.top_left.lng - x_tolerance && 
           photo.coord.lng < bounds.bottom_right.lng + x_tolerance;
  });
}

export function calculatePhotoDistances(
  photos: PhotoData[],
  center: { lat: number; lng: number },
  maxRange: number
): PhotoWithDistance[] {
  const centerCoord = new Coordinate(center.lat, center.lng);
  
  return photos.map(photo => {
    const photoCoord = new Coordinate(photo.coord.lat, photo.coord.lng);
    const distance = calculator.getDistance(centerCoord, photoCoord);
    
    return {
      ...photo,
      range_distance: distance <= maxRange ? distance : null
    } as PhotoWithDistance;
  }).filter(photo => photo.range_distance !== null);
}

export function updatePhotoBearings(
  photos: PhotoData[],
  currentBearing: number
): PhotoWithBearing[] {
  return photos.map(photo => {
    const abs_bearing_diff = Math.abs(Angles.distance(currentBearing, photo.bearing));
    const bearing_color = getBearingColor(abs_bearing_diff);
    
    return {
      ...photo,
      abs_bearing_diff,
      bearing_color
    } as PhotoWithBearing;
  });
}

export function sortPhotosByAngularDistance(
  photos: PhotoWithBearing[],
  currentBearing: number
): PhotoWithBearing[] {
  return photos
    .map(photo => ({
      ...photo,
      angular_distance_abs: Math.abs(Angles.distance(currentBearing, photo.bearing))
    }))
    .sort((a, b) => a.angular_distance_abs - b.angular_distance_abs);
}

function getBearingColor(abs_bearing_diff: number): string {
  if (abs_bearing_diff === null) return '#9E9E9E'; // grey
  return 'hsl(' + Math.round(100 - abs_bearing_diff/2) + ', 100%, 70%)';
}

export function fixupBearings(photos: PhotoData[]) {
  // Sort photos by bearing, spreading out photos with the same bearing
  if (photos.length < 2) return;
  
  // For large photo sets, limit iterations to prevent freezing
  const maxIterations = photos.length > 100 ? 5 : 10;
  let iterations = 0;
  let moved = true;
  
  while (moved && iterations < maxIterations) {
    photos.sort((a: PhotoData, b: PhotoData) => a.bearing - b.bearing);
    moved = false;
    iterations++;
    
    for (let index = 0; index < photos.length; index++) {
      const next = photos[(index + 1) % photos.length];
      const photo = photos[index];
      let diff = next.bearing - photo.bearing;
      if (diff === 0) {
        next.bearing = (next.bearing + 0.01 * iterations) % 360;
        moved = true;
      }
    }
  }
}

// Spatial indexing for efficient area queries - stores only IDs
export class PhotoSpatialIndex {
  private gridSize: number;
  private grid: Map<string, Set<string>> = new Map();
  private photoLocations: Map<string, { lat: number; lng: number }> = new Map();
  
  constructor(gridSize: number = 0.01) { // ~1km grid cells
    this.gridSize = gridSize;
  }
  
  addPhoto(photoId: string, lat: number, lng: number) {
    this.photoLocations.set(photoId, { lat, lng });
    const key = this.getGridKey(lat, lng);
    
    if (!this.grid.has(key)) {
      this.grid.set(key, new Set());
    }
    this.grid.get(key)!.add(photoId);
  }
  
  removePhoto(photoId: string) {
    const location = this.photoLocations.get(photoId);
    if (!location) return;
    
    const key = this.getGridKey(location.lat, location.lng);
    this.grid.get(key)?.delete(photoId);
    this.photoLocations.delete(photoId);
  }
  
  getPhotoIdsInBounds(bounds: Bounds, maxResults: number = 2000): string[] {
    const results: string[] = [];
    const seen = new Set<string>();
    
    // Early exit if no photos
    if (this.photoLocations.size === 0) {
      return results;
    }
    
    // Get all grid cells that intersect with bounds
    const minLat = Math.floor(bounds.bottom_right.lat / this.gridSize) * this.gridSize;
    const maxLat = Math.ceil(bounds.top_left.lat / this.gridSize) * this.gridSize;
    const minLng = Math.floor(bounds.top_left.lng / this.gridSize) * this.gridSize;
    const maxLng = Math.ceil(bounds.bottom_right.lng / this.gridSize) * this.gridSize;
    
    // Calculate number of grid cells
    const latCells = Math.ceil((maxLat - minLat) / this.gridSize);
    const lngCells = Math.ceil((maxLng - minLng) / this.gridSize);
    const totalCells = latCells * lngCells;
    
    // If bounds are too large, just return empty - no point checking millions of cells
    if (totalCells > 100000) {
      console.log(`Bounds too large: ${totalCells} cells, skipping`);
      return results;
    }
    
    // If too many cells, sample them
    let latStep = this.gridSize;
    let lngStep = this.gridSize;
    
    if (totalCells > 1000) {
      // Sample grid cells to limit iteration
      const samplingFactor = Math.ceil(Math.sqrt(totalCells / 1000));
      latStep = this.gridSize * samplingFactor;
      lngStep = this.gridSize * samplingFactor;
      console.log(`Sampling grid: ${totalCells} cells, sampling every ${samplingFactor} cells`);
    }
    
    // Early exit if we've collected enough results
    let cellsChecked = 0;
    outer: for (let lat = minLat; lat <= maxLat; lat += latStep) {
      for (let lng = minLng; lng <= maxLng; lng += lngStep) {
        cellsChecked++;
        const key = this.getGridKey(lat, lng);
        const photoIds = this.grid.get(key);
        
        if (photoIds) {
          for (const id of photoIds) {
            if (!seen.has(id)) {
              seen.add(id);
              const location = this.photoLocations.get(id);
              if (location && this.isInBounds(location, bounds)) {
                results.push(id);
                
                // Stop early if we have enough
                if (results.length >= maxResults) {
                  break outer;
                }
              }
            }
          }
        }
      }
    }
    
    return results;
  }
  
  private getGridKey(lat: number, lng: number): string {
    const gridLat = Math.floor(lat / this.gridSize) * this.gridSize;
    const gridLng = Math.floor(lng / this.gridSize) * this.gridSize;
    return `${gridLat},${gridLng}`;
  }
  
  private isInBounds(location: { lat: number; lng: number }, bounds: Bounds): boolean {
    return location.lat <= bounds.top_left.lat && 
           location.lat >= bounds.bottom_right.lat &&
           location.lng >= bounds.top_left.lng && 
           location.lng <= bounds.bottom_right.lng;
  }
  
  clear() {
    this.photoLocations.clear();
    this.grid.clear();
  }
  
  size(): number {
    return this.photoLocations.size;
  }
}