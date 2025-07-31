import type { LatLng } from 'leaflet';

// Photo data types
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
  type?: string;
  url?: string;
  path?: string;
  name?: string;
}

// Worker message types
export type WorkerMessageType = 
  | 'init' 
  | 'loadPhotos' 
  | 'loadFromSources'
  | 'updateBounds'
  | 'updateSources' 
  | 'getPhotosInRange'
  | 'updateConfig'
  | 'terminate';

export type WorkerResponseType = 
  | 'ready' 
  | 'success' 
  | 'photosUpdate' 
  | 'bearingUpdate' 
  | 'error';

export interface WorkerMessage {
  id: string;
  type: WorkerMessageType;
  data?: {
    photos?: PhotoData[];
    bounds?: Bounds;
    range?: number;
    sources?: SourceConfig[];
    bearing?: number;
    center?: { lat: number; lng: number };
    config?: {
      recalculateBearingDiffForAllPhotosInArea?: boolean;
    };
  };
}

export interface WorkerResponse {
  id: string;
  type: WorkerResponseType;
  data?: {
    photos?: PhotoData[];
    hillviewCount?: number;
    mapillaryCount?: number;
    photosInRange?: PhotoData[];
    bearing?: number;
  };
  error?: {
    message: string;
    operation?: string;
    timestamp?: number;
  };
}

// Result types
export interface PhotosUpdateData {
  photos: PhotoData[];
  hillviewCount: number;
  mapillaryCount: number;
}

export interface BearingUpdateData {
  photosInRange: PhotoData[];
  bearing: number;
}

export interface WorkerError {
  message: string;
  operation?: string;
  timestamp?: number;
}