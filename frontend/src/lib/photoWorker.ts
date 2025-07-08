import { LatLng } from 'leaflet';

// Worker message types
export interface WorkerMessage {
  id: string;
  type: 'init' | 'loadPhotos' | 'updateBounds' | 'updateRange' | 'updateSources' | 'getBearingPhotos' | 'terminate';
  data?: any;
}

export interface WorkerResponse {
  id: string;
  type: 'photosUpdate' | 'bearingUpdate' | 'error';
  data?: any;
}

// Data types (copied from photoProcessing.ts)
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

export interface Bounds {
  top_left: LatLng;
  bottom_right: LatLng;
}

export interface SourceConfig {
  id: string;
  enabled: boolean;
}

// Web Worker wrapper class
class PhotoWorkerManager {
  private worker: Worker | null = null;
  private messageId = 0;
  private pendingMessages = new Map<string, { resolve: Function; reject: Function }>();
  private onPhotosUpdateCallback: ((photos: PhotoData[]) => void) | null = null;
  private onBearingUpdateCallback: ((result: any) => void) | null = null;

  constructor() {}

  async initialize(): Promise<void> {
    if (this.worker) {
      return;
    }

    // Create worker with inline code
    const workerCode = `
      // Import distance calculation utilities
      class Coordinate {
        constructor(lat, lng) {
          this.lat = lat;
          this.lng = lng;
        }
      }
      
      class DistanceCalculator {
        getDistance(coord1, coord2) {
          const R = 6371000; // Earth's radius in meters
          const lat1Rad = coord1.lat * Math.PI / 180;
          const lat2Rad = coord2.lat * Math.PI / 180;
          const deltaLat = (coord2.lat - coord1.lat) * Math.PI / 180;
          const deltaLng = (coord2.lng - coord1.lng) * Math.PI / 180;
          
          const a = Math.sin(deltaLat/2) * Math.sin(deltaLat/2) +
                   Math.cos(lat1Rad) * Math.cos(lat2Rad) *
                   Math.sin(deltaLng/2) * Math.sin(deltaLng/2);
          const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
          
          return R * c;
        }
      }
      
      const calculator = new DistanceCalculator();
      
      // Photo data store - source of truth
      let photoStore = new Map();
      let currentBounds = null;
      let currentRange = 5000; // Default 5km range
      let sourcesConfig = [];
      let lastVisiblePhotos = [];
      
      // Configuration
      const MAX_PHOTOS_IN_AREA = 500;
      const MAX_PHOTOS_IN_RANGE = 100;
      
      // Spatial indexing for efficient queries
      class PhotoSpatialIndex {
        constructor(gridSize = 0.01) {
          this.gridSize = gridSize;
          this.grid = new Map();
          this.photoLocations = new Map();
        }
        
        addPhoto(photoId, lat, lng) {
          this.photoLocations.set(photoId, { lat, lng });
          const key = this.getGridKey(lat, lng);
          
          if (!this.grid.has(key)) {
            this.grid.set(key, new Set());
          }
          this.grid.get(key).add(photoId);
        }
        
        removePhoto(photoId) {
          const location = this.photoLocations.get(photoId);
          if (!location) return;
          
          const key = this.getGridKey(location.lat, location.lng);
          this.grid.get(key)?.delete(photoId);
          this.photoLocations.delete(photoId);
        }
        
        getPhotoIdsInBounds(bounds, maxResults = 2000) {
          const results = [];
          const seen = new Set();
          
          if (this.photoLocations.size === 0) {
            return results;
          }
          
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
          
          for (let lat = minLat; lat <= maxLat; lat += latStep) {
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
                        return results;
                      }
                    }
                  }
                }
              }
            }
          }
          
          return results;
        }
        
        getGridKey(lat, lng) {
          const gridLat = Math.floor(lat / this.gridSize) * this.gridSize;
          const gridLng = Math.floor(lng / this.gridSize) * this.gridSize;
          return \`\${gridLat},\${gridLng}\`;
        }
        
        isInBounds(location, bounds) {
          const normalizeLng = (lng) => {
            while (lng > 180) lng -= 360;
            while (lng < -180) lng += 360;
            return lng;
          };
          
          const photoLng = normalizeLng(location.lng);
          const leftLng = normalizeLng(bounds.top_left.lng);
          const rightLng = normalizeLng(bounds.bottom_right.lng);
          
          const inLat = location.lat <= bounds.top_left.lat && 
                       location.lat >= bounds.bottom_right.lat;
          
          let inLng;
          if (leftLng > rightLng) {
            // Bounds cross the date line
            inLng = photoLng >= leftLng || photoLng <= rightLng;
          } else {
            // Normal bounds
            inLng = photoLng >= leftLng && photoLng <= rightLng;
          }
          
          return inLat && inLng;
        }
        
        clear() {
          this.photoLocations.clear();
          this.grid.clear();
        }
      }
      
      const spatialIndex = new PhotoSpatialIndex();
      
      // Photo processing functions
      function loadPhotos(photos) {
        photoStore.clear();
        spatialIndex.clear();
        
        for (const photo of photos) {
          photoStore.set(photo.id, photo);
          spatialIndex.addPhoto(photo.id, photo.coord.lat, photo.coord.lng);
        }
        
        console.log(\`Worker: Loaded \${photos.length} photos\`);
        recalculateVisiblePhotos();
      }
      
      function updateBounds(bounds) {
        currentBounds = bounds;
        recalculateVisiblePhotos();
      }
      
      function updateRange(range) {
        currentRange = range;
        recalculateVisiblePhotos();
      }
      
      function updateSources(sources) {
        sourcesConfig = sources;
        recalculateVisiblePhotos();
      }
      
      function recalculateVisiblePhotos() {
        if (!currentBounds) {
          return;
        }
        
        const startTime = performance.now();
        
        const hillviewEnabled = sourcesConfig.find(s => s.id === 'hillview')?.enabled ?? false;
        const mapillaryEnabled = sourcesConfig.find(s => s.id === 'mapillary')?.enabled ?? false;
        
        let hillviewFiltered = [];
        let mapillaryFiltered = [];
        
        // Get photo IDs in spatial bounds first
        const photoIdsInBounds = spatialIndex.getPhotoIdsInBounds(currentBounds, MAX_PHOTOS_IN_AREA * 2);
        
        // Filter by source and apply limits
        if (hillviewEnabled) {
          const hillviewInBounds = [];
          
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
          const mapillaryInBounds = [];
          
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
        
        // Combine and deduplicate
        const combinedMap = new Map();
        
        for (const photo of hillviewFiltered) {
          combinedMap.set(photo.id, photo);
        }
        
        for (const photo of mapillaryFiltered) {
          if (!combinedMap.has(photo.id)) {
            combinedMap.set(photo.id, photo);
          }
        }
        
        const visiblePhotos = Array.from(combinedMap.values());
        
        // Apply bearing fixup
        fixupBearings(visiblePhotos);
        
        lastVisiblePhotos = visiblePhotos;
        
        console.log(\`Worker: Filtered \${visiblePhotos.length} photos in \${performance.now() - startTime}ms\`);
        
        // Send update to main thread
        postMessage({
          id: 'auto',
          type: 'photosUpdate',
          data: {
            photos: visiblePhotos,
            hillviewCount: hillviewFiltered.length,
            mapillaryCount: mapillaryFiltered.length
          }
        });
      }
      
      function fixupBearings(photos) {
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
            let diff = next.bearing - photo.bearing;
            if (diff === 0) {
              next.bearing = (next.bearing + 0.01 * iterations) % 360;
              moved = true;
            }
          }
        }
      }
      
      function getBearingPhotos(bearing, center) {
        // Calculate distances for current visible photos
        const photosWithDistance = [];
        const centerCoord = new Coordinate(center.lat, center.lng);
        
        for (const photo of lastVisiblePhotos) {
          const photoCoord = new Coordinate(photo.coord.lat, photo.coord.lng);
          const distance = calculator.getDistance(centerCoord, photoCoord);
          
          if (distance <= currentRange) {
            photosWithDistance.push({
              ...photo,
              range_distance: distance
            });
          }
        }
        
        // Sort by distance and limit
        photosWithDistance.sort((a, b) => a.range_distance - b.range_distance);
        const photosInRange = photosWithDistance.slice(0, MAX_PHOTOS_IN_RANGE);
        
        // Update bearing colors (but don't sort - leave that to main thread)
        const photosWithBearings = photosInRange.map(photo => {
          const absBearingDiff = Math.abs(angleDifference(bearing, photo.bearing));
          const bearingColor = getBearingColor(absBearingDiff);
          
          return {
            ...photo,
            abs_bearing_diff: absBearingDiff,
            bearing_color: bearingColor
          };
        });
        
        postMessage({
          id: 'auto',
          type: 'bearingUpdate',
          data: {
            photosInRange: photosWithBearings,
            bearing: bearing
          }
        });
      }
      
      function angleDifference(a, b) {
        const diff = Math.abs(a - b);
        return diff > 180 ? 360 - diff : diff;
      }
      
      function getBearingColor(absBearingDiff) {
        if (absBearingDiff === null) return '#9E9E9E';
        return 'hsl(' + Math.round(100 - absBearingDiff/2) + ', 100%, 70%)';
      }
      
      // Message handler
      self.onmessage = function(e) {
        const { id, type, data } = e.data;
        
        try {
          switch (type) {
            case 'init':
              // Worker initialized
              postMessage({ id, type: 'ready' });
              break;
              
            case 'loadPhotos':
              loadPhotos(data.photos);
              break;
              
            case 'updateBounds':
              updateBounds(data.bounds);
              break;
              
            case 'updateRange':
              updateRange(data.range);
              break;
              
            case 'updateSources':
              updateSources(data.sources);
              break;
              
            case 'getBearingPhotos':
              getBearingPhotos(data.bearing, data.center);
              break;
              
            case 'terminate':
              self.close();
              break;
              
            default:
              throw new Error(\`Unknown message type: \${type}\`);
          }
        } catch (error) {
          postMessage({
            id,
            type: 'error',
            data: { error: error.message }
          });
        }
      };
    `;

    const blob = new Blob([workerCode], { type: 'application/javascript' });
    this.worker = new Worker(URL.createObjectURL(blob));

    this.worker.onmessage = (e) => {
      const { id, type, data } = e.data;
      
      if (type === 'photosUpdate' && this.onPhotosUpdateCallback) {
        this.onPhotosUpdateCallback(data.photos);
      } else if (type === 'bearingUpdate' && this.onBearingUpdateCallback) {
        this.onBearingUpdateCallback(data);
      } else if (type === 'error') {
        console.error('Photo worker error:', data.error);
      } else {
        // Handle regular message responses
        const pending = this.pendingMessages.get(id);
        if (pending) {
          this.pendingMessages.delete(id);
          pending.resolve(data);
        }
      }
    };

    this.worker.onerror = (error) => {
      console.error('Photo worker error:', error);
    };

    // Initialize worker
    await this.sendMessage('init');
  }

  private async sendMessage(type: string, data?: any): Promise<any> {
    if (!this.worker) {
      throw new Error('Worker not initialized');
    }

    const id = `msg_${++this.messageId}`;
    
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pendingMessages.delete(id);
        reject(new Error('Worker message timeout'));
      }, 30000);

      this.pendingMessages.set(id, {
        resolve: (result: any) => {
          clearTimeout(timeout);
          resolve(result);
        },
        reject: (error: any) => {
          clearTimeout(timeout);
          reject(error);
        }
      });

      this.worker!.postMessage({ id, type, data });
    });
  }

  // Public API
  async loadPhotos(photos: PhotoData[]): Promise<void> {
    await this.sendMessage('loadPhotos', { photos });
  }

  async updateBounds(bounds: Bounds): Promise<void> {
    await this.sendMessage('updateBounds', { bounds });
  }

  async updateRange(range: number): Promise<void> {
    await this.sendMessage('updateRange', { range });
  }

  async updateSources(sources: SourceConfig[]): Promise<void> {
    await this.sendMessage('updateSources', { sources });
  }

  async getBearingPhotos(bearing: number, center: { lat: number; lng: number }): Promise<void> {
    await this.sendMessage('getBearingPhotos', { bearing, center });
  }

  onPhotosUpdate(callback: (photos: PhotoData[]) => void): void {
    this.onPhotosUpdateCallback = callback;
  }

  onBearingUpdate(callback: (result: any) => void): void {
    this.onBearingUpdateCallback = callback;
  }

  terminate(): void {
    if (this.worker) {
      this.worker.terminate();
      this.worker = null;
    }
    this.pendingMessages.clear();
  }
}

// Singleton instance
export const photoWorker = new PhotoWorkerManager();