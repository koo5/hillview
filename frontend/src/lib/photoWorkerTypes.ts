import type {PhotoId, SimpleCoord, PhotoSize, BasePhotoData} from './types/photoCommon';

// Re-export common types for use in other worker files
export type {PhotoId, SimpleCoord, PhotoSize};

// Worker-specific photo data (extends base with SimpleCoord)
export interface PhotoData extends BasePhotoData {
    coord: SimpleCoord;  // Override with SimpleCoord for workers
    source?: any;  // Worker version uses any instead of Source type
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
    color?: string;
    url?: string;
    path?: string;
    backend_url?: string;  // For Mapillary API
    client_id?: string;    // For Mapillary API
}

// Worker message types
export type WorkerMessageType =
    | 'init'
    /*| 'loadFromSources'*/
    /*| 'updateBounds'*/
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
        photos_in_range?: PhotoData[];
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
    photos_in_range: PhotoData[];
    bearing: number;
}

export interface WorkerError {
    message: string;
    operation?: string;
    timestamp?: number;
}
