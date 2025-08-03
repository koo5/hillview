/// <reference lib="webworker" />

import type { WorkerMessage, WorkerResponse, PhotoData, Bounds, SourceConfig } from './photoWorkerTypes';
// Note: Cannot import Leaflet in worker context (window is not defined)
// import { LatLng } from 'leaflet';
import { loadJsonPhotos } from './utils/photoParser';
import { MapillaryWorkerHandler } from './mapillaryWorkerHandler';

// Webworker version for runtime checking
declare const __WORKER_VERSION__: string;
export const WORKER_VERSION = __WORKER_VERSION__;

console.log(`PhotoWorker: Worker script loaded with version: ${WORKER_VERSION}`);
import { updatePhotoBearingData } from './utils/bearingUtils';
import { getDistance, calculateCenterFromBounds, isInBounds } from './utils/distanceUtils';

// Photo data store - source of truth
const photoStore = new Map<string, PhotoData>();
let currentBounds: Bounds | null = null;
let currentRange = 5000; // Default 5km range
let sourcesConfig: SourceConfig[] = [];

// Initialize Mapillary handler
const mapillaryHandler = new MapillaryWorkerHandler({
  onPhotosAdded: (photos: PhotoData[]) => {
    // Add photos to store and spatial index
    photos.forEach(photo => {
      photoStore.set(photo.id, photo);
      if (spatialIndex) {
        // Handle different PhotoData formats
        if (photo.lat !== undefined && photo.lng !== undefined) {
          // Mapillary format with lat/lng properties
          spatialIndex.addPhoto(photo.id, photo.lat, photo.lng);
        } else if (photo.coord) {
          // Traditional format with coord property
          spatialIndex.addPhoto(photo.id, photo.coord.lat, photo.coord.lng);
        }
      }
    });
    
    // Trigger recalculation if we have bounds
    if (currentBounds) {
      recalculatePhotosInArea();
      
      // Also trigger range update for navigation using bounds center
      const center = calculateCenterFromBounds(currentBounds);
      getPhotosInRange(center);
    }
  },
  onStreamComplete: () => {
    console.log('Worker: Mapillary streaming completed');
  },
  onError: (error: string) => {
    console.error('Worker: Mapillary error:', error);
  },
  onStatusUpdate: (status) => {
    // Send unified status update to main thread for debug panel
    postMessage({
      id: 'auto',
      type: 'statusUpdate',
      data: { 
        mapillaryStatus: {
          // Legacy compatibility fields
          uncached_regions: status.uncachedRegions || 0,
          is_streaming: status.isStreaming,
          total_live_photos: status.totalPhotos,
          
          // New detailed fields
          stream_phase: status.streamPhase,
          completed_regions: status.completedRegions?.length || 0,
          last_request_time: status.lastRequestTime,
          last_response_time: status.lastResponseTime,
          current_url: status.currentUrl,
          last_error: status.lastError,
          last_bounds: status.lastBounds
        }
      }
    } as WorkerResponse);
  }
});
let lastVisiblePhotos: PhotoData[] = [];
let geoPicsUrl = 'http://localhost:8212'; // Default fallback
let recalculateBearingDiffForAllPhotosInArea = false;

// Configuration
const MAX_PHOTOS_IN_AREA = 400;
const MAX_PHOTOS_IN_RANGE = 100;

// Fixed 10x10 spatial index for efficient queries
class PhotoSpatialIndex {
  private grid: Set<string>[] = []; // Fixed array of 100 cells (10x10)
  private photoLocations = new Map<string, { lat: number; lng: number }>();
  private minLat = Infinity;
  private maxLat = -Infinity;
  private minLng = Infinity;
  private maxLng = -Infinity;
  
  constructor() {
    // Initialize 100 grid cells (10x10)
    for (let i = 0; i < 100; i++) {
      this.grid[i] = new Set<string>();
    }
  }
  
  addPhoto(photoId: string, lat: number, lng: number): void {
    this.photoLocations.set(photoId, { lat, lng });
    
    // Update bounds
    this.minLat = Math.min(this.minLat, lat);
    this.maxLat = Math.max(this.maxLat, lat);
    this.minLng = Math.min(this.minLng, lng);
    this.maxLng = Math.max(this.maxLng, lng);
    
    // Add to grid cell
    const cellIndex = this.getGridCellIndex(lat, lng);
    this.grid[cellIndex].add(photoId);
  }
  
  removePhoto(photoId: string): void {
    const location = this.photoLocations.get(photoId);
    if (!location) return;
    
    const cellIndex = this.getGridCellIndex(location.lat, location.lng);
    this.grid[cellIndex].delete(photoId);
    this.photoLocations.delete(photoId);
  }
  
  getPhotoIdsInBounds(bounds: Bounds): string[] {
    const results: string[] = [];
    
    if (this.photoLocations.size === 0) {
      console.log('PhotoSpatialIndex: No photos in index');
      return results;
    }
    
    // If no photos have been added yet, return empty
    if (this.minLat === Infinity) {
      return results;
    }
    
    // Calculate which grid cells intersect with the bounds
    const startTime = performance.now();
    
    for (let cellIndex = 0; cellIndex < 100; cellIndex++) {
      const photoIds = this.grid[cellIndex];
      if (photoIds.size === 0) continue;
      
      // Check each photo in this cell
      for (const photoId of photoIds) {
        const location = this.photoLocations.get(photoId);
        if (location && this.isInBounds(location, bounds)) {
          results.push(photoId);
        }
      }
    }
    
    const processingTime = performance.now() - startTime;
    console.log(`PhotoSpatialIndex: Found ${results.length} photos in ${processingTime.toFixed(1)}ms (fixed 10x10 grid)`);
    
    return results;
  }
  
  private getGridCellIndex(lat: number, lng: number): number {
    // Handle edge case where we have no bounds yet
    if (this.minLat === Infinity) {
      return 0;
    }
    
    // Prevent division by zero
    const latRange = this.maxLat - this.minLat;
    const lngRange = this.maxLng - this.minLng;
    
    if (latRange === 0 && lngRange === 0) {
      return 0; // All photos at same location
    }
    
    // Calculate grid position (0-9 for each dimension)
    const latGrid = latRange === 0 ? 0 : Math.floor(((lat - this.minLat) / latRange) * 10);
    const lngGrid = lngRange === 0 ? 0 : Math.floor(((lng - this.minLng) / lngRange) * 10);
    
    // Clamp to valid range (0-9)
    const clampedLatGrid = Math.max(0, Math.min(9, latGrid));
    const clampedLngGrid = Math.max(0, Math.min(9, lngGrid));
    
    // Convert to single index (0-99)
    return clampedLatGrid * 10 + clampedLngGrid;
  }
  
  private isInBounds(location: { lat: number; lng: number }, bounds: Bounds): boolean {
    return isInBounds(location, bounds);
  }
  
  clear(): void {
    this.photoLocations.clear();
    for (let i = 0; i < 100; i++) {
      this.grid[i].clear();
    }
    this.minLat = Infinity;
    this.maxLat = -Infinity;
    this.minLng = Infinity;
    this.maxLng = -Infinity;
  }
}

const spatialIndex = new PhotoSpatialIndex();

// Grid-based photo sampling
function samplePhotosInGrid(photos: PhotoData[], maxPhotos: number): PhotoData[] {
  if (photos.length <= maxPhotos) return photos;

  console.log(`Worker: Sampling ${photos.length} photos down to ${maxPhotos} using grid sampling`);
  
  // Create a 10x10 grid
  const gridSize = 10;
  const totalCells = gridSize * gridSize;
  
  // Find bounds of all photos
  let minLat = Infinity, maxLat = -Infinity;
  let minLng = Infinity, maxLng = -Infinity;
  
  for (const photo of photos) {
    minLat = Math.min(minLat, photo.coord.lat);
    maxLat = Math.max(maxLat, photo.coord.lat);
    minLng = Math.min(minLng, photo.coord.lng);
    maxLng = Math.max(maxLng, photo.coord.lng);
  }
  
  const latStep = (maxLat - minLat) / gridSize;
  const lngStep = (maxLng - minLng) / gridSize;
  
  // Create grid cells
  const grid = new Map<string, PhotoData[]>();
  
  // Assign photos to grid cells
  for (const photo of photos) {
    const gridLat = Math.floor((photo.coord.lat - minLat) / latStep);
    const gridLng = Math.floor((photo.coord.lng - minLng) / lngStep);
    const cellKey = `${Math.min(gridLat, gridSize - 1)},${Math.min(gridLng, gridSize - 1)}`;
    
    if (!grid.has(cellKey)) {
      grid.set(cellKey, []);
    }
    grid.get(cellKey)!.push(photo);
  }
  
  // Sample photos from grid cells
  const sampledPhotos: PhotoData[] = [];
  const photosPerCell = Math.ceil(maxPhotos / totalCells);
  
  for (const cellPhotos of grid.values()) {
    if (cellPhotos.length <= photosPerCell) {
      sampledPhotos.push(...cellPhotos);
    } else {
      // Sample evenly from cell
      const step = cellPhotos.length / photosPerCell;
      for (let i = 0; i < photosPerCell; i++) {
        const index = Math.floor(i * step);
        sampledPhotos.push(cellPhotos[index]);
      }
    }
    
    if (sampledPhotos.length >= maxPhotos) break;
  }

  console.log(`Worker: Sampled down to ${sampledPhotos.length} photos from ${photos.length}, slicing to max ${maxPhotos}`);
  return sampledPhotos.slice(0, maxPhotos);
}

// Photo loading from sources
async function loadFromSources(sources: SourceConfig[]): Promise<void> {
  try {
    console.log('Worker: Loading photos from sources', sources.map(s => ({ id: s.id, enabled: s.enabled, type: s.type, url: s.url })));
    console.log('Worker: Full source objects:', sources);
    try {
      console.log('Worker: First source JSON:', JSON.stringify(sources[0]));
      console.log('Worker: First source type directly:', sources[0].type);
      console.log('Worker: Sources array JSON:', JSON.stringify(sources));
    } catch (e) {
      console.log('Worker: JSON serialization failed:', e);
    }
    
    // Check if Mapillary is disabled and stop stream if needed
    const mapillarySource = sources.find(s => s.id === 'mapillary');
    if (!mapillarySource || !mapillarySource.enabled) {
      console.log('Worker: Mapillary disabled or not found, stopping stream');
      mapillaryHandler.stopStream();
      mapillaryHandler.clearPhotos();
    }
    
    photoStore.clear();
    spatialIndex.clear();
    
    const allPhotos: PhotoData[] = [];
    
    for (const source of sources) {
      if (!source.enabled) {
        console.log(`Worker: Skipping disabled source: ${source.id}`);
        continue;
      }
      
      try {
        let sourcePhotos: PhotoData[] = [];
        
        switch (source.type) {
          case 'json':
            if (source.url) {
              sourcePhotos = await loadJsonPhotos(source.url, geoPicsUrl);
              
              // Set source reference on each photo
              sourcePhotos.forEach(photo => {
                photo.source = source;
              });
            }
            break;
          case 'mapillary':
            console.log('Worker: Starting Mapillary streaming for source:', source.id);
            // Start Mapillary streaming - photos will be added via callback
            if (currentBounds && source.backendUrl && source.clientId) {
              await mapillaryHandler.startStream(
                currentBounds.top_left.lat,
                currentBounds.top_left.lng,
                currentBounds.bottom_right.lat,
                currentBounds.bottom_right.lng,
                source.clientId,
                source.backendUrl
              );
            } else {
              console.log('Worker: Cannot start Mapillary stream - missing bounds or config');
            }
            // Note: sourcePhotos remains empty here, photos are added via callback
            break;
          case 'device':
            console.log('Worker: Device photo loading not yet implemented in worker');
            break;
          case 'directory':
            console.log('Worker: Directory photo loading not yet implemented in worker');
            break;
          default:
            console.log(`Worker: Unknown source type: ${source.type} for source ${source.id}`);
        }
        
        console.log(`Worker: Loaded ${sourcePhotos.length} photos from ${source.id}`);
        allPhotos.push(...sourcePhotos);
        
      } catch (error) {
        console.error(`Worker: Error loading from source ${source.id}:`, error);
      }
    }
    
    // Load photos into worker stores
    for (const photo of allPhotos) {
      photoStore.set(photo.id, photo);
      spatialIndex.addPhoto(photo.id, photo.coord.lat, photo.coord.lng);
    }
    
    console.log(`Worker: Total loaded ${allPhotos.length} photos from ${sources.length} sources`);
    recalculatePhotosInArea();
    
  } catch (error) {
    console.error('Worker: Error in loadFromSources:', error);
    postError('loadFromSources', error);
  }
}

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
    recalculatePhotosInArea();
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
      recalculatePhotosInArea();
    } else {
      console.log('Worker: Bounds unchanged, skipping recalculation');
    }
  } catch (error) {
    console.error('Worker: Error updating bounds:', error);
    postError('updateBounds', error);
  }
}

async function updateSources(sources: SourceConfig[]): Promise<void> {
  try {
    // Only reload if sources actually changed
    const sourcesChanged = !sourcesConfig || 
      sourcesConfig.length !== sources.length ||
      sourcesConfig.some((s, i) => s.id !== sources[i]?.id || s.enabled !== sources[i]?.enabled);
    
    if (sourcesChanged) {
      console.log('Worker: Source configuration changed, reloading photos');
      sourcesConfig = sources;
      
      // Reload photos with new source configuration
      await loadFromSources(sources);
    }
  } catch (error) {
    console.error('Worker: Error updating sources:', error);
    postError('updateSources', error);
  }
}

function recalculatePhotosInArea(): void {
  if (!currentBounds) {
    console.log('Worker: recalculatePhotosInArea: No bounds set, skipping recalculation. Photos loaded:', photoStore.size);
    return;
  }
  
  console.log('Worker: recalculatePhotosInArea: bounds:', currentBounds, 'input Photos:', photoStore.size);
  const startTime = performance.now();
  
  // Get photo IDs in spatial bounds first  
  const photoIdsInBounds = spatialIndex.getPhotoIdsInBounds(currentBounds);
  console.log(`Worker: recalculatePhotosInArea: Found ${photoIdsInBounds.length} photos in bounds`);
  
  // Get all photos in bounds (source filtering already done at load time)
  const photosInBounds: PhotoData[] = [];
  
  for (const photoId of photoIdsInBounds) {
    const photo = photoStore.get(photoId);
    if (photo) {
      photosInBounds.push(photo);
    }
  }
  
  // Apply grid-based sampling if too many photos
  const visiblePhotos = photosInBounds.length <= MAX_PHOTOS_IN_AREA 
    ? photosInBounds 
    : samplePhotosInGrid(photosInBounds, MAX_PHOTOS_IN_AREA);
  
  // Sort by bearing, then by ID for stable ordering
  visiblePhotos.sort((a, b) => {
    if (a.bearing !== b.bearing) {
      return a.bearing - b.bearing;
    }
    return a.id.localeCompare(b.id);
  });
  
  // Calculate distances from center of bounds
  const center = calculateCenterFromBounds(currentBounds);
  
  for (const photo of visiblePhotos) {
    const distance = getDistance(center, photo.coord);
    //console.log(`Worker: Photo ${photo.id} distance from center: ${distance.toFixed(2)}m`);
    photo.range_distance = distance <= currentRange ? distance : null;
  }
  
  lastVisiblePhotos = visiblePhotos;
  
  // Only log when we have results or significant processing time
  const processingTime = performance.now() - startTime;
  //if (visiblePhotos.length > 0 || processingTime > 10) {
    console.log(`Worker: recalculatePhotosInArea: Filtered down to ${visiblePhotos.length} photos in ${processingTime.toFixed(1)}ms`);
  //}
  
  // Send update to main thread
  postMessage({
    id: 'auto',
    type: 'photosUpdate',
    data: {
      photos: visiblePhotos,
      hillviewCount: 0,
      mapillaryCount: 0
    }
  } as WorkerResponse);
}


function getPhotosInRange(center: { lat: number; lng: number }): void {
  try {
    let photosWithDistance: PhotoData[] = [];
    
    console.log('Worker: Recalculating distances for photos, lastVisiblePhotos:', lastVisiblePhotos.length);
    for (const photo of lastVisiblePhotos) {
      const distance = getDistance(center, photo.coord);

      //console.log(`Worker: Photo ${photo.id} distance from center: ${distance.toFixed(2)}m, limit: ${currentRange}m`);

      if (distance <= currentRange) {
        photosWithDistance.push({
          ...photo,
          range_distance: distance
        });
      }
    }

    // Limit photos (preserve bearing order from lastVisiblePhotos)
    photosWithDistance = photosWithDistance.slice(0, MAX_PHOTOS_IN_RANGE);
    console.log(`Worker: getPhotosInRange filtered ${photosWithDistance.length} photos within range`);

    postMessage({
      id: 'auto',
      type: 'rangeUpdate',
      data: {
        photosInRange: photosWithDistance
      }
    } as WorkerResponse);
  } catch (error) {
    console.error('Worker: Error filtering photos by range:', error);
    postError('getPhotosInRange', error);
  }
}

function updateBearingColors(bearing: number): void {
  try {
    console.log(`Worker: Updating bearing colors for ${lastVisiblePhotos.length} photos, bearing: ${bearing}`);
    
    // Update bearing colors for all visible photos
    const photosWithColors = lastVisiblePhotos.map(photo =>
      updatePhotoBearingData(photo, bearing)
    );
    
    postMessage({
      id: 'auto',
      type: 'bearingUpdate',
      data: {
        photos: photosWithColors,
        bearing: bearing
      }
    } as WorkerResponse);
  } catch (error) {
    console.error('Worker: Error updating bearing colors:', error);
    postError('updateBearingColors', error);
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
self.onmessage = async function(e: MessageEvent<WorkerMessage>) {
  const { id, type, data } = e.data;
  
  try {
    switch (type) {
      case 'init':
        // Worker initialized
        console.log(`PhotoWorker: Init request received, responding with version: ${WORKER_VERSION}`);
        postMessage({ id, type: 'ready', data: { version: WORKER_VERSION } } as WorkerResponse);
        break;
        
      case 'loadPhotos':
        if (data?.photos) {
          loadPhotos(data.photos);
        }
        postMessage({ id, type: 'success' } as WorkerResponse);
        break;
        
      case 'loadFromSources':
        console.log('Worker: loadFromSources message received, data:', data);
        if (data?.sources) {
          console.log('Worker: data.sources is valid, length:', data.sources.length);
          await loadFromSources(data.sources);
        } else {
          console.log('Worker: data.sources is invalid:', data?.sources);
        }
        postMessage({ id, type: 'success' } as WorkerResponse);
        break;
        
      case 'updateBounds':
        if (data?.bounds) {
          updateBounds(data.bounds);
        }
        postMessage({ id, type: 'success' } as WorkerResponse);
        break;
        
      case 'updateSources':
        if (data?.sources) {
          await updateSources(data.sources);
        }
        postMessage({ id, type: 'success' } as WorkerResponse);
        break;
        
      case 'updateRange':
        if (data?.range !== undefined) {
          console.log(`Worker: Updating range from ${currentRange} to ${data.range}`);
          currentRange = data.range;
        }
        postMessage({ id, type: 'success' } as WorkerResponse);
        break;
        
      case 'getPhotosInRange':
        if (data?.center) {
          getPhotosInRange(data.center);
        }
        postMessage({ id, type: 'success' } as WorkerResponse);
        break;
        
      case 'updateBearingColors':
        if (data?.bearing !== undefined) {
          updateBearingColors(data.bearing);
        }
        postMessage({ id, type: 'success' } as WorkerResponse);
        break;
        
      case 'updateConfig':
        if (data?.config) {
          if (data.config.recalculateBearingDiffForAllPhotosInArea !== undefined) {
            recalculateBearingDiffForAllPhotosInArea = data.config.recalculateBearingDiffForAllPhotosInArea;
            console.log('Worker: Updated recalculateBearingDiffForAllPhotosInArea to', recalculateBearingDiffForAllPhotosInArea);
          }
          if (data.config.geoPicsUrl !== undefined) {
            geoPicsUrl = data.config.geoPicsUrl;
            console.log('Worker: Updated geoPicsUrl to', geoPicsUrl);
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