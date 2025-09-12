import type {PhotoId} from './types/photoTypes';

// Re-export PhotoId for use in other worker files
export type {PhotoId};

// Simple coordinate interface for worker compatibility (can't import leaflet in workers)
export interface SimpleCoord {
    lat: number;
    lng: number;
}

// Photo data types
export interface PhotoData {
    id: PhotoId;
    source_type: string;
    file: string;
    url: string;
    coord: SimpleCoord;
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
    top_left: SimpleCoord;
    bottom_right: SimpleCoord;
}

export interface SourceConfig {
    id: string;
    name: string;
    type: 'stream' | 'device';
    enabled: boolean;
    requests?: number[];
    color?: string;
    url?: string;
    path?: string;
    backendUrl?: string;  // For Mapillary API
    clientId?: string;    // For Mapillary API
}

// Worker message types
export type WorkerMessageType =
    | 'init'
    | 'loadFromSources'
    | 'updateBounds'
    | 'updateSources'
    | 'updateRange'
    | 'getPhotosInRange'
    | 'updateBearingColors'
    | 'updateConfig'
    | 'terminate';

export type WorkerResponseType =
    | 'ready'
    | 'success'
    | 'photosUpdate'
    | 'rangeUpdate'
    | 'bearingUpdate'
    | 'statusUpdate'
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