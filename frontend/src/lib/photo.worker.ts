/// <reference lib="webworker" />

import type { WorkerMessage, WorkerResponse, PhotoData, Bounds, SourceConfig } from './photoWorkerTypes';
import { updatePhotoBearingData } from './utils/bearingUtils';
import { SimpleDistanceCalculator, calculateCenterFromBounds, isInBounds } from './utils/distanceUtils';

// Distance calculator instance
const calculator = new SimpleDistanceCalculator();

// Photo data store - source of truth
const photoStore = new Map<string, PhotoData>();
let currentBounds: Bounds | null = null;
let currentRange = 5000; // Default 5km range
let sourcesConfig: SourceConfig[] = [];
let lastVisiblePhotos: PhotoData[] = [];

// Configuration
const MAX_PHOTOS_IN_AREA = 500;
const MAX_PHOTOS_IN_RANGE = 100;
let recalculateBearingDistances = false;

// Spatial indexing for efficient queries
class PhotoSpatialIndex {
  private gridSize: number;
  private grid = new Map<string, Set<string>>();
  private photoLocations = new Map<string, { lat: number; lng: number }>();
  
  constructor(gridSize = 0.01) { // ~1km grid cells
    this.gridSize = gridSize;
  }
  
  addPhoto(photoId: string, lat: number, lng: number): void {
    this.photoLocations.set(photoId, { lat, lng });
    const key = this.getGridKey(lat, lng);
    
    if (!this.grid.has(key)) {
      this.grid.set(key, new Set());
    }
    this.grid.get(key)!.add(photoId);
  }
  
  removePhoto(photoId: string): void {
    const location = this.photoLocations.get(photoId);
    if (!location) return;
    
    const key = this.getGridKey(location.lat, location.lng);
    this.grid.get(key)?.delete(photoId);
    this.photoLocations.delete(photoId);
  }
  
  getPhotoIdsInBounds(bounds: Bounds, maxResults = 2000): string[] {
    const results: string[] = [];
    const seen = new Set<string>();
    
    if (this.photoLocations.size === 0) {
      console.log('PhotoSpatialIndex: No photos in index');
      return results;
    }
    
    console.log(`PhotoSpatialIndex: Searching bounds`, bounds, `in ${this.photoLocations.size} photos`);
    
    const minLat = Math.floor(bounds.bottom_right.lat / this.gridSize) * this.gridSize;
    const maxLat = Math.ceil(bounds.top_left.lat / this.gridSize) * this.gridSize;
    const minLng = Math.floor(bounds.top_left.lng / this.gridSize) * this.gridSize;
    const maxLng = Math.ceil(bounds.bottom_right.lng / this.gridSize) * this.gridSize;
    
    const latCells = Math.ceil((maxLat - minLat) / this.gridSize);
    const lngCells = Math.ceil((maxLng - minLng) / this.gridSize);
    const totalCells = latCells * lngCells;
    
    if (totalCells > 100000) {
      return results;
    }
    
    let latStep = this.gridSize;
    let lngStep = this.gridSize;
    
    if (totalCells > 1000) {
      const samplingFactor = Math.ceil(Math.sqrt(totalCells / 1000));
      latStep = this.gridSize * samplingFactor;
      lngStep = this.gridSize * samplingFactor;
    }
    
    outer: for (let lat = minLat; lat <= maxLat; lat += latStep) {
      for (let lng = minLng; lng <= maxLng; lng += lngStep) {
        const key = this.getGridKey(lat, lng);
        const photoIds = this.grid.get(key);
        
        if (photoIds) {
          for (const id of photoIds) {
            if (!seen.has(id)) {
              seen.add(id);
              const location = this.photoLocations.get(id);
              if (location && this.isInBounds(location, bounds)) {
                results.push(id);
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
    return isInBounds(location, bounds);
  }
  
  clear(): void {
    this.photoLocations.clear();
    this.grid.clear();
  }
}

const spatialIndex = new PhotoSpatialIndex();

// Photo processing functions
function loadPhotos(photos: PhotoData[]): void {
  try {
    photoStore.clear();
    spatialIndex.clear();
    
    for (const photo of photos) {
      photoStore.set(photo.id, photo);
      spatialIndex.addPhoto(photo.id, photo.coord.lat, photo.coord.lng);
    }
    
    console.log(`Worker: Loaded ${photos.length} photos`);
    recalculateVisiblePhotos();
  } catch (error) {
    console.error('Worker: Error loading photos:', error);
    postError('loadPhotos', error);
  }
}

function updateBounds(bounds: Bounds): void {
  try {
    console.log('Worker: updateBounds called with:', bounds);
    // Only recalculate if bounds actually changed
    if (!currentBounds || 
        currentBounds.top_left.lat !== bounds.top_left.lat ||
        currentBounds.top_left.lng !== bounds.top_left.lng ||
        currentBounds.bottom_right.lat !== bounds.bottom_right.lat ||
        currentBounds.bottom_right.lng !== bounds.bottom_right.lng) {
      currentBounds = bounds;
      console.log('Worker: Bounds updated, triggering recalculation');
      recalculateVisiblePhotos();
    } else {
      console.log('Worker: Bounds unchanged, skipping recalculation');
    }
  } catch (error) {
    console.error('Worker: Error updating bounds:', error);
    postError('updateBounds', error);
  }
}

function updateRange(range: number): void {
  try {
    // Only recalculate if range actually changed
    if (currentRange !== range) {
      currentRange = range;
      recalculateVisiblePhotos();
    }
  } catch (error) {
    console.error('Worker: Error updating range:', error);
    postError('updateRange', error);
  }
}

function updateSources(sources: SourceConfig[]): void {
  try {
    // Only recalculate if sources actually changed
    const sourcesChanged = !sourcesConfig || 
      sourcesConfig.length !== sources.length ||
      sourcesConfig.some((s, i) => s.id !== sources[i]?.id || s.enabled !== sources[i]?.enabled);
    
    if (sourcesChanged) {
      sourcesConfig = sources;
      recalculateVisiblePhotos();
    }
  } catch (error) {
    console.error('Worker: Error updating sources:', error);
    postError('updateSources', error);
  }
}

function recalculateVisiblePhotos(): void {
  if (!currentBounds) {
    console.log('Worker: No bounds set, skipping recalculation. Photos loaded:', photoStore.size);
    return;
  }
  
  console.log('Worker: Recalculating visible photos with bounds:', currentBounds, 'Photos:', photoStore.size);
  const startTime = performance.now();
  
  const hillviewEnabled = sourcesConfig.find(s => s.id === 'hillview')?.enabled ?? false;
  const mapillaryEnabled = sourcesConfig.find(s => s.id === 'mapillary')?.enabled ?? false;
  const deviceEnabled = sourcesConfig.find(s => s.id === 'device')?.enabled ?? false;
  
  let hillviewFiltered: PhotoData[] = [];
  let mapillaryFiltered: PhotoData[] = [];
  let deviceFiltered: PhotoData[] = [];
  
  // Get photo IDs in spatial bounds first
  const photoIdsInBounds = spatialIndex.getPhotoIdsInBounds(currentBounds, MAX_PHOTOS_IN_AREA * 2);
  
  // Filter by source and apply limits
  if (hillviewEnabled) {
    const hillviewInBounds: PhotoData[] = [];
    
    for (const photoId of photoIdsInBounds) {
      const photo = photoStore.get(photoId);
      if (photo && photo.source?.id === 'hillview') {
        hillviewInBounds.push(photo);
      }
    }
    
    // Prioritize user and device photos
    const userPhotos = hillviewInBounds.filter(p => p.isUserPhoto);
    const devicePhotos = hillviewInBounds.filter(p => p.isDevicePhoto);
    const regularPhotos = hillviewInBounds.filter(p => !p.isUserPhoto && !p.isDevicePhoto);
    
    hillviewFiltered = [...userPhotos, ...devicePhotos];
    
    const remainingSlots = MAX_PHOTOS_IN_AREA - hillviewFiltered.length;
    if (remainingSlots > 0 && regularPhotos.length > 0) {
      if (regularPhotos.length <= remainingSlots) {
        hillviewFiltered.push(...regularPhotos);
      } else {
        // Sample evenly by bearing
        regularPhotos.sort((a, b) => a.bearing - b.bearing);
        const step = regularPhotos.length / remainingSlots;
        for (let i = 0; i < remainingSlots; i++) {
          const index = Math.floor(i * step);
          hillviewFiltered.push(regularPhotos[index]);
        }
      }
    }
  }
  
  if (mapillaryEnabled) {
    const mapillaryInBounds: PhotoData[] = [];
    
    for (const photoId of photoIdsInBounds) {
      const photo = photoStore.get(photoId);
      if (photo && photo.source?.id === 'mapillary') {
        mapillaryInBounds.push(photo);
        if (mapillaryInBounds.length >= MAX_PHOTOS_IN_AREA) {
          break;
        }
      }
    }
    
    mapillaryFiltered = mapillaryInBounds;
  }
  
  if (deviceEnabled) {
    const deviceInBounds: PhotoData[] = [];
    
    for (const photoId of photoIdsInBounds) {
      const photo = photoStore.get(photoId);
      if (photo && photo.source?.id === 'device') {
        deviceInBounds.push(photo);
      }
    }
    
    deviceFiltered = deviceInBounds;
  }
  
  // Combine and deduplicate
  const combinedMap = new Map<string, PhotoData>();
  
  for (const photo of hillviewFiltered) {
    combinedMap.set(photo.id, photo);
  }
  
  for (const photo of mapillaryFiltered) {
    if (!combinedMap.has(photo.id)) {
      combinedMap.set(photo.id, photo);
    }
  }
  
  for (const photo of deviceFiltered) {
    if (!combinedMap.has(photo.id)) {
      combinedMap.set(photo.id, photo);
    }
  }
  
  const visiblePhotos = Array.from(combinedMap.values());
  
  // Apply bearing fixup
  fixupBearings(visiblePhotos);
  
  // Calculate distances from center of bounds
  const center = calculateCenterFromBounds(currentBounds);
  
  for (const photo of visiblePhotos) {
    const distance = calculator.getDistance(center, photo.coord);
    photo.range_distance = distance <= currentRange ? distance : null;
  }
  
  lastVisiblePhotos = visiblePhotos;
  
  // Only log when we have results or significant processing time
  const processingTime = performance.now() - startTime;
  if (visiblePhotos.length > 0 || processingTime > 10) {
    console.log(`Worker: Filtered ${visiblePhotos.length} photos in ${processingTime.toFixed(1)}ms`);
  }
  
  // Send update to main thread
  postMessage({
    id: 'auto',
    type: 'photosUpdate',
    data: {
      photos: visiblePhotos,
      hillviewCount: hillviewFiltered.length,
      mapillaryCount: mapillaryFiltered.length
    }
  } as WorkerResponse);
}

function fixupBearings(photos: PhotoData[]): void {
  if (photos.length < 2) return;
  
  const maxIterations = photos.length > 100 ? 5 : 10;
  let iterations = 0;
  let moved = true;
  
  while (moved && iterations < maxIterations) {
    photos.sort((a, b) => a.bearing - b.bearing);
    moved = false;
    iterations++;
    
    for (let index = 0; index < photos.length; index++) {
      const next = photos[(index + 1) % photos.length];
      const photo = photos[index];
      const diff = next.bearing - photo.bearing;
      if (diff === 0) {
        next.bearing = (next.bearing + 0.01 * iterations) % 360;
        moved = true;
      }
    }
  }
}

function getBearingPhotos(bearing: number, center: { lat: number; lng: number }): void {
  try {
    let photosWithDistance: PhotoData[] = [];
    
    if (recalculateBearingDistances) {
      // Recalculate distances for current visible photos
      for (const photo of lastVisiblePhotos) {
        const distance = calculator.getDistance(center, photo.coord);
        
        if (distance <= currentRange) {
          photosWithDistance.push({
            ...photo,
            range_distance: distance
          });
        }
      }
      
      // Limit photos (preserve bearing order from lastVisiblePhotos)
      photosWithDistance = photosWithDistance.slice(0, MAX_PHOTOS_IN_RANGE);
    } else {
      // Use existing distances from lastVisiblePhotos
      photosWithDistance = lastVisiblePhotos.filter(photo => 
        photo.range_distance !== null && 
        photo.range_distance !== undefined && 
        photo.range_distance <= currentRange
      ).slice(0, MAX_PHOTOS_IN_RANGE);
    }
    
    // Update bearing colors (but don't sort - leave that to main thread)
    const photosWithBearings = photosWithDistance.map(photo => 
      updatePhotoBearingData(photo, bearing)
    );
    
    postMessage({
      id: 'auto',
      type: 'bearingUpdate',
      data: {
        photosInRange: photosWithBearings,
        bearing: bearing
      }
    } as WorkerResponse);
  } catch (error) {
    console.error('Worker: Error getting bearing photos:', error);
    postError('getBearingPhotos', error);
  }
}


function postError(operation: string, error: any): void {
  postMessage({
    id: 'error',
    type: 'error',
    error: {
      message: error?.message || 'Unknown error',
      operation,
      timestamp: Date.now()
    }
  } as WorkerResponse);
}

// Message handler
self.onmessage = function(e: MessageEvent<WorkerMessage>) {
  const { id, type, data } = e.data;
  
  try {
    switch (type) {
      case 'init':
        // Worker initialized
        postMessage({ id, type: 'ready' } as WorkerResponse);
        break;
        
      case 'loadPhotos':
        if (data?.photos) {
          loadPhotos(data.photos);
        }
        postMessage({ id, type: 'success' } as WorkerResponse);
        break;
        
      case 'updateBounds':
        if (data?.bounds) {
          updateBounds(data.bounds);
        }
        postMessage({ id, type: 'success' } as WorkerResponse);
        break;
        
      case 'updateRange':
        if (data?.range !== undefined) {
          updateRange(data.range);
        }
        postMessage({ id, type: 'success' } as WorkerResponse);
        break;
        
      case 'updateSources':
        if (data?.sources) {
          updateSources(data.sources);
        }
        postMessage({ id, type: 'success' } as WorkerResponse);
        break;
        
      case 'getBearingPhotos':
        if (data?.bearing !== undefined && data?.center) {
          getBearingPhotos(data.bearing, data.center);
        }
        postMessage({ id, type: 'success' } as WorkerResponse);
        break;
        
      case 'updateConfig':
        if (data?.config) {
          if (data.config.recalculateBearingDistances !== undefined) {
            recalculateBearingDistances = data.config.recalculateBearingDistances;
            console.log('Worker: Updated recalculateBearingDistances to', recalculateBearingDistances);
          }
        }
        postMessage({ id, type: 'success' } as WorkerResponse);
        break;
        
      case 'terminate':
        self.close();
        break;
        
      default:
        throw new Error(`Unknown message type: ${type}`);
    }
  } catch (error: any) {
    postMessage({
      id,
      type: 'error',
      error: { message: error?.message || 'Unknown error' }
    } as WorkerResponse);
  }
};

// Export for TypeScript
export {};