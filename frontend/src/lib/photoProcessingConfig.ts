import { localStorageSharedStore } from './svelte-shared-store';

// Configuration for photo processing
export const USE_WEBWORKER = localStorageSharedStore('use_webworker', true);

// Common interface for both services
export interface PhotoProcessingServiceInterface {
  // For the existing PhotoProcessingService
  queueAreaFilter?: (bounds: any, range: number, sourcesConfig: any[]) => void;
  queueBearingUpdate?: (bearing: number, photoIds: string[], priority?: string) => void;
  queueDistanceCalculation?: (photoIds: string[], center: any, range: number) => void;
  onResult?: (type: string, callback: (result: any) => void) => void;
  updatePhotoStore?: (photos: any[]) => void;
  
  // For the new PhotoWorkerService
  initialize?: () => Promise<void>;
  loadPhotos?: (photos: any[]) => Promise<void>;
  updateMapBounds?: (bounds: any) => Promise<void>;
  updateRange?: (range: number) => Promise<void>;
  updateSources?: (sources: any[]) => Promise<void>;
  updateBearing?: (bearing: number, center: any) => Promise<void>;
  onPhotosUpdate?: (callback: (photos: any[]) => void) => void;
  onBearingUpdate?: (callback: (result: any) => void) => void;
  getCurrentBearingData?: () => any | null;
  terminate?: () => void;
}