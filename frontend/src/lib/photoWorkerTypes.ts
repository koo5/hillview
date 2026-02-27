import type {PhotoId, SimpleCoord, PhotoSize, BasePhotoData} from './types/photoCommon';

// Re-export common types for use in other worker files
export type {PhotoId, SimpleCoord, PhotoSize};

// Query options for photo filtering/sorting based on AI analysis
export interface QueryOptions {
    time_of_day: string | null;  // day, night, dawn_dusk
    location_type: string | null;  // indoors, outdoors, mixed
    min_farthest_distance: number | null;  // meters
    max_closest_distance: number | null;  // meters
    min_scenic_score: number | null;  // 1-5
    visibility_distance: string | null;  // near, medium, far, panoramic
    tallest_building: string | null;  // none, low_rise, mid_rise, high_rise, skyscraper
    features: string[];  // OR logic
    // Future: sorting options can be added here
}

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
